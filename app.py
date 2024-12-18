from flask import Flask, render_template, request, redirect, url_for, flash, abort
import json
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv
import logging

load_dotenv()  # Chargement des variables d'environnement depuis .env

app = Flask(__name__)
# Configuration du mode développement
app.config['DEV_MODE'] = os.environ.get('DEV_MODE', 'false').lower() == 'true'
app.config['ENV'] = os.environ.get('FLASK_ENV', 'production')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'votre_clé_secrète_ici')
app.logger.setLevel(logging.INFO)

# Log du mode de l'application au démarrage
app.logger.info(f"Application running in {'DEVELOPMENT' if app.config['DEV_MODE'] else 'PRODUCTION'} mode")

# Configuration Cloudinary
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# Liste des mois en français
MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

def save_gallery_data(data):
    with open('galleries.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_gallery_data():
    try:
        with open('galleries.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def format_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{date.day} {MOIS_FR[date.month-1]} {date.year}"

@app.route('/')
def index():
    galleries = load_gallery_data()
    
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        date = datetime.strptime(gallery['date'], '%Y-%m-%d')
        month_key = f"{MOIS_FR[date.month-1]} {date.year}"
        month_num = date.strftime('%m')
        year = date.strftime('%Y')
        
        if month_key not in galleries_by_month:
            galleries_by_month[month_key] = {
                'galleries': [],
                'month': int(month_num),
                'year': int(year),
                'cover': None
            }
        
        # Ajouter l'ID de la galerie à l'objet gallery pour le tri
        gallery['id'] = gallery_id
        galleries_by_month[month_key]['galleries'].append(gallery)
        
        # Utiliser la première image de couverture trouvée comme cover du mois
        if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
            galleries_by_month[month_key]['cover'] = gallery['cover_image']
    
    return render_template('index.html', 
                         galleries_by_month=galleries_by_month,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/gallery/<gallery_id>')
def gallery(gallery_id):
    galleries = load_gallery_data()
    gallery = galleries.get(gallery_id)
    if not gallery:
        return "Gallery not found", 404
    # Ajouter l'ID à l'objet gallery
    gallery['id'] = gallery_id
    return render_template('gallery.html', 
                         gallery=gallery, 
                         dev_mode=app.config['DEV_MODE'],
                         format_date=format_date)

@app.route('/<int:year>/<int:month>')
def month_galleries(year, month):
    galleries = load_gallery_data()
    month_galleries = []
    background_image = None
    
    for gallery_id, gallery in galleries.items():
        date = datetime.strptime(gallery['date'], '%Y-%m-%d')
        if date.year == year and date.month == month:
            gallery['id'] = gallery_id
            gallery['formatted_date'] = format_date(gallery['date'])
            month_galleries.append(gallery)
            if not background_image and gallery.get('cover_image'):
                background_image = gallery['cover_image']
    
    if not month_galleries:
        return "Aucune galerie trouvée pour ce mois", 404
    
    # Trier les galeries par date croissante
    month_galleries.sort(key=lambda x: x['date'])
    
    month_name = f"{MOIS_FR[month-1]} {year}"
    return render_template('month.html', 
                         galleries=month_galleries,
                         month=month_name,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/upload_photos/<gallery_id>', methods=['POST'])
def upload_photos(gallery_id):
    app.logger.info(f"Début de l'upload pour gallery_id: {gallery_id}")
    
    if 'photos' not in request.files:
        app.logger.warning("Pas de fichiers dans la requête")
        flash('Aucune photo sélectionnée')
        return redirect(url_for('gallery', gallery_id=gallery_id))
    
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        app.logger.error(f"Galerie {gallery_id} non trouvée")
        flash('Galerie non trouvée')
        return redirect(url_for('index'))
    
    gallery = galleries[gallery_id]
    if 'photos' not in gallery:
        gallery['photos'] = []
    
    files = request.files.getlist('photos')
    app.logger.info(f"Nombre de fichiers reçus : {len(files)}")
    
    for file in files:
        if file.filename:
            try:
                app.logger.info(f"Upload de {file.filename}")
                # Vérifier la configuration Cloudinary
                app.logger.info("Configuration Cloudinary:")
                app.logger.info(f"Cloud name: {cloudinary.config().cloud_name}")
                app.logger.info(f"API Key présente: {'Oui' if cloudinary.config().api_key else 'Non'}")
                
                # Upload to Cloudinary
                result = cloudinary.uploader.upload(file)
                app.logger.info(f"Upload réussi: {result['secure_url']}")
                
                gallery['photos'].append({
                    'url': result['secure_url'],
                    'filename': file.filename
                })
            except Exception as e:
                app.logger.error(f"Erreur lors de l'upload de {file.filename}: {str(e)}")
                import traceback
                app.logger.error(traceback.format_exc())
                flash(f'Erreur lors du téléchargement de {file.filename}: {str(e)}')
                continue
    
    try:
        save_gallery_data(galleries)
        app.logger.info("Données sauvegardées avec succès")
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")
        flash('Erreur lors de la sauvegarde des données')
        return redirect(url_for('gallery', gallery_id=gallery_id))
    
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/create_gallery', methods=['POST'])
def create_gallery():
    name = request.form.get('name', '').strip()
    date = request.form.get('date', '').strip()
    description = request.form.get('description', '').strip()
    
    if not name or not date:
        flash('Le nom et la date sont requis')
        return redirect(url_for('index'))
    
    galleries = load_gallery_data()
    
    # Générer un ID unique pour la nouvelle galerie
    gallery_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Créer la nouvelle galerie
    new_gallery = {
        'name': name,
        'date': date,
        'description': description,
        'photos': []
    }
    
    # Gérer l'image de couverture si fournie
    if 'cover_image' in request.files:
        cover_file = request.files['cover_image']
        if cover_file.filename:
            try:
                result = cloudinary.uploader.upload(cover_file)
                new_gallery['cover_image'] = result['secure_url']
            except Exception as e:
                flash(f'Erreur lors du téléchargement de l\'image de couverture: {str(e)}')
    
    galleries[gallery_id] = new_gallery
    save_gallery_data(galleries)
    
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/edit_gallery/<gallery_id>', methods=['POST'])
def edit_gallery(gallery_id):
    app.logger.info(f"Modification de la galerie {gallery_id}")
    app.logger.info(f"Données reçues: {request.form}")
    
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        flash('Galerie non trouvée')
        return redirect(url_for('index'))
    
    gallery = galleries[gallery_id]
    gallery['name'] = request.form.get('name', gallery['name']).strip()
    gallery['description'] = request.form.get('description', '').strip()
    
    # Mettre à jour la date
    new_date = request.form.get('date')
    if new_date:
        gallery['date'] = new_date
        gallery['formatted_date'] = format_date(new_date)
    
    try:
        save_gallery_data(galleries)
        flash('Galerie mise à jour avec succès')
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde: {str(e)}")
        flash('Erreur lors de la sauvegarde des modifications')
    
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/gallery/<gallery_id>/delete', methods=['POST'])
def delete_gallery(gallery_id):
    if not app.config['DEV_MODE']:
        abort(403)  # Forbidden in production mode
        
    galleries = load_gallery_data()
    if gallery_id in galleries:
        # Supprimer la galerie des données
        del galleries[gallery_id]
        save_gallery_data(galleries)
        flash('Galerie supprimée avec succès', 'success')
    else:
        flash('Galerie non trouvée', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
