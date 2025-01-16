from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
import json
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv
import logging
import uuid
import re

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

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_gallery_data(data):
    with open('galleries.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_gallery_data():
    try:
        with open('galleries.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def load_projects():
    try:
        with open('projects.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_projects(projects):
    with open('projects.json', 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=4)

def format_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{date.day} {MOIS_FR[date.month-1]} {date.year}"

def sort_galleries_by_date(galleries):
    # Convert galleries dict to list and add date object for sorting
    gallery_list = []
    for gallery_id, gallery in galleries.items():
        gallery['id'] = gallery_id
        gallery['date_obj'] = datetime.strptime(gallery['date'], '%Y-%m-%d')
        gallery_list.append(gallery)
    
    # Sort galleries by date
    return sorted(gallery_list, key=lambda x: x['date_obj'])

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/index')
def index():
    galleries = load_gallery_data()
    
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        date = datetime.strptime(gallery['date'], '%Y-%m-%d')
        if date.year == 2024:  # Filtrer uniquement les galeries de 2024
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
            
            gallery['id'] = gallery_id
            galleries_by_month[month_key]['galleries'].append(gallery)
            
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
    
    # Déterminer la page de retour en fonction de l'année
    date = datetime.strptime(gallery['date'], '%Y-%m-%d')
    return_page = 'future' if date.year == 2025 else 'index'
    
    # Ajouter l'ID à l'objet gallery
    gallery['id'] = gallery_id
    return render_template('gallery.html', 
                         gallery=gallery, 
                         dev_mode=app.config['DEV_MODE'],
                         format_date=format_date,
                         return_page=return_page)

@app.route('/month/<int:year>/<int:month>')
def month_galleries(year, month):
    galleries = load_gallery_data()
    month_galleries = []
    month_name = MOIS_FR[month-1]
    
    app.logger.info(f"Recherche des galeries pour {month_name} {year}")
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == year and date.month == month:
                gallery['id'] = gallery_id
                gallery['formatted_date'] = format_date(gallery['date'])
                month_galleries.append(gallery)
                app.logger.info(f"Galerie trouvée: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Récupérer l'image de fond de la première galerie
    background_image = month_galleries[0]['cover_image'] if month_galleries else None
    
    return render_template('month.html',
                         galleries=month_galleries,
                         month=f"{month_name} {year}",  # Titre formaté
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
    if not app.config['DEV_MODE']:
        abort(403)  # Forbidden in production mode
        
    name = request.form.get('name')
    date = request.form.get('date')
    description = request.form.get('description')
    
    # Vérifier l'année de la date pour rediriger vers la bonne page
    year = datetime.strptime(date, '%Y-%m-%d').year
    return_route = 'index'  # par défaut pour 2024
    
    if year == 2021:
        return_route = 'year_2021'
    elif year == 2022:
        return_route = 'year_2022'
    elif year == 2023:
        return_route = 'bestof'
    elif year == 2025:
        return_route = 'future'
    
    # Création d'un ID unique pour la galerie
    gallery_id = str(uuid.uuid4())
    
    # Chargement des données existantes
    galleries = load_gallery_data()
    
    # Création de la nouvelle galerie
    new_gallery = {
        'name': name,
        'date': date,
        'description': description,
        'photos': [],
        'cover_image': None
    }
    
    # Gestion de l'image de couverture
    if 'cover_image' in request.files:
        cover_file = request.files['cover_image']
        if cover_file and allowed_file(cover_file.filename):
            try:
                # Upload vers Cloudinary
                upload_result = cloudinary.uploader.upload(cover_file)
                new_gallery['cover_image'] = upload_result['secure_url']
            except Exception as e:
                app.logger.error(f"Erreur lors de l'upload Cloudinary: {str(e)}")
                flash("Erreur lors de l'upload de l'image de couverture", 'error')
    
    # Ajout de la nouvelle galerie
    galleries[gallery_id] = new_gallery
    save_gallery_data(galleries)
    
    flash('Galerie créée avec succès', 'success')
    return redirect(url_for(return_route))

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

@app.route('/years')
def years():
    return render_template('years.html')

@app.route('/future')
def future():
    galleries = load_gallery_data()
    galleries_by_month = {}
    today = datetime.now()
    
    for gallery_id, gallery in galleries.items():
        date = datetime.strptime(gallery['date'], '%Y-%m-%d')
        if date.year == 2025:
            month_key = f"{MOIS_FR[date.month-1]} {date.year}"
            month_num = date.strftime('%m')
            year = date.strftime('%Y')
            
            if month_key not in galleries_by_month:
                galleries_by_month[month_key] = {
                    'galleries': [],
                    'month': int(month_num),
                    'year': int(year),
                    'cover': None,
                    'is_future': date > today  # Ajouter un indicateur pour les dates futures
                }
            
            gallery['id'] = gallery_id
            gallery['is_future'] = date > today  # Ajouter l'indicateur à chaque galerie
            galleries_by_month[month_key]['galleries'].append(gallery)
            
            if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                galleries_by_month[month_key]['cover'] = gallery['cover_image']
    
    return render_template('future.html', 
                         galleries_by_month=galleries_by_month,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/bestof')
def bestof():
    galleries = load_gallery_data()
    galleries_by_month = {}
    background_image = None
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2023:
                month_key = f"{MOIS_FR[date.month-1]} {date.year}"
                month_num = date.strftime('%m')
                year = date.strftime('%Y')
                
                # Chercher la photo de fond dans le mois d'août
                if date.month == 8 and not background_image and gallery.get('cover_image'):
                    background_image = gallery['cover_image']
                
                if month_key not in galleries_by_month:
                    galleries_by_month[month_key] = {
                        'galleries': [],
                        'month': int(month_num),
                        'year': int(year),
                        'cover': None
                    }
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    return render_template('bestof.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/gallery/<gallery_id>/delete_photo/<int:photo_index>', methods=['POST'])
def delete_photo(gallery_id, photo_index):
    if not app.config['DEV_MODE']:
        abort(403)  # Forbidden in production mode
        
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        flash('Galerie non trouvée', 'error')
        return redirect(url_for('index'))
    
    gallery = galleries[gallery_id]
    if 'photos' in gallery and 0 <= photo_index < len(gallery['photos']):
        # Supprimer la photo
        deleted_photo = gallery['photos'].pop(photo_index)
        save_gallery_data(galleries)
        flash('Photo supprimée avec succès', 'success')
    else:
        flash('Photo non trouvée', 'error')
    
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/2021')
def year_2021():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    app.logger.info("=== Début du traitement des galeries 2021 ===")
    app.logger.info(f"Nombre total de galeries chargées: {len(galleries)}")
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            app.logger.info(f"Traitement de la galerie {gallery_id}: date = {date}")
            
            if date.year == 2021:
                month_key = f"{MOIS_FR[date.month-1]} {date.year}"
                month_num = date.strftime('%m')
                year = date.strftime('%Y')
                
                app.logger.info(f"Galerie de 2021 trouvée: {gallery['name']} pour le mois {month_key}")
                
                if month_key not in galleries_by_month:
                    galleries_by_month[month_key] = {
                        'galleries': [],
                        'month': int(month_num),
                        'year': int(year),
                        'cover': None
                    }
                    app.logger.info(f"Création du mois {month_key}")
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                # Mettre à jour l'image de couverture si c'est la première galerie du mois
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                    app.logger.info(f"Image de couverture définie pour {month_key}: {gallery['cover_image']}")
                
                app.logger.info(f"Galerie ajoutée pour 2021: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
    
    app.logger.info(f"=== Résumé du traitement ===")
    app.logger.info(f"Nombre de mois trouvés: {len(galleries_by_month)}")
    for month_key, data in galleries_by_month.items():
        app.logger.info(f"Mois {month_key}: {len(data['galleries'])} galeries")
    
    # Trouver la première image de couverture disponible
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                app.logger.info(f"Image de fond trouvée: {background_image}")
                break
    
    app.logger.info("=== Fin du traitement des galeries 2021 ===")
    
    return render_template('year2021.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2022')
def year_2022():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2022:
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
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                # Mettre à jour l'image de couverture si c'est la première galerie du mois
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                
                app.logger.info(f"Galerie ajoutée pour 2022: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Trouver la première image de couverture disponible
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                break
    
    return render_template('year2022.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/debug_galleries')
def debug_galleries():
    if app.config['DEV_MODE']:
        galleries = load_gallery_data()
        return jsonify(galleries)
    return "Debug mode only", 403

@app.route('/debug_2021')
def debug_2021():
    if app.config['DEV_MODE']:
        galleries = load_gallery_data()
        galleries_2021 = {}
        
        for gallery_id, gallery in galleries.items():
            try:
                date = datetime.strptime(gallery['date'], '%Y-%m-%d')
                if date.year == 2021:
                    galleries_2021[gallery_id] = gallery
            except Exception as e:
                app.logger.error(f"Erreur avec la galerie {gallery_id}: {str(e)}")
        
        return jsonify({
            'total_galleries': len(galleries),
            'galleries_2021': galleries_2021,
            'count_2021': len(galleries_2021)
        })
    return "Debug mode only", 403

@app.route('/2020')
def year_2020():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2020:
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
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                # Mettre à jour l'image de couverture si c'est la première galerie du mois
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                
                app.logger.info(f"Galerie ajoutée pour 2020: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Trouver la première image de couverture disponible
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                break
    
    return render_template('year2020.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2019')
def year2019():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2019:
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
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Trouver la première image de couverture disponible
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                break
    
    return render_template('year2019.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2018')
def year2018():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2018:
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
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                break
    
    return render_template('year2018.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2017')
def year2017():
    galleries = load_gallery_data()
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2017:
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
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    background_image = None
    if galleries_by_month:
        for month_data in galleries_by_month.values():
            if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                background_image = month_data['galleries'][0]['cover_image']
                break
    
    return render_template('year2017.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/memories')
def memories():
    # Charger les projets
    photos = load_projects()
    app.logger.info(f"Nombre de projets chargés : {len(photos)}")
    
    # Trier les projets par date
    photos.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
    
    return render_template('memories.html',
                         photos=photos,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/dreams')
def dreams():
    # Charger les projets
    photos = load_projects()
    app.logger.info(f"Nombre de projets chargés : {len(photos)}")
    
    # Trier les projets par date
    photos.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
    
    return render_template('dreams.html',
                         photos=photos,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/add_project', methods=['POST'])
def add_project():
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        data = request.form
        file = request.files['cover_image']
        
        if file:
            upload_result = cloudinary.uploader.upload(file)
            image_url = upload_result['secure_url']
            
            new_project = {
                'id': str(uuid.uuid4()),
                'url': image_url,
                'gallery_name': data['title'],
                'date': data['date'],
                'formatted_date': format_date(data['date']),
                'description': data['description']
            }
            
            projects = load_projects()
            projects.append(new_project)
            save_projects(projects)
            
        return redirect(url_for('memories'))
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'ajout du projet: {str(e)}")
        flash("Erreur lors de l'ajout du projet")
        return redirect(url_for('memories'))

@app.route('/edit_project/<project_id>', methods=['POST'])
def edit_project(project_id):
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        data = request.form
        projects = load_projects()
        
        project = next((p for p in projects if p['id'] == project_id), None)
        if not project:
            return abort(404)
        
        project['gallery_name'] = data['title']
        project['date'] = data['date']
        project['formatted_date'] = format_date(data['date'])
        project['description'] = data['description']
        
        if 'cover_image' in request.files and request.files['cover_image'].filename:
            file = request.files['cover_image']
            upload_result = cloudinary.uploader.upload(file)
            project['url'] = upload_result['secure_url']
        
        save_projects(projects)
        return redirect(url_for('memories'))
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la modification du projet: {str(e)}")
        flash("Erreur lors de la modification du projet")
        return redirect(url_for('memories'))

@app.route('/delete_project/<project_id>', methods=['POST'])
def delete_project(project_id):
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        projects = load_projects()
        projects = [p for p in projects if p['id'] != project_id]
        save_projects(projects)
        flash("Projet supprimé avec succès")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la suppression du projet: {str(e)}")
        flash("Erreur lors de la suppression du projet")
    
    return redirect(url_for('memories'))

@app.route('/memories-of-centuries')
def memories_of_centuries():
    # Charger les photos depuis le fichier JSON dédié
    try:
        with open('century_memories.json', 'r', encoding='utf-8') as f:
            memories = json.load(f)
    except FileNotFoundError:
        memories = {}
    
    return render_template('memories_shuffle.html', 
                         memories=memories,
                         current_year=datetime.now().year,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/add-century-memory', methods=['POST'])
def add_century_memory():
    if 'photo' not in request.files:
        flash('Aucune photo sélectionnée')
        return redirect(url_for('memories_of_centuries'))
    
    photo = request.files['photo']
    if photo.filename == '':
        flash('Aucune photo sélectionnée')
        return redirect(url_for('memories_of_centuries'))
    
    if not allowed_file(photo.filename):
        flash('Type de fichier non autorisé')
        return redirect(url_for('memories_of_centuries'))
    
    try:
        # Upload de la photo sur Cloudinary
        upload_result = cloudinary.uploader.upload(photo)
        
        # Récupérer les données existantes
        try:
            with open('century_memories.json', 'r', encoding='utf-8') as f:
                memories = json.load(f)
        except FileNotFoundError:
            memories = {}
        
        # Créer une nouvelle entrée
        memory_id = str(uuid.uuid4())
        year = request.form.get('year', datetime.now().year)
        
        if str(year) not in memories:
            memories[str(year)] = []
            
        new_memory = {
            'id': memory_id,
            'url': upload_result['secure_url'],
            'title': request.form.get('title', ''),
            'description': request.form.get('description', ''),
            'year': str(year)
        }
        
        memories[str(year)].append(new_memory)
        
        # Sauvegarder les données
        with open('century_memories.json', 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=4)
            
        flash('Photo ajoutée avec succès')
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'ajout de la photo : {str(e)}")
        flash('Une erreur est survenue lors de l\'ajout de la photo')
    
    return redirect(url_for('memories_of_centuries'))

@app.route('/edit-century-memory/<memory_id>', methods=['POST'])
def edit_century_memory(memory_id):
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        with open('century_memories.json', 'r', encoding='utf-8') as f:
            memories = json.load(f)
        
        # Trouver et mettre à jour le souvenir
        for year in memories.values():
            for memory in year:
                if memory['id'] == memory_id:
                    memory['title'] = request.form['title']
                    memory['year'] = request.form['year']
                    memory['description'] = request.form['description']
                    
                    if 'photo' in request.files and request.files['photo'].filename:
                        file = request.files['photo']
                        upload_result = cloudinary.uploader.upload(file)
                        memory['url'] = upload_result['secure_url']
                    
                    break
        
        with open('century_memories.json', 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=4)
            
        return redirect(url_for('memories_of_centuries'))
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la modification du souvenir: {str(e)}")
        flash("Erreur lors de la modification du souvenir")
        return redirect(url_for('memories_of_centuries'))

@app.route('/delete-century-memory/<memory_id>', methods=['POST'])
def delete_century_memory(memory_id):
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        with open('century_memories.json', 'r', encoding='utf-8') as f:
            memories = json.load(f)
        
        # Supprimer le souvenir
        for year in memories:
            memories[year] = [m for m in memories[year] if m['id'] != memory_id]
            
        # Supprimer les années vides
        memories = {k: v for k, v in memories.items() if v}
        
        with open('century_memories.json', 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=4)
            
        return '', 204
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la suppression du souvenir: {str(e)}")
        return 'Erreur lors de la suppression', 500

@app.route('/memories-shuffle')
def memories_shuffle():
    try:
        with open('century_memories.json', 'r', encoding='utf-8') as f:
            memories = json.load(f)
    except FileNotFoundError:
        memories = {}
    
    # Aplatir toutes les photos en une seule liste
    all_photos = []
    for year_photos in memories.values():
        all_photos.extend(year_photos)
    
    return render_template('memories_pile.html', 
                         photos=all_photos,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/memories-pile')
def memories_pile():
    try:
        with open('century_memories.json', 'r', encoding='utf-8') as f:
            memories = json.load(f)
        
        # Créer une liste de toutes les photos
        all_memories = []
        for year, year_memories in memories.items():
            if year != "1900":  # Exclure l'année 1900
                for memory in year_memories:
                    if int(year) <= 2016:  # Filtrer jusqu'à 2016
                        all_memories.append(memory)
        
        return render_template('memories_pile.html', 
                             photos=all_memories,
                             dev_mode=app.config['DEV_MODE'])
    except Exception as e:
        app.logger.error(f"Erreur: {str(e)}")
        return render_template('memories_pile.html', photos=[], dev_mode=app.config['DEV_MODE'])

@app.route('/bouquetin')
def bouquetin():
    return render_template('bouquetin.html')

if __name__ == '__main__':
    app.run(debug=True)
