from flask import Flask, render_template, request, redirect, url_for, flash, abort
import json
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)
app.config['DEV_MODE'] = os.getenv('DEV_MODE', 'False').lower() == 'true'  # Par défaut False
app.secret_key = 'votre_clé_secrète_ici'

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
    return render_template('gallery.html', gallery=gallery, dev_mode=app.config['DEV_MODE'])

@app.route('/<int:year>/<int:month>')
def month_galleries(year, month):
    try:
        app.logger.info(f"Accessing month_galleries for {month}/{year}")
        
        with open('galleries.json', 'r', encoding='utf-8') as f:
            galleries = json.load(f)
        
        app.logger.info(f"Loaded galleries: {len(galleries)} found")
        
        # Filtrer les galeries pour ce mois
        month_galleries = []
        background_image = None
        
        for gallery_id, gallery in galleries.items():
            app.logger.debug(f"Processing gallery {gallery_id}: {gallery.get('date')}")
            gallery_date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if gallery_date.year == year and gallery_date.month == month:
                gallery = gallery.copy()  # Create a copy to avoid modifying the original
                gallery['id'] = gallery_id
                month_galleries.append(gallery)
                # Utiliser la première photo de la première galerie comme fond d'écran
                if not background_image and gallery.get('photos'):
                    background_image = gallery['photos'][0]['url']
        
        app.logger.info(f"Found {len(month_galleries)} galleries for {month}/{year}")
        
        if not month_galleries:
            app.logger.warning(f"No galleries found for {month}/{year}")
            abort(404)
        
        # Trier les galeries par date
        month_galleries.sort(key=lambda x: x['date'], reverse=True)
        
        # S'assurer que month est un entier valide entre 1 et 12
        if not (1 <= month <= 12):
            app.logger.error(f"Invalid month value: {month}")
            abort(404)
            
        month_name = f"{MOIS_FR[month-1]} {year}"
        app.logger.info(f"Rendering template with month_name: {month_name}")
        
        return render_template('month.html', 
                             month=month_name,
                             galleries=month_galleries,
                             background_image=background_image)
                             
    except Exception as e:
        app.logger.error(f"Error in month_galleries: {str(e)}")
        app.logger.exception("Full traceback:")
        abort(500)

@app.route('/upload_photos/<gallery_id>', methods=['POST'])
def upload_photos(gallery_id):
    if 'photos' not in request.files:
        flash('Aucune photo sélectionnée')
        return redirect(url_for('gallery', gallery_id=gallery_id))
    
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        flash('Galerie non trouvée')
        return redirect(url_for('index'))
    
    gallery = galleries[gallery_id]
    if 'photos' not in gallery:
        gallery['photos'] = []
    
    files = request.files.getlist('photos')
    
    for file in files:
        if file.filename:
            try:
                # Upload to Cloudinary
                result = cloudinary.uploader.upload(file)
                gallery['photos'].append({
                    'url': result['secure_url'],
                    'filename': file.filename
                })
            except Exception as e:
                flash(f'Erreur lors du téléchargement de {file.filename}: {str(e)}')
                continue
    
    save_gallery_data(galleries)
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/create_gallery', methods=['POST'])
def create_gallery():
    name = request.form.get('name', '').strip()
    date = request.form.get('date', '').strip()
    description = request.form.get('description', '').strip()
    
    if not name or not date:
        flash('Le nom et la date sont requis')
        return redirect(url_for('index'))
    
    try:
        # Valider le format de la date
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        flash('Format de date invalide')
        return redirect(url_for('index'))
    
    # Créer un ID unique basé sur la date et l'heure
    gallery_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    galleries = load_gallery_data()
    
    # Créer la nouvelle galerie
    galleries[gallery_id] = {
        'name': name,
        'date': date,
        'formatted_date': format_date(date),
        'description': description,
        'photos': []
    }
    
    # Gérer l'upload de l'image de couverture
    if 'cover_image' in request.files:
        cover_file = request.files['cover_image']
        if cover_file.filename:
            try:
                # Upload to Cloudinary
                result = cloudinary.uploader.upload(cover_file)
                galleries[gallery_id]['cover_image'] = result['secure_url']
            except Exception as e:
                flash(f'Erreur lors du téléchargement de l\'image de couverture: {str(e)}')
    
    save_gallery_data(galleries)
    return redirect(url_for('gallery', gallery_id=gallery_id))

if __name__ == '__main__':
    app.run(debug=True)
