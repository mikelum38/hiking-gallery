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

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

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

def load_flowers_data():
    try:
        with open('mountain_flowers.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_flowers_data(data):
    with open('mountain_flowers.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_animals_data():
    try:
        with open('mountain_animals.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('animals', [])
    except FileNotFoundError:
        return []

def save_animals_data(animals):
    with open('mountain_animals.json', 'w', encoding='utf-8') as f:
        json.dump({'animals': animals}, f, ensure_ascii=False, indent=4)

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

@app.route('/2024')
def year_2024():
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
    
    return render_template('2024.html', 
                         galleries_by_month=galleries_by_month,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/gallery/<gallery_id>')
def gallery(gallery_id):
    galleries = load_gallery_data()
    gallery = galleries.get(gallery_id)
    if not gallery:
        return "Gallery not found", 404
    
    # Special case for GR20 gallery
    if gallery_id == "20240905_gr20":
        return render_template('gallery_gr20.html', 
                             gallery=gallery,
                             dev_mode=app.config['DEV_MODE'],
                             format_date=format_date)
    
    # Déterminer la page de retour en fonction de l'année
    date = datetime.strptime(gallery['date'], '%Y-%m-%d')
    year = date.year
    if year == 2025:
        return_page = 'year_2025'
    elif year == 2016:
        return_page = 'year_2016'
    elif year == 2017:
        return_page = 'year_2017'
    elif year == 2018:
        return_page = 'year_2018'
    elif year == 2019:
        return_page = 'year_2019'
    elif year == 2020:
        return_page = 'year_2020'
    elif year == 2021:
        return_page = 'year_2021'
    elif year == 2022:
        return_page = 'year_2022'
    elif year == 2023:
        return_page = 'year_2023'
    else:
        return_page = 'year_2024'
    
    # Ajouter l'ID à l'objet gallery
    gallery['id'] = gallery_id
    
    # Ajouter formatted_date s'il n'existe pas
    if 'formatted_date' not in gallery:
        date_obj = datetime.strptime(gallery['date'], '%Y-%m-%d')
        day = str(date_obj.day).lstrip('0')  # Enlever le zéro initial
        gallery['formatted_date'] = f"{day} {date_obj.strftime('%B %Y')}"
    
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
        return redirect(url_for('years'))
    
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
    return_route = 'year_2024'  # par défaut pour 2024
    
    if year == 2021:
        return_route = 'year_2021'
    elif year == 2022:
        return_route = 'year_2022'
    elif year == 2023:
        return_route = 'year_2023'
    elif year == 2025:
        return_route = 'year_2025'
    elif year == 2020:
        return_route = 'year_2020'
    elif year == 2019:
        return_route = 'year_2019'
    elif year == 2018:
        return_route = 'year_2018'
    elif year == 2017:
        return_route = 'year_2017'
    elif year == 2016:
        return_route = 'year_2016'
    
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
        return redirect(url_for('2024'))
    
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
    
    return redirect(url_for('2024'))

@app.route('/years')
def years():
    return render_template('years.html', dev_mode=app.config['DEV_MODE'])

@app.route('/2025')
def year_2025():
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
            galleries_by_month[month_key]['galleries'].append(gallery)
            
            if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                galleries_by_month[month_key]['cover'] = gallery['cover_image']
    
    return render_template('2025.html', 
                         galleries_by_month=galleries_by_month,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2023')
def year_2023():
    try:
        galleries = load_gallery_data()
        galleries_by_month = {}
        
        for gallery_id, gallery in galleries.items():
            try:
                date = datetime.strptime(gallery['date'], '%Y-%m-%d')
                if date.year == 2023:
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
                    
                    app.logger.info(f"Galerie ajoutée pour 2023: {gallery['name']}")
            except Exception as e:
                app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
        
        # Trouver la première image de couverture disponible
        background_image = None
        if galleries_by_month:
            for month_data in galleries_by_month.values():
                if month_data['galleries'] and month_data['galleries'][0].get('cover_image'):
                    background_image = month_data['galleries'][0]['cover_image']
                    break
        
        return render_template('2023.html', 
                             galleries_by_month=galleries_by_month,
                             background_image=background_image,
                             dev_mode=app.config['DEV_MODE'])
    except Exception as e:
        app.logger.error(f"Error in 2023 route: {str(e)}")
        return redirect(url_for('years'))

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
    
    return render_template('2021.html', 
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
    
    return render_template('2022.html', 
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
    
    return render_template('2020.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2019')
def year_2019():
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
    
    return render_template('2019.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2018')
def year_2018():
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
    
    return render_template('2018.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/2017')
def year_2017():
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
    
    return render_template('2017.html', 
                         galleries_by_month=galleries_by_month,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/projets')
def projets():
    try:
        # Charger les projets
        photos = load_projects()
        app.logger.info(f"Nombre de projets chargés : {len(photos)}")
        
        # Debug: afficher le contenu des projets
        app.logger.info("Contenu des projets :")
        for photo in photos:
            app.logger.info(f"Projet: {photo}")
        
        # Trier les projets par date
        photos.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))
        
        return render_template('projets.html',
                             photos=photos,
                             dev_mode=app.config['DEV_MODE'])
    except Exception as e:
        app.logger.error(f"Erreur dans la route /projets : {str(e)}")
        flash("Une erreur s'est produite lors du chargement des projets")
        return redirect(url_for('year_2025'))

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
            
        return redirect(url_for('projets'))
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'ajout du projet: {str(e)}")
        flash("Erreur lors de l'ajout du projet")
        return redirect(url_for('projets'))

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
        return redirect(url_for('projets'))
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la modification du projet: {str(e)}")
        flash('Erreur lors de la modification du projet')
        return redirect(url_for('projets'))

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
    
    return redirect(url_for('projets'))

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

@app.route('/mountain_flowers')
def mountain_flowers():
    flowers = load_flowers_data()
    return render_template('mountain_flowers.html', flowers=flowers, dev_mode=app.config['DEV_MODE'])

@app.route('/add_flower', methods=['POST'])
def add_flower():
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Not allowed in production mode'}), 403

    if 'image' not in request.files:
        return jsonify({'error': 'No image file'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    try:
        # Upload de l'image à Cloudinary
        upload_result = cloudinary.uploader.upload(file)
        
        new_flower = {
            'id': str(uuid.uuid4()),
            'name': request.form.get('name'),
            'description': request.form.get('description'),
            'image_url': upload_result['secure_url'],
            'thumbnail_url': cloudinary.utils.cloudinary_url(upload_result['public_id'], 
                                                           width=300, 
                                                           height=200, 
                                                           crop='fill')[0],
            'date_added': datetime.now().isoformat()
        }
        
        flowers = load_flowers_data()
        flowers.append(new_flower)
        save_flowers_data(flowers)
        
        return jsonify(new_flower), 201
        
    except Exception as e:
        app.logger.error(f"Error adding flower: {str(e)}")
        return jsonify({'error': 'Failed to add flower'}), 500

@app.route('/get_flower/<flower_id>')
def get_flower(flower_id):
    flowers = load_flowers_data()
    flower = next((f for f in flowers if f['id'] == flower_id), None)
    if flower:
        return jsonify(flower)
    return jsonify({'error': 'Flower not found'}), 404

@app.route('/edit_flower', methods=['POST'])
def edit_flower():
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Not allowed in production mode'}), 403

    flowers = load_flowers_data()
    flower_id = request.form.get('id')
    flower_index = next((i for i, f in enumerate(flowers) if f['id'] == flower_id), None)

    if flower_index is None:
        return jsonify({'error': 'Flower not found'}), 404

    try:
        flower = flowers[flower_index]
        flower['name'] = request.form.get('name')
        flower['description'] = request.form.get('description')

        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            if not allowed_file(file.filename):
                return jsonify({'error': 'File type not allowed'}), 400

            # Upload de la nouvelle image à Cloudinary
            upload_result = cloudinary.uploader.upload(file)
            flower['image_url'] = upload_result['secure_url']
            flower['thumbnail_url'] = cloudinary.utils.cloudinary_url(upload_result['public_id'], 
                                                                    width=300, 
                                                                    height=200, 
                                                                    crop='fill')[0]

        save_flowers_data(flowers)
        flower['position'] = flower_index + 1
        return jsonify(flower), 200

    except Exception as e:
        app.logger.error(f"Error editing flower: {str(e)}")
        return jsonify({'error': 'Failed to edit flower'}), 500

@app.route('/delete_flower/<flower_id>', methods=['POST'])
def delete_flower(flower_id):
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Not allowed in production mode'}), 403

    flowers = load_flowers_data()
    flower_index = next((i for i, f in enumerate(flowers) if f['id'] == flower_id), None)

    if flower_index is None:
        return jsonify({'error': 'Flower not found'}), 404

    try:
        # Supprimer la fleur de la liste
        flowers.pop(flower_index)
        save_flowers_data(flowers)
        
        return jsonify({'success': True, 'position': flower_index + 1}), 200

    except Exception as e:
        app.logger.error(f"Error deleting flower: {str(e)}")
        return jsonify({'error': 'Failed to delete flower'}), 500

@app.route('/mountain_animals')
def mountain_animals():
    animals = load_animals_data()
    return render_template('mountain_animals.html', animals=animals, dev_mode=app.config['DEV_MODE'])

@app.route('/add_animal', methods=['POST'])
def add_animal():
    app.logger.info("Début de l'ajout d'un animal")
    
    if not app.config['DEV_MODE']:
        app.logger.warning("Tentative d'ajout en mode production")
        return jsonify({'error': 'Not allowed in production mode'}), 403

    if 'image' not in request.files:
        app.logger.error("Pas de fichier image dans la requête")
        return jsonify({'error': 'No image file'}), 400
    
    file = request.files['image']
    app.logger.info(f"Fichier reçu: {file.filename}")
    
    if file.filename == '':
        app.logger.error("Nom de fichier vide")
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        app.logger.error(f"Type de fichier non autorisé: {file.filename}")
        return jsonify({'error': 'File type not allowed'}), 400

    try:
        app.logger.info("Tentative d'upload vers Cloudinary")
        # Upload de l'image à Cloudinary
        upload_result = cloudinary.uploader.upload(file)
        app.logger.info(f"Upload Cloudinary réussi: {upload_result['secure_url']}")
        
        new_animal = {
            'id': str(uuid.uuid4()),
            'name': request.form.get('name'),
            'description': request.form.get('description'),
            'image_url': upload_result['secure_url'],
            'thumbnail_url': cloudinary.utils.cloudinary_url(upload_result['public_id'], 
                                                     width=300, 
                                                     height=200, 
                                                     crop='fill')[0],
            'date_added': datetime.now().isoformat()
        }
        
        app.logger.info(f"Nouvel animal créé: {new_animal}")
        
        animals = load_animals_data()
        app.logger.info(f"Nombre d'animaux avant ajout: {len(animals)}")
        animals.append(new_animal)
        save_animals_data(animals)
        app.logger.info(f"Nombre d'animaux après ajout: {len(animals)}")
        
        return jsonify(new_animal)
        
    except Exception as e:
        app.logger.error(f"Error adding animal: {str(e)}")
        return jsonify({'error': f'Failed to add animal: {str(e)}'}), 500

@app.route('/edit_animal/<animal_id>', methods=['POST'])
def edit_animal(animal_id):
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Not allowed in production mode'}), 403

    animals = load_animals_data()
    animal_index = next((i for i, a in enumerate(animals) if a['id'] == animal_id), None)

    if animal_index is None:
        return jsonify({'error': 'Animal not found'}), 404

    try:
        animal = animals[animal_index]
        animal['name'] = request.form.get('name')
        animal['description'] = request.form.get('description')

        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            if not allowed_file(file.filename):
                return jsonify({'error': 'File type not allowed'}), 400

            # Upload de la nouvelle image à Cloudinary
            upload_result = cloudinary.uploader.upload(file)
            animal['image_url'] = upload_result['secure_url']
            animal['thumbnail_url'] = cloudinary.utils.cloudinary_url(upload_result['public_id'], 
                                                              width=300, 
                                                              height=200, 
                                                              crop='fill')[0]

        save_animals_data(animals)
        return jsonify(animal)
        
    except Exception as e:
        app.logger.error(f"Error editing animal: {str(e)}")
        return jsonify({'error': 'Failed to edit animal'}), 500

@app.route('/api/animals/<animal_id>', methods=['DELETE'])
def delete_animal(animal_id):
    try:
        animals = load_animals_data()
        animal_index = next((i for i, a in enumerate(animals) if a['id'] == animal_id), None)

        if animal_index is None:
            return jsonify({'error': 'Animal not found'}), 404

        del animals[animal_index]
        save_animals_data(animals)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error deleting animal: {str(e)}")
        return jsonify({'error': 'Failed to delete animal'}), 500

@app.route('/2016')
def year_2016():
    galleries = load_gallery_data()
    galleries_by_month = {}
    background_image = None
    
    # Dictionnaire de traduction des mois
    month_translations = {
        'January': 'Janvier',
        'February': 'Février',
        'March': 'Mars',
        'April': 'Avril',
        'May': 'Mai',
        'June': 'Juin',
        'July': 'Juillet',
        'August': 'Août',
        'September': 'Septembre',
        'October': 'Octobre',
        'November': 'Novembre',
        'December': 'Décembre'
    }
    
    for gallery_id, gallery in galleries.items():
        date = datetime.strptime(gallery['date'], '%Y-%m-%d')
        if date.year == 2016:
            month_name = date.strftime('%B')  # Nom du mois en anglais
            french_month = month_translations[month_name]  # Traduction en français
            if french_month not in galleries_by_month:
                galleries_by_month[french_month] = {
                    'year': date.year,
                    'month': date.month,
                    'cover': None
                }
            if gallery.get('cover_image'):
                if not galleries_by_month[french_month]['cover']:
                    galleries_by_month[french_month]['cover'] = gallery['cover_image']
                if not background_image:
                    background_image = gallery['cover_image']

    # Traduire les noms des mois en français
    french_months = {}
    for month in galleries_by_month:
        french_months[month] = galleries_by_month[month]

    return render_template('2016.html', 
                         galleries_by_month=french_months,
                         background_image=background_image,
                         dev_mode=app.config['DEV_MODE'])

@app.route('/in_my_life')
def in_my_life():
    return redirect(url_for('inmy_landing'))

@app.route('/wheel-of-fortune')
def wheel_of_fortune():
    return render_template('wheel_of_fortune.html', dev_mode=app.config['DEV_MODE'])

@app.route('/inmy')
def inmy_landing():
    if request.args.get('back') == 'true':
        return redirect(url_for('years'))
    return render_template('inmy_cover.html')

@app.route('/inmy/life')
def inmy_life():
    page = request.args.get('page', 1, type=int)
    total_pages = 4
    
    # Load texts from JSON file
    try:
        with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
            texts = json.load(f)
    except FileNotFoundError:
        texts = {}
    
    # Get text for current page
    text_key = str(page)
    page_text = texts.get(text_key, '')
    
    # Navigation URLs
    prev_url = url_for('inmy_landing') if page == 1 else url_for('inmy_life', page=page-1)
    next_url = url_for('inmy_life', page=page+1) if page < total_pages else None
    
    return render_template('inmy_life.html', 
                         page=page,
                         total_pages=total_pages,
                         prev_url=prev_url,
                         next_url=next_url,
                         dev_mode=app.config['DEV_MODE'],
                         **{f'text{page}': page_text})

@app.route('/save_inmy_life_text', methods=['POST'])
def save_inmy_life_text():
    try:
        data = request.get_json()
        page = data.get('page')
        text = data.get('text')
        
        if not page or text is None:
            return jsonify({'success': False, 'error': 'Page ou texte manquant'})
        
        # Charger le fichier JSON existant ou créer un nouveau
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                texts = json.load(f)
        except FileNotFoundError:
            texts = {}
        
        # Mettre à jour le texte pour la page
        texts[str(page)] = text
        
        # Sauvegarder dans le fichier
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(texts, f, ensure_ascii=False, indent=4)
        
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde du texte: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/inmy/back')
def inmy_back():
    return render_template('inmy_back_cover.html')

@app.route('/gallery/<gallery_id>/delete_photo/<int:photo_index>', methods=['POST'])
def delete_photo(gallery_id, photo_index):
    if not app.config['DEV_MODE']:
        return "Non autorisé", 403
        
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        flash('Galerie non trouvée')
        return redirect(url_for('years'))
        
    gallery = galleries[gallery_id]
    if 'photos' not in gallery or photo_index >= len(gallery['photos']):
        flash('Photo non trouvée')
        return redirect(url_for('gallery', gallery_id=gallery_id))
        
    # Supprimer la photo
    del gallery['photos'][photo_index]
    save_gallery_data(galleries)
    
    flash('Photo supprimée avec succès')
    return redirect(url_for('gallery', gallery_id=gallery_id))

if __name__ == '__main__':
    app.run(debug=True)
