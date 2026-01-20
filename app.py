# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, session
import json
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os
import cloudinary.api
from dotenv import load_dotenv
import logging
import uuid
import requests
from functools import lru_cache
import io
import traceback
from flask import send_file
from config import config, Config
from search import SearchEngine, setup_search_routes

# Initialiser Sentry si activé
if Config.ENABLE_SENTRY and Config.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.environ.get('FLASK_ENV', 'production')
    )


load_dotenv()  # Chargement des variables d'environnement depuis .env

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)

# Configuration de l'application
env = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[env])

# Initialiser le moteur de recherche
search_engine = SearchEngine('galleries.json')
app.logger.info(f"Moteur de recherche initialisé : {search_engine.get_stats()['total_galleries']} galeries indexées")
# Configuration des routes de recherche
setup_search_routes(app, search_engine)

# Initialiser Flask-Sentry si activé
if Config.ENABLE_SENTRY and Config.SENTRY_DSN:
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        environment=os.environ.get('FLASK_ENV', 'production')
    )

# Validation de la configuration
try:
    Config.validate_config()
except ValueError as e:
    app.logger.error(f"Erreur de configuration: {e}")
    raise

# Configuration du mode développement
app.config['DEV_MODE'] = app.config.get('DEV_MODE', False)

# Clé secrète obligatoire
app.secret_key = app.config['SECRET_KEY']
if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY doit être définie dans les variables d'environnement")
app.logger.setLevel(logging.INFO)

# Log du mode de l'application au démarrage
app.logger.info(f"Application running in {'DEVELOPMENT' if app.config['DEV_MODE'] else 'PRODUCTION'} mode")

# Configuration Cloudinary
cloudinary.config(
    cloud_name = app.config['CLOUDINARY_CLOUD_NAME'],
    api_key = app.config['CLOUDINARY_API_KEY'],
    api_secret = app.config['CLOUDINARY_API_SECRET']
)

# Liste des mois en français
MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

# Cache persistant pour les dimensions des photos
PHOTO_DIMENSIONS_CACHE_FILE = 'photo_dimensions_cache.json'

def load_photo_dimensions_cache():
    """Charger le cache des dimensions de photos"""
    try:
        with open(PHOTO_DIMENSIONS_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_photo_dimensions_cache(cache):
    """Sauvegarder le cache des dimensions de photos"""
    try:
        with open(PHOTO_DIMENSIONS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde du cache des dimensions: {e}")

def save_photo_dimensions_to_gallery(gallery_id, photo_id, width, height):
    """
    Sauvegarde les dimensions d'une photo dans le JSON de la galerie.
    Approche lazy loading : sauvegarde uniquement lors de la visualisation.
    Version optimisée et directe : modification ciblée du fichier.
    """
    try:
        # Déterminer l'année pour le fichier en utilisant la galerie directement
        # Pas besoin de charger toutes les galeries !
        year_file = None
        year_galleries = {}
        
        # Chercher dans quel fichier se trouve la galerie
        for year in range(2015, 2030):
            test_file = f"galleries_{year}.json"
            if os.path.exists(test_file):
                try:
                    with open(test_file, 'r', encoding='utf-8') as f:
                        test_galleries = json.load(f)
                        if gallery_id in test_galleries:
                            year_file = test_file
                            year_galleries = test_galleries
                            break
                except:
                    continue
        
        if not year_file:
            app.logger.error(f"Galerie {gallery_id} non trouvée dans aucun fichier")
            return
        
        # Mettre à jour la galerie dans ce fichier
        if gallery_id in year_galleries:
            # Trouver la photo et mettre à jour ses dimensions
            for photo in year_galleries[gallery_id].get('photos', []):
                current_photo_id = photo['url'].split('/')[-1].split('.')[0]
                if current_photo_id == photo_id:
                    photo['width'] = width
                    photo['height'] = height
                    break
            
            # Sauvegarder uniquement ce fichier
            with open(year_file, 'w', encoding='utf-8') as f:
                json.dump(year_galleries, f, ensure_ascii=False, indent=2)
            
            app.logger.info(f"✅ Dimensions sauvegardées pour {photo_id}: {width}x{height} dans {year_file}")
            
            # Plus besoin de vider le cache - les données sont toujours fraîches
        else:
            app.logger.error(f"Galerie {gallery_id} non trouvée dans {year_file}")
            
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde des dimensions pour {photo_id}: {e}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")

def get_photo_dimensions(photo_id):
    """
    Obtenir les dimensions d'une photo.
    OPTIMISATION: Les dimensions sont maintenant stockées directement dans galleries_YYYY.json
    Cette fonction n'est appelée que pour les photos sans dimensions (legacy).
    """
    try:
        # Appeler l'API Cloudinary (seulement pour les photos legacy)
        result = cloudinary.api.resource(photo_id)
        app.logger.info(f"Dimensions récupérées via API pour {photo_id}: {result['width']}x{result['height']}")
        return {
            'width': result['width'],
            'height': result['height']
        }
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des dimensions de {photo_id}: {e}")
        return {'width': 0, 'height': 0}


from werkzeug.utils import secure_filename

def validate_upload(file, max_size_mb=50):
    """Validation complète des fichiers uploadés"""
    if not file or not file.filename:
        return False, "Aucun fichier sélectionné", None
    
    # Taille maximale (50MB par défaut pour supporter 45 photos)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > max_size_mb * 1024 * 1024:
        return False, f"Fichier trop volumineux (max {max_size_mb}MB)", None
    
    # Sécurisation du nom de fichier
    filename = secure_filename(file.filename)
    if not filename:
        return False, "Nom de fichier invalide", None
    
    # Validation de l'extension
    if not allowed_file(filename):
        return False, "Type de fichier non autorisé", None
    
    # Validation du type MIME
    allowed_mimes = ['image/jpeg', 'image/png', 'image/gif']
    if file.content_type not in allowed_mimes:
        return False, f"Type MIME {file.content_type} non autorisé", None
    
    return True, filename, file

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_single_gallery_to_year(gallery_id, gallery_data):
    """
    Sauvegarde uniquement une galerie dans son fichier galleries_YYYY.json correspondant.
    Optimisé pour le lazy loading : ne sauvegarde que l'année concernée.
    """
    try:
        # Déterminer l'année de la galerie
        if 'year' in gallery_data:
            year = gallery_data['year']
        else:
            date = datetime.strptime(gallery_data['date'], '%Y-%m-%d')
            year = date.year
            gallery_data['year'] = year
            gallery_data['month'] = date.month
            gallery_data['day'] = date.day
        
        # Charger uniquement le fichier de l'année concernée
        year_file = f"galleries_{year}.json"
        year_galleries = {}
        
        if os.path.exists(year_file):
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
        
        # Mettre à jour uniquement cette galerie
        year_galleries[gallery_id] = gallery_data
        
        # Sauvegarder uniquement ce fichier
        with open(year_file, 'w', encoding='utf-8') as f:
            json.dump(year_galleries, f, ensure_ascii=False, indent=2)
        
        app.logger.info(f"✅ {year_file} mis à jour (1 galerie)")
        
        # Mettre à jour le cache
        clear_gallery_cache()
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde de {gallery_id}: {e}")

def save_gallery_data(data):
    """
    Sauvegarde les galeries dans les fichiers appropriés.
    OPTION B : Sauvegarde dans galleries_YYYY.json + galleries.json (backup)
    """
    # Organiser les galeries par année
    galleries_by_year = {}
    
    for gallery_id, gallery in data.items():
        try:
            # Utiliser la métadonnée 'year' si disponible, sinon parser la date
            if 'year' in gallery:
                year = gallery['year']
            else:
                date = datetime.strptime(gallery['date'], '%Y-%m-%d')
                year = date.year
                # Ajouter la métadonnée pour la prochaine fois
                gallery['year'] = year
                gallery['month'] = date.month
                gallery['day'] = date.day
            
            if year not in galleries_by_year:
                galleries_by_year[year] = {}
            
            galleries_by_year[year][gallery_id] = gallery
            
        except Exception as e:
            app.logger.error(f"Erreur lors de la classification de {gallery_id}: {e}")
            continue
    
    # Sauvegarder chaque année dans son propre fichier
    for year, galleries in galleries_by_year.items():
        year_file = f"galleries_{year}.json"
        with open(year_file, 'w', encoding='utf-8') as f:
            json.dump(galleries, f, ensure_ascii=False, indent=2)
        app.logger.info(f"✅ {year_file} sauvegardé ({len(galleries)} galeries)")
    
    # Sauvegarder aussi dans galleries.json (backup/compatibilité)
    with open('galleries.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    # Reconstruire l'index des galeries par année
    rebuild_galleries_index()
    
    # Mettre à jour les métadonnées
    update_galleries_metadata()
    
    # Mettre à jour l'index de recherche
    global search_engine
    search_engine = SearchEngine('galleries.json')
    app.logger.info("✅ Tous les fichiers sauvegardés et index mis à jour")

def load_gallery_data():
    """
    Charge les données des galeries depuis les fichiers JSON par année.
    Version optimisée : charge uniquement les fichiers nécessaires.
    """
    galleries = {}
    
    # Parcourir uniquement les fichiers galleries_YYYY.json existants
    for year_file in sorted([f for f in os.listdir('.') if f.startswith('galleries_') and f.endswith('.json') and f != 'galleries_index.json' and f != 'galleries_metadata.json' and f != 'galleries_by_year.json']):
        try:
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
                galleries.update(year_galleries)
                # Log seulement si le fichier contient des galeries
                if year_galleries:
                    app.logger.info(f"✅ Chargement OPTIMAL : {len(year_galleries)} galeries depuis {year_file}")
        except Exception as e:
            app.logger.error(f"Erreur lors du chargement de {year_file}: {e}")
    
    # Fallback vers galleries.json si aucun fichier trouvé
    if not galleries and os.path.exists('galleries.json'):
        try:
            with open('galleries.json', 'r', encoding='utf-8') as f:
                galleries = json.load(f)
                app.logger.info(f"✅ Fallback : Chargement depuis galleries.json")
        except Exception as e:
            app.logger.error(f"Erreur lors du chargement de galleries.json: {e}")
            return {}
    
    if galleries:
        app.logger.info(f"✅ Total chargé : {len(galleries)} galeries")
    return galleries

def load_gallery_data_for_year(year):
    """
    Charge uniquement les galeries d'une année spécifique.
    Version ultra-optimisée pour le lazy loading.
    """
    year_file = f"galleries_{year}.json"
    
    if os.path.exists(year_file):
        try:
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
                app.logger.info(f"✅ Chargement ULTRA-OPTIMAL : {len(year_galleries)} galeries depuis {year_file}")
                return year_galleries
        except Exception as e:
            app.logger.error(f"Erreur lors du chargement de {year_file}: {e}")
    
    return {}

def clear_gallery_cache():
    """Invalider le cache des galeries après modifications"""
    # Plus de cache à vider - les données sont toujours fraîches
    pass

def load_galleries_index():
    """Charge l'index des galeries par année"""
    try:
        with open('galleries_index.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        app.logger.warning("galleries_index.json non trouvé, création automatique...")
        # Créer l'index automatiquement si absent
        rebuild_galleries_index()
        return load_galleries_index()

def load_galleries_by_year():
    """Charge les galeries groupées par année"""
    try:
        with open('galleries_by_year.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        app.logger.warning("galleries_by_year.json non trouvé, création automatique...")
        # Créer le groupement automatiquement si absent
        galleries = load_gallery_data()
        by_year = {}
        for gallery_id, gallery in galleries.items():
            year = gallery.get('year', datetime.strptime(gallery['date'], '%Y-%m-%d').year)
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(gallery)
        
        with open('galleries_by_year.json', 'w', encoding='utf-8') as f:
            json.dump(by_year, f, ensure_ascii=False, indent=2)
        
        return by_year

def rebuild_galleries_index():
    """Reconstruit l'index des galeries par année"""
    galleries = load_gallery_data()
    index = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            year = str(date.year)
            
            if year not in index:
                index[year] = []
            
            index[year].append(gallery_id)
        except (ValueError, KeyError) as e:
            app.logger.warning(f"Impossible d'indexer la galerie {gallery_id}: {e}")
    
    # Sauvegarder l'index
    with open('galleries_index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    app.logger.info(f"Index reconstruit : {sum(len(v) for v in index.values())} galeries indexées")
    return index

def update_galleries_metadata():
    """Met à jour le fichier de métadonnées globales"""
    try:
        metadata = {
            "updated_at": datetime.now().isoformat(),
            "total_galleries": 0,
            "years": {}
        }
        
        # Parcourir tous les fichiers galleries_YYYY.json
        for year_file in sorted([f for f in os.listdir('.') if f.startswith('galleries_') and f.endswith('.json') and f != 'galleries_index.json' and f != 'galleries_metadata.json']):
            try:
                with open(year_file, 'r', encoding='utf-8') as f:
                    year_galleries = json.load(f)
                
                year = year_file.replace('galleries_', '').replace('.json', '')
                file_size = os.path.getsize(year_file) / 1024  # En KB
                
                metadata["years"][year] = {
                    "count": len(year_galleries),
                    "file": year_file,
                    "size_kb": round(file_size, 1)
                }
                metadata["total_galleries"] += len(year_galleries)
                
            except Exception as e:
                app.logger.error(f"Erreur lors de la lecture de {year_file}: {e}")
        
        # Sauvegarder les métadonnées
        with open('galleries_metadata.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        app.logger.info(f"Métadonnées mises à jour : {metadata['total_galleries']} galeries")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour des métadonnées: {e}")

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
    """Charge les données des fleurs et optimise les URLs des images."""
    try:
        with open('mountain_flowers.json', 'r', encoding='utf-8') as f:
            flowers = json.load(f)
            for flower in flowers:
                flower['optimized_image_url'] = get_optimized_flower_url(flower['image_url'])
            app.logger.info("mountain_flowers.json loaded successfully")
            return flowers
    except FileNotFoundError as e:
        app.logger.error(f"mountain_flowers.json not found: {e}")
        return []
    except json.JSONDecodeError as e:
        app.logger.error(f"Error decoding mountain_flowers.json: {e}")
        return []

def save_flowers_data(data):
    with open('mountain_flowers.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_animals_data():
    """Charge les données des animaux et optimise les URLs des images."""
    try:
        with open('mountain_animals.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            animals = data.get('animals', [])
            for animal in animals:
                animal['optimized_image_url'] = get_optimized_animal_url(animal['image_url'], type="main")
                animal['optimized_url_thumbnail'] = get_optimized_animal_url(animal.get('thumbnail_url', animal['image_url']), type="thumbnail")
            app.logger.info("mountain_animals.json loaded successfully")
            return animals

    except FileNotFoundError as e:
        app.logger.error(f"mountain_animals.json not found: {e}")
        return []
    except json.JSONDecodeError as e:
        app.logger.error(f"Error decoding mountain_animals.json: {e}")
        return []


def save_animals_data(animals):
    with open('mountain_animals.json', 'w', encoding='utf-8') as f:
        json.dump({'animals': animals}, f, ensure_ascii=False, indent=4)

def format_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{date.day} {MOIS_FR[date.month-1]} {date.year}"

def count_hikes_by_month(galleries, year=2025):
    """Compte le nombre de sorties par mois pour une année donnée."""
    monthly_counts = {month: 0 for month in range(1, 13)}  # Initialisation des compteurs à 0 pour chaque mois
    
    for gallery in galleries.values():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == year:
                monthly_counts[date.month] += 1
        except (ValueError, KeyError):
            continue
            
    return monthly_counts

def sort_galleries_by_date(galleries):
    # Convert galleries dict to list and add date object for sorting
    gallery_list = []
    for gallery_id, gallery in galleries.items():
        gallery['id'] = gallery_id
        gallery['date_obj'] = datetime.strptime(gallery['date'], '%Y-%m-%d')
        gallery_list.append(gallery)
    
    # Sort galleries by date
    return sorted(gallery_list, key=lambda x: x['date_obj'])

#    Cache les fichiers statiques mp3 pour améliorer les performances.

@lru_cache(maxsize=128)
def get_cached_static_file(filename):
    """
    Cache les fichiers statiques pour améliorer les performances.
    """
    try:
        with open(os.path.join(app.static_folder, filename), 'rb') as f:
            return f.read()
    except FileNotFoundError:
        app.logger.error(f"Fichier statique non trouvé: {filename}")
        return None

@app.route('/cached_static/<path:filename>')
def cached_static(filename):
    content = get_cached_static_file(filename)
    return send_file(io.BytesIO(content), mimetype='audio/mp3')


# optimisations images cloudinary 

def get_optimized_cover_url(cover_image_url):
    """
    Génère une URL Cloudinary optimisée pour une image de couverture.
    """
    if not cover_image_url:
        return None
    
    try:
        # Extraire le public_id de l'URL
        public_id = cover_image_url.split('/')[-1].split('.')[0]
        
        # Construire l'URL avec les transformations
        transformations = 'f_auto,q_auto,w_400,h_300,c_fill'
        optimized_cover_url = cover_image_url.replace('/upload/', '/upload/' + transformations + '/')
        
        return optimized_cover_url
    except Exception as e:
        app.logger.error(f"Erreur lors de l'optimisation de l'URL de couverture: {e}")
        return None


@lru_cache(maxsize=500)
def get_cloudinary_background_url(image_name, page_type="others"):
    """
    Génère une URL Cloudinary optimisée pour une image de fond.
    Cache les résultats pour éviter les appels API répétés.
    """
    try:
        # Récupérer les informations de l'image depuis Cloudinary
        result = cloudinary.api.resource(image_name)
        version = result['version']

        # Construire le public ID avec le numéro de version
        full_public_id = f"v{version}/{image_name}"

        # Générer l'URL avec le public ID complet et les transformations
        if page_type == "years":
            return cloudinary.CloudinaryImage(full_public_id).build_url(transformation=[{'fetch_format': 'auto'}, {'quality': 'auto'}, {'width': 2048, 'crop': 'limit'}], secure=True)
        else:
            return cloudinary.CloudinaryImage(full_public_id).build_url(transformation=[{'fetch_format': 'auto'}, {'quality': 'auto'}, {'width': 1280, 'crop': 'limit'}], secure=True)

    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des informations de l'image: {e}")
        app.logger.error(f"Erreur: {e}")
        return None

def get_optimized_memory_url(image_url, page_type="shuffle"):
    """
    Génère une URL Cloudinary optimisée pour une image de la section "Memories of Centuries".
    """
    app.logger.info(f"URL reçue : {image_url}")
    try:
        # Extraire le public_id de l'URL
        public_id = image_url.split('/')[-1].split('.')[0]

        # Construire l'URL avec les transformations
        if page_type == "shuffle":
            transformations = 'f_auto,q_auto,w_800'
        elif page_type == "pile":
            transformations = 'f_auto,q_auto,w_800'
        elif page_type == "centuries":
            transformations = 'f_auto,q_auto,w_1200,c_fill'
        else:
            transformations = 'f_auto,q_auto,w_1200'

        optimized_memory_url = image_url.replace('/upload/', '/upload/' + transformations + '/')
        app.logger.info(f"URL optimisée : {optimized_memory_url}")
        return optimized_memory_url
    except Exception as e:
        app.logger.error(f"Erreur lors de l'optimisation de l'URL de couverture: {e}")
        return image_url


def get_cloudinary_wheel_url(image_name):
    """
    Génère une URL Cloudinary optimisée pour une image de la roue.
    """
    try:
        # Récupérer les informations de l'image depuis Cloudinary
        result = cloudinary.api.resource(image_name)
        version = result['version']

        # Construire le public ID avec le numéro de version
        full_public_id = f"v{version}/{image_name}"

        # Générer l'URL avec le public ID complet et les transformations
        return cloudinary.CloudinaryImage(full_public_id).build_url(transformation=[{'fetch_format': 'auto'}, {'quality': 'auto'}, {'width': 300, 'crop': 'limit'}], secure=True)
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des informations de l'image: {e}")
        app.logger.error(f"Erreur: {e}")
        return None

def get_optimized_flower_url(image_url):
    """Génère une URL Cloudinary optimisée pour l'image principale d'une fleur."""
    transformations_main = 'f_auto,q_auto,w_800'
    url_parts_main = image_url.split('/upload/')
    if len(url_parts_main) == 2:
        optimized_url_main = url_parts_main[0] + '/upload/' + transformations_main + '/' + url_parts_main[1]
        return optimized_url_main
    return image_url


def get_optimized_animal_url(image_url, type="main"):
    """
    Génère une URL Cloudinary optimisée pour l'image principale d'un animal ou pour une miniature.
    """
    transformations_main = 'f_auto,q_auto,w_800'
    transformations_thumbnail = 'f_auto,q_auto,w_300,h_180,c_fill'
    url_parts = image_url.split('/upload/')

    if len(url_parts) == 2:
        if type == "main":
            optimized_url = url_parts[0] + '/upload/' + transformations_main + '/' + url_parts[1]
        else:
            optimized_url = url_parts[0] + '/upload/' + transformations_thumbnail + '/' + url_parts[1]
        return optimized_url
    return image_url

@lru_cache(maxsize=1000)
def get_responsive_photo_urls(image_url, width, height):
    """
    Génère toutes les URLs responsive nécessaires pour une photo de galerie.
    Cache les résultats pour éviter les calculs répétés.
    
    Args:
        image_url: URL Cloudinary de l'image
        width: Largeur de l'image
        height: Hauteur de l'image
    
    Returns:
        dict avec les URLs pour différentes tailles (400w, 800w, 1200w, lightbox, lqip)
    """
    try:
        url_parts = image_url.split('/upload/')
        if len(url_parts) != 2:
            return None
        
        base_url = url_parts[0] + '/upload/'
        image_name = url_parts[1]
        
        # Déterminer l'orientation (paysage vs portrait)
        is_landscape = width > height
        
        # Définir les transformations selon l'orientation
        if is_landscape:
            trans_400 = 'f_auto,q_auto,w_400,c_limit'
            trans_800 = 'f_auto,q_auto,w_800,c_limit'
            trans_1200 = 'f_auto,q_auto,w_1200,c_limit'
        else:
            trans_400 = 'f_auto,q_auto,h_400,c_limit'
            trans_800 = 'f_auto,q_auto,h_800,c_limit'
            trans_1200 = 'f_auto,q_auto,h_1200,c_limit'
        
        return {
            'base_url': base_url,
            'image_name': image_name,
            'url_400': f"{base_url}{trans_400}/{image_name}",
            'url_800': f"{base_url}{trans_800}/{image_name}",
            'url_1200': f"{base_url}{trans_1200}/{image_name}",
            'url_lightbox': f"{base_url}f_auto,q_auto,w_1600,c_limit/{image_name}",
            'url_lqip': f"{base_url}f_auto,q_10,w_50,e_blur:1000/{image_name}"
        }
    except Exception as e:
        app.logger.error(f"Erreur lors de la génération des URLs responsive: {e}")
        return None

# gestiobn des pages web

@app.route('/')
def home():    
    carousel_images = [get_cloudinary_background_url(f"mountain{i}") for i in range(1, 11)]
    return render_template('home.html', carousel_images=carousel_images)


@app.route('/dreams')
def dreams():
   optimized_url = get_cloudinary_background_url("loup")
   return render_template('dreams.html', dev_mode=app.config['DEV_MODE'], optimized_url=optimized_url)


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
                
                # OPTIMISATION: Stocker les dimensions directement
                gallery['photos'].append({
                    'url': result['secure_url'],
                    'filename': file.filename,
                    'width': result.get('width', 0),
                    'height': result.get('height', 0)
                })
                app.logger.info(f"Dimensions stockées: {result.get('width')}x{result.get('height')}")
            except Exception as e:
                app.logger.error(f"Erreur lors de l'upload de {file.filename}: {str(e)}")
                app.logger.error(f"Traceback complet: {traceback.format_exc()}")
                flash(f'Erreur lors du téléchargement de {file.filename}: {str(e)}')
                continue
    
    try:
        save_gallery_data(galleries)
        clear_gallery_cache()
        app.logger.info("Données sauvegardées avec succès")
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")
        flash('Erreur lors de la sauvegarde des données')
        return redirect(url_for('gallery', gallery_id=gallery_id))
    
    return redirect(url_for('gallery', gallery_id=gallery_id))

@app.route('/gallery/<gallery_id>/delete', methods=['POST'])
def delete_gallery(gallery_id):
    if not app.config['DEV_MODE']:
        abort(403)  # Forbidden in production mode
        
    galleries = load_gallery_data()
    if gallery_id in galleries:
        # Récupérer l'année de la galerie avant suppression
        try:
            gallery_date = datetime.strptime(galleries[gallery_id]['date'], '%Y-%m-%d')
            year = gallery_date.year
        except (ValueError, KeyError):
            year = 2025  # Valeur par défaut en cas d'erreur
            
        # Supprimer la galerie des données
        del galleries[gallery_id]
        save_gallery_data(galleries)
        clear_gallery_cache()
        flash('Galerie supprimée avec succès', 'success')
        
        # Rediriger vers la page de l'année appropriée
        return redirect(url_for('year_view', year=year))
    else:
        flash('Galerie non trouvée', 'error')
        return redirect(url_for('year_view', year=2025))

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
    elif year == 2024:
        return_route = 'year_2024'
    elif year == 2025:
        return_route = 'year_2025'
    elif year == 2026:
        return_route = 'year_2026'
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
                app.logger.error(f"Traceback complet: {traceback.format_exc()}")
                flash("Erreur lors de l'upload de l'image de couverture", 'error')
    
    # Ajout de la nouvelle galerie
    try:
        galleries[gallery_id] = new_gallery
        save_gallery_data(galleries)
        clear_gallery_cache()
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")
        app.logger.error(f"Traceback complet: {traceback.format_exc()}")
        flash('Erreur lors de la sauvegarde des données')
        return redirect(url_for(return_route))
    
    flash('Galerie créée avec succès', 'success')
    return redirect(url_for(return_route))

@app.route('/edit_gallery/<gallery_id>', methods=['POST'])
def edit_gallery(gallery_id):
    app.logger.info(f"Modification de la galerie {gallery_id}")
    app.logger.info(f"Données reçues: {request.form}")
    
    galleries = load_gallery_data()
    if gallery_id not in galleries:
        flash('Galerie non trouvée')
        return redirect(url_for('year_view', year=2024))
    
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
        clear_gallery_cache()
        flash('Galerie mise à jour avec succès')
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde: {str(e)}")
        app.logger.error(f"Traceback complet: {traceback.format_exc()}")
        flash('Erreur lors de la sauvegarde des modifications')
    
    return redirect(url_for('gallery', gallery_id=gallery_id))


@app.route('/gallery/<gallery_id>')
def gallery(gallery_id):
    page = request.args.get('page', 1, type=int)
    per_page = app.config['PHOTOS_PER_PAGE']
    
    # Essayer d'abord avec l'index pour trouver l'année de la galerie
    try:
        index = load_galleries_index()
        gallery_year = None
        
        # Chercher dans quel fichier se trouve la galerie
        for year, gallery_ids in index.items():
            if gallery_id in gallery_ids:
                gallery_year = int(year)
                break
        
        if gallery_year:
            # Chargement ultra-optimisé : uniquement le fichier de l'année
            galleries = load_gallery_data_for_year(gallery_year)
        else:
            # Fallback : chargement complet
            galleries = load_gallery_data()
    except:
        # En cas d'erreur avec l'index, utiliser le chargement complet
        galleries = load_gallery_data()
    
    gallery = galleries.get(gallery_id)
    if not gallery:
        return "Gallery not found", 404
    
    # Créer une copie pour éviter de modifier l'original
    gallery_copy = gallery.copy()
    # Copie profonde des photos pour hériter les dimensions du JSON
    gallery_copy['photos'] = [photo.copy() for photo in gallery.get('photos', [])]
        
    # S'assurer que formatted_date est défini
    if 'date' in gallery_copy and 'formatted_date' not in gallery_copy:
        gallery_copy['formatted_date'] = format_date(gallery_copy['date'])
    
    # Pagination des photos
    total_photos = len(gallery_copy.get('photos', []))
    total_pages = (total_photos + per_page - 1) // per_page  # Arrondi supérieur
    
    start = (page - 1) * per_page
    end = start + per_page
    
    photos = gallery_copy.get('photos', [])
    gallery_copy['photos_paginated'] = photos[start:end]
    gallery_copy['pagination'] = {
        'current_page': page,
        'total_pages': total_pages,
        'total_photos': total_photos,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }
    
    # Déterminer la page de retour en fonction de l'année
    date = datetime.strptime(gallery_copy['date'], '%Y-%m-%d')
    year = date.year
    return_page = f'year_view'  # Utiliser la route dynamique
    
    # Ajouter l'ID à l'objet gallery_copy
    gallery_copy['id'] = gallery_id
    
    # Ajouter formatted_date s'il n'existe pas
    if 'formatted_date' not in gallery_copy:
        date_obj = datetime.strptime(gallery_copy['date'], '%Y-%m-%d')
        day = str(date_obj.day).lstrip('0')  # Enlever le zéro initial
        gallery_copy['formatted_date'] = f"{day} {date_obj.strftime('%B %Y')}"

    # Special case for GR20 gallery
    if gallery_id == "20240905_gr20":
        optimized_background_url = get_cloudinary_background_url("corse")
        # Get the image URL from Cloudinary
        gr20_thumbnail_url = cloudinary.CloudinaryImage("gr20_thumbnail").build_url(secure=True)
         
        return render_template('gallery.html', 
                            gallery=gallery_copy,
                            dev_mode=app.config['DEV_MODE'],
                            format_date=format_date,
                            return_page=return_page,
                            optimized_background_url=optimized_background_url,
                            gr20_thumbnail_url=gr20_thumbnail_url)
    else:
        optimized_background_url = None
        # Optimize the background image URL
        if gallery_copy.get('cover_image'):
            image_name = gallery_copy['cover_image'].split('/')[-1].split('.')[0]
            gallery_copy['optimized_background_url'] = get_cloudinary_background_url(image_name)
            gallery_copy['cover_image'] = None # Remove the original image
        else:
            gallery_copy['optimized_background_url'] = None
 
        # Définir l'image de fond
        optimized_background_url = gallery_copy['optimized_background_url']
        # Optimiser la récupération des dimensions des photos avec cache persistant
        # Les dimensions sont déjà dans gallery_copy si elles existent dans le JSON
        dimensions_updated = False
        for photo in gallery_copy['photos']:
            photo_id = photo['url'].split('/')[-1].split('.')[0]
            
            # Vérifier si les dimensions sont déjà dans la photo (elles viennent du JSON)
            if 'width' in photo and 'height' in photo and photo['width'] > 0 and photo['height'] > 0:
                # Les dimensions sont déjà en cache, pas d'appel API
                pass
            else:
                # Utiliser le cache persistant ET sauvegarder pour les prochaines fois
                app.logger.info(f"Dimensions manquantes pour {photo_id}, appel API...")
                dimensions = get_photo_dimensions(photo_id)
                if dimensions['width'] > 0 and dimensions['height'] > 0:
                    photo['width'] = dimensions['width']
                    photo['height'] = dimensions['height']
                    # Sauvegarder les dimensions dans le JSON pour les prochaines visualisations
                    save_photo_dimensions_to_gallery(gallery_id, photo_id, dimensions['width'], dimensions['height'])
                    dimensions_updated = True
                else:
                    app.logger.warning(f"Impossible de récupérer les dimensions pour {photo_id}")
            
            # OPTIMISATION: Optimisation simple des URLs Cloudinary
            if photo['url'] and 'cloudinary.com' in photo['url']:
                # Ajouter une optimisation basique pour réduire la taille
                url_parts = photo['url'].split('/upload/')
                if len(url_parts) == 2:
                    base_url = url_parts[0] + '/upload/'
                    image_name = url_parts[1]
                    # Optimisation modérée : qualité auto et taille raisonnable
                    optimized_url = f"{base_url}f_auto,q_auto,w_1200,c_limit/{image_name}"
                    photo['url'] = optimized_url

        return render_template('gallery.html', 
                            gallery=gallery_copy, 
                            dev_mode=app.config['DEV_MODE'],
                            format_date=format_date,
                            return_page=return_page,
                            optimized_background_url=optimized_background_url)
   


@app.route('/month/<int:year>/<int:month>')
def month_galleries(year, month):
    # OPTIMISATION : Charger uniquement les galeries de l'année demandée
    galleries = load_gallery_data_for_year(year)
    month_galleries_data = []
    optimized_background_url = None
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == year and date.month == month:
                gallery['id'] = gallery_id
                gallery['formatted_date'] = format_date(gallery['date'])
                
              # Traitement spécifique pour la galerie GR20
                if gallery_id == "20240905_gr20":
                    gallery['optimized_cover_url'] = get_cloudinary_background_url("gr20_thumbnail")
                else:
                    # Définir l'image de fond si elle n'est pas déjà définie
                    if not optimized_background_url and gallery.get('cover_image'):
                        image_name = gallery['cover_image'].split('/')[-1].split('.')[0]
                        optimized_background_url = get_cloudinary_background_url(image_name)

                    # Optimiser l'image de couverture pour la vignette (même logique que year_view)
                    if gallery.get('cover_image'):
                        image_name = gallery['cover_image'].split('/')[-1].split('.')[0]
                        gallery['optimized_cover_url'] = get_cloudinary_background_url(image_name)
                        app.logger.info(f"Vignette optimisée pour {gallery_id}: {gallery['optimized_cover_url']}")
                    else:
                        gallery['optimized_cover_url'] = None
                        app.logger.warning(f"Pas d'image de couverture pour {gallery_id}")
                month_galleries_data.append(gallery)
                app.logger.debug(f"Galerie ajoutée pour {MOIS_FR[month-1]} {year}: {gallery['name']}")


        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")

    # Trier les galeries par date
    month_galleries_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))
    
    return render_template('month.html',
                           galleries=month_galleries_data,
                           optimized_background_url=optimized_background_url, 
                           month=f"{MOIS_FR[month-1]} {year}",
                           year=year,
                           dev_mode=app.config['DEV_MODE'])


@app.route('/years')
def years():
    background_url = get_cloudinary_background_url("granier",page_type="years")
    return render_template('years.html', dev_mode=app.config['DEV_MODE'], background_url=background_url)

@app.route('/projets')
def projets():
    app.logger.info("Fonction projets appelée")
    try:
        # Charger les projets
        app.logger.info("Tentative de chargement des projets")
        all_projects = load_projects()
        
        # Filtrer pour ne garder que les projets de 2025 ou sans année spécifiée
        photos = [p for p in all_projects if p.get('year', 2025) != 2026]
        app.logger.info(f"Nombre de projets chargés : {len(photos)}")

        # Trier les projets par date (du plus récent au plus ancien)
        app.logger.info("Tentative de tri des projets")
        photos_sorted = sorted(
            photos,
            key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'),
            reverse=True
        )
        app.logger.info("Tri des projets réussi")

        return render_template('projets.html',
                             photos=photos_sorted,
                             dev_mode=app.config['DEV_MODE'])
    except FileNotFoundError as e:
        app.logger.error(f"Fichier projects.json non trouvé: {e}")
        flash("Le fichier des projets est manquant.")
        return redirect(url_for('year_view', year=2025))
    except json.JSONDecodeError as e:
        app.logger.error(f"Erreur de décodage JSON dans projects.json: {e}")
        flash("Erreur de format dans le fichier des projets.")
        return redirect(url_for('year_view', year=2025))
    except ValueError as e:
        app.logger.error(f"Erreur de format de date dans projects.json: {e}")
        flash("Erreur de format de date dans le fichier des projets.")
        return redirect(url_for('year_view', year=2025))
    except Exception as e:
        app.logger.error(f"Une erreur s'est produite lors du chargement des projets: {e}")
        flash("Une erreur s'est produite lors du chargement des projets")
        return redirect(url_for('year_view', year=2025))

@app.route('/add_project', methods=['POST'])
@app.route('/add_project/<int:year>', methods=['POST'])
def add_project(year=None):
    if not app.config['DEV_MODE']:
        return abort(403)
    
    try:
        data = request.form
        file = request.files['cover_image']
        
        if file:
            upload_result = cloudinary.uploader.upload(file)
            image_url = upload_result['secure_url']
            
            # Si l'année n'est pas spécifiée dans l'URL, on la déduit de la date
            if year is None:
                # Essayer d'extraire l'année de la date fournie
                try:
                    date_obj = datetime.strptime(data['date'], '%Y-%m-%d')
                    year = date_obj.year
                except (ValueError, KeyError):
                    # Si la date est invalide ou absente, on utilise l'année courante
                    year = datetime.now().year
            
            new_project = {
                'id': str(uuid.uuid4()),
                'url': image_url,
                'gallery_name': data['title'],
                'date': data['date'],
                'formatted_date': format_date(data['date']),
                'description': data['description'],
                'year': year  # Ajout de l'année au projet
            }
            
            projects = load_projects()
            projects.append(new_project)
            save_projects(projects)
            
        # Rediriger vers la page appropriée en fonction de l'année
        if year == 2026:
            return redirect(url_for('projets_2026'))
        else:
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
    # Optimiser les URLs des images
    for year, year_memories in memories.items():
        for memory in year_memories:
            memory['optimized_url'] = get_optimized_memory_url(memory['url'], page_type="centuries")

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
            'optimized_url': get_optimized_memory_url(upload_result['secure_url'], page_type="centuries"),
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
                        memory['optimized_url'] = get_optimized_memory_url(upload_result['secure_url'], page_type="centuries")
                    
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
         for photo in year_photos:
            photo['optimized_url'] = get_optimized_memory_url(photo['url'], page_type="shuffle")
            all_photos.append(photo)
    
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
                        memory['optimized_url'] = get_optimized_memory_url(memory['url'], page_type="pile")
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
@app.route('/admin/download-json/<filename>')
def download_json(filename):
    """Endpoint sécurisé pour télécharger les fichiers JSON (uniquement en dev)"""
    if not app.config.get('DEV_MODE', False):
        return "Non autorisé en production", 403
    
    # Validation du nom de fichier pour sécurité
    if not filename.startswith('galleries_') or not filename.endswith('.json'):
        return "Nom de fichier invalide", 400
    
    # Vérifier que le fichier existe
    file_path = os.path.join('.', filename)
    if not os.path.exists(file_path):
        return "Fichier non trouvé", 404
    
    # Envoyer le fichier
    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/admin/sync-all-json')
def sync_all_json():
    """Page de synchronisation de tous les JSON (uniquement en dev)"""
    if not app.config.get('DEV_MODE', False):
        return "Non autorisé en production", 403
    
    import glob
    json_files = glob.glob('galleries_*.json')
    index_files = ['galleries_index.json', 'galleries_by_year.json', 'galleries_metadata.json']
    
    all_files = json_files + [f for f in index_files if os.path.exists(f)]
    
    return render_template('sync_json.html', files=all_files)

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

# les années :

@app.route('/<int:year>')
def year_view(year):
    # Validation de l'année
    if year < 2016 or year > 2026:
        abort(404)
    
    # OPTIMISATION : Charger uniquement les galeries de l'année demandée
    galleries = load_gallery_data_for_year(year)
    galleries_by_month = {}
    today = datetime.now()  # Ajouter pour détecter les dates futures
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == year:
                month_key = f"{MOIS_FR[date.month-1]} {date.year}"
                month_num = date.strftime('%m')
                year_str = date.strftime('%Y')
                
                if month_key not in galleries_by_month:
                    galleries_by_month[month_key] = {
                        'galleries': [],
                        'month': int(month_num),
                        'year': year_str,
                        'cover': None
                    }
                
                # Ajouter l'indicateur is_future pour 2026
                if year == 2026:
                    galleries_by_month[month_key]['is_future'] = date > today
                
                gallery['id'] = gallery_id
                galleries_by_month[month_key]['galleries'].append(gallery)
                
                # Mettre à jour l'image de couverture si c'est la première galerie du mois
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                    # Optimize cover image URL
                    image_name = gallery['cover_image'].split('/')[-1].split('.')[0]
                    galleries_by_month[month_key]['optimized_cover'] = get_cloudinary_background_url(image_name)
                    app.logger.info(f"Galerie ajoutée pour {year}: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Trouver la première image de couverture disponible
    background_url = None
    if galleries_by_month:     
        app.logger.info("Recherche de l'image de fond")
        for month_data in galleries_by_month.values():
            if month_data['cover']:
                background_url = get_cloudinary_background_url(month_data['cover'].split('/')[-1].split('.')[0]) if month_data['cover'] else None
                if background_url: #si on a trouvé une image on sort de la boucle
                    break

    # Calculer les statistiques de sorties pour chaque mois
    for month_key, month_data in galleries_by_month.items():
        month_data['hikes_count'] = len(month_data['galleries'])
        # Calculer le total de photos pour le mois
        month_data['photos_count'] = sum(len(gallery.get('photos', [])) for gallery in month_data['galleries'])
    
    return render_template(f'{year}.html', 
                        galleries_by_month=galleries_by_month,
                        background_url=background_url,
                        dev_mode=app.config['DEV_MODE'])

@app.route('/wheel-of-fortune')
def wheel_of_fortune():
    background_url = get_cloudinary_background_url("roue")
    wheel_images = [get_cloudinary_wheel_url(f"roue{i}") for i in range(1, 13)]
    return render_template('wheel_of_fortune.html', dev_mode=app.config['DEV_MODE'], wheel_images=wheel_images, background_url=background_url)


@app.route('/inmy')
def inmy_landing():
    if request.args.get('back') == 'true':
        return redirect(url_for('years'))
    session['slide_url'] = get_cloudinary_background_url("slide-img-fall")
    return render_template('inmy_cover.html', slide_url=session['slide_url'])


@app.route('/inmy_life')
def inmy_life():
    page = request.args.get('page', 1, type=int)
    total_pages = 6
    
    # Load texts from JSON file
    try:
        with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
            texts = json.load(f)
    except FileNotFoundError:
        texts = {}

    # Assurer que toutes les clés de texte existent
    for i in range(1, total_pages + 1):
        if str(i) not in texts:
            texts[str(i)] = ""  # Initialiser avec une chaîne vide si la clé n'existe pas
    
    # Get text for current page
    text_key = str(page)
    page_text = texts.get(text_key, '')
    
    # Navigation URLs
    prev_url = url_for('inmy_landing') if page == 1 else url_for('inmy_life', page=page-1)
    next_url = url_for('inmy_life', page=page+1) if page < total_pages else None
    
      # Get image URLs from Cloudinary
    page_image_url = get_cloudinary_background_url(f"page{page}") if page <= 5 else None

      # Préparer les variables de texte pour le template
    text_vars = {}
    for i in range(1, total_pages + 1):
        text_vars[f'text{i}'] = texts.get(str(i), "")

    return render_template('inmy_life.html', 
                         page=page,
                         total_pages=total_pages,
                         prev_url=prev_url,
                         next_url=next_url,
                         dev_mode=app.config['DEV_MODE'],
                         page_image_url=page_image_url,
                         slide_url=session.get('slide_url', get_cloudinary_background_url("slide-img-fall")),
                         **text_vars)

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

@app.route('/gallery/<gallery_id>/update_order', methods=['POST'])
def update_photo_order(gallery_id):
    if not app.config['DEV_MODE']:
        return jsonify({'status': 'error', 'message': 'Non autorisé'}), 403
    
    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'status': 'error', 'message': 'Données invalides'}), 400
    
    try:
        galleries = load_gallery_data()
        if gallery_id not in galleries:
            return jsonify({'status': 'error', 'message': 'Galerie non trouvée'}), 404
        
        gallery = galleries[gallery_id]
        if 'photos' not in gallery:
            return jsonify({'status': 'error', 'message': 'Aucune photo dans la galerie'}), 400
        
        # Créer un dictionnaire pour accéder rapidement aux photos par leur URL
        photos_by_url = {}
        for photo in gallery['photos']:
            if 'url' in photo and isinstance(photo['url'], str):
                # Utiliser l'URL complète comme clé
                photos_by_url[photo['url']] = photo
                
                # Ajouter également une entrée avec le nom de fichier comme clé
                filename = photo['url'].split('/')[-1].split('?')[0]
                photos_by_url[filename] = photo
        
        new_photos_order = []
        missing_photos = []
        
        # Reconstruire l'ordre des photos selon l'ordre reçu
        for item in data['order']:
            if 'url' in item:
                url = item['url']
                # Essayer de trouver la photo par URL complète d'abord
                if url in photos_by_url:
                    new_photos_order.append(photos_by_url[url])
                else:
                    # Sinon, essayer avec le nom de fichier
                    filename = url.split('/')[-1].split('?')[0]
                    if filename in photos_by_url:
                        new_photos_order.append(photos_by_url[filename])
                    else:
                        missing_photos.append(url)
        
        # Vérifier si toutes les photos ont été trouvées
        if missing_photos:
            return jsonify({
                'status': 'error', 
                'message': 'Certaines photos n\'ont pas été trouvées',
                'missing_photos': missing_photos
            }), 400
        
        # Mettre à jour la galerie avec le nouvel ordre
        gallery['photos'] = new_photos_order
        
        # Sauvegarder les modifications
        save_gallery_data(galleries)
        clear_gallery_cache()
        
        return jsonify({
            'status': 'success', 
            'message': 'Ordre des photos mis à jour avec succès',
            'new_order': [{'url': p.get('url'), 'filename': p.get('filename')} for p in new_photos_order]
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour de l'ordre des photos: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': f'Erreur serveur: {str(e)}'
        })

@app.route('/2026')
def year_2026():
    """Route spécifique pour 2026 avec logique future intégrée"""
    return year_view(2026)

@app.route('/projets-2026')
def projets_2026():
    """Affiche la page des projets pour l'année 2026."""
    try:
        # Charger les projets existants depuis le fichier JSON
        projects = load_projects()
        
        # Filtrer les projets pour ne garder que ceux de l'année 2026
        # Si le projet n'a pas d'année spécifiée, on le considère comme 2025 pour la rétrocompatibilité
        year_projects = [p for p in projects if p.get('year', 2025) == 2026]
        
        # Trier les projets par date (du plus récent au plus ancien)
        year_projects_sorted = sorted(
            year_projects,
            key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'),
            reverse=True
        )
        
        return render_template(
            'projets-2026.html',
            photos=year_projects_sorted,  # Utilisation de 'photos' pour la cohérence avec le template
            dev_mode=app.config['DEV_MODE']
        )
    except Exception as e:
        app.logger.error(f"Erreur lors du chargement des projets 2026: {str(e)}")
        return render_template('error.html', error_message="Une erreur est survenue lors du chargement des projets 2026.")

# À ajouter dans app.py après les autres routes

@app.route('/map')
def interactive_map():
    """Route pour la carte interactive des randonnées"""
    galleries = load_gallery_data()
    
    # Convertir les galeries en format pour la carte
    hikes = []
    for gallery_id, gallery in galleries.items():
        # Vérifier si la galerie a des coordonnées GPS
        if 'lat' in gallery and 'lon' in gallery:
            hike_data = {
                'id': gallery_id,
                'name': gallery.get('name', 'Sans nom'),
                'lat': gallery['lat'],
                'lon': gallery['lon'],
                'date': gallery.get('date', ''),
                'description': gallery.get('description', ''),
                'photos_count': len(gallery.get('photos', [])),
                'cover_image': get_optimized_cover_url(gallery.get('cover_image')) if gallery.get('cover_image') else None,
                'distance': gallery.get('distance', None),
                'denivele': gallery.get('denivele', None),
                'difficulty': gallery.get('difficulty', 'moyen'),
                'duration': gallery.get('duration', None)
            }
            hikes.append(hike_data)
    
    # Trier par date (plus récent en premier)
    hikes.sort(key=lambda x: x['date'], reverse=True)
    
    # Convertir en JSON pour le template
    hikes_json = json.dumps(hikes)
    
    return render_template('map.html', hikes_json=hikes_json)


@app.route('/api/hikes')
def get_hikes_api():
    """API pour récupérer les données des randonnées"""
    galleries = load_gallery_data()
    
    hikes = []
    for gallery_id, gallery in galleries.items():
        if 'lat' in gallery and 'lon' in gallery:
            hike_data = {
                'id': gallery_id,
                'name': gallery.get('name', 'Sans nom'),
                'lat': gallery['lat'],
                'lon': gallery['lon'],
                'date': gallery.get('date', ''),
                'description': gallery.get('description', ''),
                'photos_count': len(gallery.get('photos', [])),
                'cover_image': get_optimized_cover_url(gallery.get('cover_image')) if gallery.get('cover_image') else None,
                'distance': gallery.get('distance'),
                'denivele': gallery.get('denivele'),
                'difficulty': gallery.get('difficulty', 'moyen'),
                'duration': gallery.get('duration')
            }
            hikes.append(hike_data)
    
    return jsonify({'hikes': hikes, 'count': len(hikes)})


@app.route('/api/hike/<gallery_id>/gpx')
def get_hike_gpx(gallery_id):
    """Récupérer le fichier GPX d'une randonnée"""
    galleries = load_gallery_data()
    
    if gallery_id not in galleries:
        return jsonify({'error': 'Randonnée non trouvée'}), 404
    
    gallery = galleries[gallery_id]
    
    if 'gpx_file' not in gallery:
        return jsonify({'error': 'Pas de fichier GPX pour cette randonnée'}), 404
    
    # Retourner le chemin du fichier GPX
    return jsonify({'gpx_url': gallery['gpx_file']})


@app.route('/upload_gpx/<gallery_id>', methods=['POST'])
def upload_gpx(gallery_id):
    """Upload d'un fichier GPX pour une randonnée"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    if 'gpx_file' not in request.files:
        return jsonify({'error': 'Pas de fichier GPX'}), 400
    
    file = request.files['gpx_file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    
    # Vérifier l'extension
    if not file.filename.endswith('.gpx'):
        return jsonify({'error': 'Le fichier doit être au format GPX'}), 400
    
    try:
        # Créer le dossier GPX s'il n'existe pas
        gpx_folder = os.path.join(app.static_folder, 'gpx')
        os.makedirs(gpx_folder, exist_ok=True)
        
        # Sauvegarder le fichier
        filename = secure_filename(f"{gallery_id}.gpx")
        filepath = os.path.join(gpx_folder, filename)
        file.save(filepath)
        
        # Mettre à jour la galerie
        galleries = load_gallery_data()
        if gallery_id in galleries:
            galleries[gallery_id]['gpx_file'] = f'/static/gpx/{filename}'
            save_gallery_data(galleries)
            clear_gallery_cache()
            
            return jsonify({
                'success': True,
                'gpx_url': f'/static/gpx/{filename}'
            })
        else:
            return jsonify({'error': 'Galerie non trouvée'}), 404
            
    except Exception as e:
        app.logger.error(f"Erreur lors de l'upload du GPX: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/edit_gallery/<gallery_id>/location', methods=['POST'])
def edit_gallery_location(gallery_id):
    """Mettre à jour les coordonnées GPS d'une galerie"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    data = request.get_json()
    
    if 'lat' not in data or 'lon' not in data:
        return jsonify({'error': 'Coordonnées manquantes'}), 400
    
    try:
        galleries = load_gallery_data()
        
        if gallery_id not in galleries:
            return jsonify({'error': 'Galerie non trouvée'}), 404
        
        # Mettre à jour les coordonnées
        galleries[gallery_id]['lat'] = float(data['lat'])
        galleries[gallery_id]['lon'] = float(data['lon'])
        
        # Mettre à jour les autres informations optionnelles
        if 'distance' in data:
            galleries[gallery_id]['distance'] = float(data['distance'])
        if 'denivele' in data:
            galleries[gallery_id]['denivele'] = int(data['denivele'])
        if 'difficulty' in data:
            galleries[gallery_id]['difficulty'] = data['difficulty']
        if 'duration' in data:
            galleries[gallery_id]['duration'] = data['duration']
        
        save_gallery_data(galleries)
        clear_gallery_cache()
        
        return jsonify({'success': True, 'message': 'Coordonnées mises à jour'})
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour des coordonnées: {str(e)}")
        return jsonify({'error': str(e)}), 500
        
if __name__ == '__main__':
    app.run(debug=True)
