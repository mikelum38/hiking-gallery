# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, session
import json
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os
import tempfile
import shutil
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
from gpx_manager import gpx_manager

# Initialiser Sentry si activé
if Config.ENABLE_SENTRY and Config.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.environ.get('FLASK_ENV', 'production')
    )


load_dotenv()  # Chargement des variables d'environnement depuis .env

# Configuration des extensions de fichiers autorisées
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_GPX_EXTENSIONS = {'gpx'}

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

def allowed_gpx_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_GPX_EXTENSIONS

# Fonctions de déduction de coordonnées
def deduire_coordonnees_gps(name, description, date):
    """Déduit les coordonnées GPS selon le lieu de la randonnée"""
    
    text = f"{name} {description}".lower()
    
    # Corse d'abord !
    if 'corse' in text or 'gr20' in text:
        return (42.389667, 9.135556), "Corse - GR20"
    
    # Lieux spécifiques avec coordonnées exactes
    lieux_specifiques = {
        'tete chevalière': (44.966667, 5.783333),  # Vercors
        'tête chevalière': (44.966667, 5.783333),  # Vercors
        'le peu': (45.183333, 5.766667),        # Uriol - Grenoble
        'pieu': (45.183333, 5.766667),          # Uriol - Grenoble
        'crête d uriol': (45.183333, 5.766667),  # Uriol - Grenoble
        'saint paul de varces': (45.183333, 5.766667), # Grenoble
        'tour isabelle': (45.083927, 5.884837),  # Chartreuse
        'aiguilles de chabrière': (44.516670, 6.366670), # Serre-Ponçon
        'vallon de la jarjatte': (44.950000, 5.616670), # Vercors
        'bivouac lacs tempêtes': (44.916670, 6.366670), # Ecrins
        'lac glaciaire grand mean': (45.479920, 6.913780), # Vanoise
        'trek nevaches': (44.900410, 6.376890),  # Briançon - Clarée
        'granier': (45.4333, 5.9167),          # Chartreuse
    }
    
    for lieu, coords in lieux_specifiques.items():
        if lieu in text:
            return coords, f"Lieu: {lieu}"
    
    # Massifs
    massifs = {
        'chartreuse': (45.083927, 5.884837),
        'vercors': (44.950000, 5.616670),
        'ecrins': (44.916670, 6.366670),
        'vanoise': (45.416670, 6.750000),
        'chamonix': (45.923638, 6.869822),
        'serre poncon': (44.516670, 6.366670),
        'bauges': (45.916670, 6.133330),
        'briançon': (44.900410, 6.376890),
        'tignes': (45.479920, 6.913780),
        'les 2 alpes': (44.983330, 6.050000),
        'alpe d huez': (45.083330, 6.050000),
        'courchevel': (45.416670, 6.583330),
        'val d isere': (45.561390, 6.983330),
        'val thorens': (45.300000, 6.583330),
        'megeve': (45.857770, 6.614940),
        'flaine': (45.983570, 6.723880),
        'annecy': (45.916670, 6.133330),
        'grenoble': (45.188529, 5.724524),
        'villard de lans': (44.950000, 5.616670),
        'chamrousse': (45.083927, 5.884837),
    }
    
    for massif, coords in massifs.items():
        if massif in text:
            return coords, f"Massif: {massif}"
    
    # Par défaut selon l'année
    if date:
        annee = date[:4]
        coords_annee = {
            '2026': (45.188529, 5.724524),  # Grenoble
            '2025': (45.923638, 6.869822),  # Chamonix
            '2024': (42.389667, 9.135556),  # Corse par défaut pour 2024
            '2023': (45.479920, 6.913780),  # Tignes
            '2022': (45.083927, 5.884837),  # Chamrousse
            '2021': (45.983570, 6.723880),  # Flaine
            '2020': (44.983330, 6.050000),  # Les 2 Alpes
            '2019': (45.416670, 6.583330),  # Courchevel
            '2018': (45.561390, 6.983330),  # Val d'Isère
            '2017': (45.300000, 6.583330),  # Val Thorens
            '2016': (45.083330, 6.050000),  # Alpe d'Huez
        }
        if annee in coords_annee:
            return coords_annee[annee], f"Défaut {annee}"
    
    return (45.188529, 5.724524), "Défaut Grenoble"

def clean_gallery_data(gallery_data):
    """
    Nettoie les données d'une galerie pour respecter les standards:
    - Supprime les champs inutiles (formatted_date, etc.)
    - S'assure que lat/lon existent
    - Conserve uniquement les champs nécessaires
    """
    if not isinstance(gallery_data, dict):
        return gallery_data
    
    # Copie pour éviter de modifier l'original
    cleaned = gallery_data.copy()
    
    # Champs à supprimer
    fields_to_remove = [
        'formatted_date',
        'coordinates_added',
        'coordinates_method', 
        'deducted_location',
        'id'  # Champ ID potentiellement ajouté par erreur
    ]
    
    for field in fields_to_remove:
        if field in cleaned:
            del cleaned[field]
    
    # S'assurer que les coordonnées GPS existent
    if 'lat' not in cleaned or 'lon' not in cleaned:
        # Essayer de déduire les coordonnées
        name = cleaned.get('name', '')
        description = cleaned.get('description', '')
        date = cleaned.get('date', '')
        
        coords, lieu = deduire_coordonnees_gps(name, description, date)
        lat, lon = coords
        cleaned['lat'] = lat
        cleaned['lon'] = lon
        
        app.logger.info(f"Coordonnées déduites pour {name}: {lat:.4f}, {lon:.4f} ({lieu})")
    
    # S'assurer que cover_image est None si absent (pas de chaîne vide)
    if 'cover_image' in cleaned and not cleaned['cover_image']:
        del cleaned['cover_image']
    
    return cleaned

def save_single_gallery_to_year(gallery_id, gallery_data):
    """
    Sauvegarde uniquement une galerie dans son fichier galleries_YYYY.json correspondant.
    Optimisé pour le lazy loading : ne sauvegarde que l'année concernée.
    """
    # Nettoyer les données avant sauvegarde
    cleaned_gallery = clean_gallery_data(gallery_data)
    
    try:
        # Déterminer l'année de la galerie
        if 'year' in cleaned_gallery:
            year = cleaned_gallery['year']
            # Les champs year/month/day sont déjà présents et dans le bon ordre
        else:
            date = datetime.strptime(cleaned_gallery['date'], '%Y-%m-%d')
            year = date.year
            # Ajouter les champs seulement s'ils n'existent pas (pour les galeries plus anciennes)
            cleaned_gallery['year'] = year
            cleaned_gallery['month'] = date.month
            cleaned_gallery['day'] = date.day
        
        # Charger uniquement le fichier de l'année concernée
        year_file = f"galleries_{year}.json"
        year_galleries = {}
        
        if os.path.exists(year_file):
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
        
        # Mettre à jour uniquement cette galerie
        year_galleries[gallery_id] = cleaned_gallery
        
        # Sauvegarder uniquement ce fichier
        with open(year_file, 'w', encoding='utf-8') as f:
            json.dump(year_galleries, f, ensure_ascii=False, indent=2)
        
        app.logger.info(f"✅ {year_file} mis à jour (1 galerie)")
        
        # Mettre à jour le cache
        clear_gallery_cache()
        
        # Ne PAS mettre à jour galleries.json pour l'upload GPX
        # Seul le fichier annuel doit être mis à jour avec les coordonnées
        # update_galleries_json_search()  # COMMENTÉ - INUTILE POUR GPX
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde de {gallery_id}: {e}")

def update_galleries_json_search():
    """
    Met à jour galleries.json avec seulement les champs de recherche.
    Utilisé pour la recherche optimisée.
    """
    try:
        # Charger toutes les galeries depuis les fichiers annuels
        all_galleries = load_gallery_data()
        
        # Extraire seulement les champs de recherche
        search_only_data = {}
        for gallery_id, gallery in all_galleries.items():
            search_only_data[gallery_id] = {
                'name': gallery.get('name', ''),
                'description': gallery.get('description', ''),
                'date': gallery.get('date', ''),
                'year': gallery.get('year', ''),
                'month': gallery.get('month', ''),
                'day': gallery.get('day', '')
            }
        
        # Sauvegarder dans galleries.json
        with open('galleries.json', 'w', encoding='utf-8') as f:
            json.dump(search_only_data, f, ensure_ascii=False, indent=2)
        
        # Reconstruire l'index des galeries par année (pour la route /gallery/<id>)
        rebuild_galleries_index()
        
        # Mettre à jour le moteur de recherche
        global search_engine
        search_engine = SearchEngine('galleries.json')
        
        app.logger.info(f"✅ galleries.json et index mis à jour ({len(all_galleries)} galeries)")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour de galleries.json: {e}")

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
    
    # Sauvegarder seulement les champs de recherche dans galleries.json
    search_only_data = {}
    for gallery_id, gallery in data.items():
        search_only_data[gallery_id] = {
            'name': gallery.get('name', ''),
            'description': gallery.get('description', ''),
            'date': gallery.get('date', ''),
            'year': gallery.get('year', ''),
            'month': gallery.get('month', ''),
            'day': gallery.get('day', '')
        }
    
    with open('galleries.json', 'w', encoding='utf-8') as f:
        json.dump(search_only_data, f, ensure_ascii=False, indent=2)
    
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
                
                # Vérifier si c'est un format direct (comme galleries_2008.json)
                if isinstance(year_galleries, dict) and 'name' in year_galleries and 'photos' in year_galleries:
                    # Format direct : créer un ID basé sur la date
                    date_str = year_galleries.get('date', '')
                    if date_str:
                        gallery_id = date_str.replace('-', '_') + '_direct'
                        galleries[gallery_id] = year_galleries
                        app.logger.info(f"✅ Format direct : 1 galerie depuis {year_file}")
                    else:
                        app.logger.warning(f"⚠️  Fichier {year_file} au format direct mais sans date")
                else:
                    # Format normal : dictionnaire de galeries
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



# FONCTIONS POUR LA GESTION SEARCH-ONLY DE GALLERIES.JSON

def save_gallery_to_search_only(gallery_id, gallery_data):
    """
    Sauvegarde uniquement les champs de recherche dans galleries.json.
    Utilisé pour optimiser la taille du fichier de recherche.
    """
    try:
        # Charger galleries.json existant
        galleries_search = {}
        if os.path.exists('galleries.json'):
            with open('galleries.json', 'r', encoding='utf-8') as f:
                galleries_search = json.load(f)
        
        # Ajouter/Mettre à jour uniquement les champs de recherche
        galleries_search[gallery_id] = {
            'name': gallery_data.get('name', ''),
            'date': gallery_data.get('date', ''),
            'description': gallery_data.get('description', ''),
            'year': gallery_data.get('year', datetime.strptime(gallery_data.get('date', '2000-01-01'), '%Y-%m-%d').year),
            'month': gallery_data.get('month', datetime.strptime(gallery_data.get('date', '2000-01-01'), '%Y-%m-%d').month),
            'day': gallery_data.get('day', datetime.strptime(gallery_data.get('date', '2000-01-01'), '%Y-%m-%d').day)
        }
        
        # Sauvegarder
        with open('galleries.json', 'w', encoding='utf-8') as f:
            json.dump(galleries_search, f, ensure_ascii=False, indent=2)
        
        app.logger.info(f"✅ Galerie {gallery_id} ajoutée à galleries.json (search-only)")
        
        # Mettre à jour le moteur de recherche
        global search_engine
        search_engine = SearchEngine('galleries.json')
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde search-only: {e}")
        raise

def update_gallery_in_search_only(gallery_id, gallery_data):
    """
    Met à jour uniquement les champs de recherche dans galleries.json.
    """
    try:
        # Charger galleries.json existant
        if not os.path.exists('galleries.json'):
            app.logger.warning("galleries.json n'existe pas, création...")
            galleries_search = {}
        else:
            with open('galleries.json', 'r', encoding='utf-8') as f:
                galleries_search = json.load(f)
        
        # Mettre à jour uniquement si la galerie existe
        if gallery_id in galleries_search:
            # Extraire year/month/day de la date si non fournis
            date_str = gallery_data.get('date', galleries_search[gallery_id].get('date', '2000-01-01'))
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                year = gallery_data.get('year', date_obj.year)
                month = gallery_data.get('month', date_obj.month)
                day = gallery_data.get('day', date_obj.day)
            except:
                year = gallery_data.get('year', 2000)
                month = gallery_data.get('month', 1)
                day = gallery_data.get('day', 1)
            
            galleries_search[gallery_id] = {
                'name': gallery_data.get('name', galleries_search[gallery_id].get('name', '')),
                'date': gallery_data.get('date', galleries_search[gallery_id].get('date', '')),
                'description': gallery_data.get('description', galleries_search[gallery_id].get('description', '')),
                'year': year,
                'month': month,
                'day': day
            }
            
            # Sauvegarder
            with open('galleries.json', 'w', encoding='utf-8') as f:
                json.dump(galleries_search, f, ensure_ascii=False, indent=2)
            
            app.logger.info(f"✅ Galerie {gallery_id} mise à jour dans galleries.json (search-only)")
            
            # Mettre à jour le moteur de recherche
            global search_engine
            search_engine = SearchEngine('galleries.json')
        else:
            app.logger.warning(f"Galerie {gallery_id} non trouvée dans galleries.json")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour search-only: {e}")
        raise

def remove_gallery_from_search_only(gallery_id):
    """
    Supprime une galerie de galleries.json.
    """
    try:
        if not os.path.exists('galleries.json'):
            return
        
        with open('galleries.json', 'r', encoding='utf-8') as f:
            galleries_search = json.load(f)
        
        if gallery_id in galleries_search:
            del galleries_search[gallery_id]
            
            with open('galleries.json', 'w', encoding='utf-8') as f:
                json.dump(galleries_search, f, ensure_ascii=False, indent=2)
            
            app.logger.info(f"✅ Galerie {gallery_id} supprimée de galleries.json")
            
            # Mettre à jour le moteur de recherche
            global search_engine
            search_engine = SearchEngine('galleries.json')
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la suppression search-only: {e}")



@app.route('/cached_static/<path:filename>')
def cached_static(filename):
    content = get_cached_static_file(filename)
    return send_file(io.BytesIO(content), mimetype='audio/mp3')


# optimisations images cloudinary 

def get_optimized_cover_url(cover_image_url, width=400, height=300, crop_mode='c_fill'):
    """
    Génère une URL Cloudinary optimisée pour une image de couverture.
    
    Args:
        cover_image_url: URL originale de l'image
        width: Largeur souhaitée (défaut: 400)
        height: Hauteur souhaitée (défaut: 300)
        crop_mode: Mode de crop (défaut: 'c_fill')
    
    Returns:
        URL optimisée ou None si erreur
    """
    if not cover_image_url:
        return None
    
    try:
        # Construire l'URL avec les transformations
        transformations = f'f_auto,q_auto,w_{width},h_{height},{crop_mode}'
        optimized_cover_url = cover_image_url.replace('/upload/', '/upload/' + transformations + '/')
        
        return optimized_cover_url
    except Exception as e:
        app.logger.error(f"Erreur lors de l'optimisation de l'URL de couverture: {e}")
        return None


def get_cloudinary_background_url(image_url, page_type="others"):
    """
    Génère une URL Cloudinary optimisée pour une image de fond.
    Plus d'appels API - simple transformation d'URL.
    """
    try:
        if not image_url or 'cloudinary.com' not in image_url:
            return image_url
        
        # Extraire le nom de l'image depuis l'URL
        url_parts = image_url.split('/upload/')
        if len(url_parts) != 2:
            return image_url
        
        # Définir les transformations selon le type de page
        if page_type == "years":
            transformations = 'f_auto,q_auto,w_2048,c_limit'
        elif page_type == "inmy_life":
            transformations = 'f_auto,q_auto,w_1200,h_800,c_fit'
        else:
            transformations = 'f_auto,q_auto,w_1280,c_limit'
        
        # Construire l'URL optimisée
        base_url = url_parts[0] + '/upload/'
        image_name = url_parts[1]
        
        return f"{base_url}{transformations}/{image_name}"
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'optimisation de l'URL de fond: {e}")
        return image_url

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
    carousel_images = [get_cloudinary_background_url(f"https://res.cloudinary.com/dfuzvu8c5/image/upload/mountain{i}") for i in range(1, 11)]
    return render_template('home.html', carousel_images=carousel_images)


@app.route('/dreams')
def dreams():
   loup_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/loup"
   optimized_url = get_cloudinary_background_url(loup_url)
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
                
                # Ajouter la photo à la galerie
                gallery['photos'].append({
                    'url': result['secure_url']
                })
            except Exception as e:
                app.logger.error(f"Erreur lors de l'upload de {file.filename}: {str(e)}")
                app.logger.error(f"Traceback complet: {traceback.format_exc()}")
                flash(f'Erreur lors du téléchargement de {file.filename}: {str(e)}')
                continue
    
    try:
        save_single_gallery_to_year(gallery_id, gallery)
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
        # Sauvegarder uniquement l'année concernée
        year_file = f"galleries_{year}.json"
        if os.path.exists(year_file):
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
            if gallery_id in year_galleries:
                del year_galleries[gallery_id]
                with open(year_file, 'w', encoding='utf-8') as f:
                    json.dump(year_galleries, f, ensure_ascii=False, indent=2)
                app.logger.info(f"✅ {year_file} mis à jour après suppression")
                
        # Supprimer aussi de galleries.json (search-only)
        remove_gallery_from_search_only(gallery_id)
                
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
    distance = request.form.get('distance')
    denivele = request.form.get('denivele')
    
    # Vérifier l'année de la date pour rediriger vers la bonne page
    year = datetime.strptime(date, '%Y-%m-%d').year
    
    # Utiliser la route year_view avec l'année en paramètre
    return_route = 'year_view'
    
    # Création d'un ID unique pour la galerie
    gallery_id = str(uuid.uuid4())
    
    # Création de la nouvelle galerie - SEULEMENT les champs de recherche
    new_gallery_search = {
        'name': name,
        'date': date,
        'description': description
    }
    
    # Création de la galerie complète pour le fichier annuel
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    new_gallery_full = {
        'name': name,
        'date': date,
        'description': description,
        'distance': float(distance) if distance else None,
        'denivele': int(denivele) if denivele else None,
        'photos': []
    }
    
    # Ajouter les coordonnées GPS déduites automatiquement
    coords, lieu = deduire_coordonnees_gps(name, description, date)
    lat, lon = coords
    new_gallery_full['lat'] = lat
    new_gallery_full['lon'] = lon
    
    # Ajouter les champs de date
    new_gallery_full['year'] = date_obj.year
    new_gallery_full['month'] = date_obj.month
    new_gallery_full['day'] = date_obj.day
    
    app.logger.info(f"Coordonnées déduites pour {name}: {lat:.4f}, {lon:.4f} ({lieu})")
    
    # Gestion du fichier GPX (uniquement en mode dev)
    gpx_processed = False
    if 'gpx_file' in request.files:
        gpx_file = request.files['gpx_file']
        if gpx_file and gpx_file.filename and allowed_gpx_file(gpx_file.filename):
            try:
                app.logger.info(f"Traitement du fichier GPX: {gpx_file.filename}")
                
                # Sauvegarder le fichier GPX temporairement pour le parser
                with tempfile.NamedTemporaryFile(delete=False, suffix='.gpx') as tmp_file:
                    gpx_file.save(tmp_file.name)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Parser le fichier GPX
                    gpx_data = gpx_manager.parse_gpx_file(tmp_file_path)
                    
                    # Créer les données de base de la galerie
                    gallery_base = {
                        'name': name,
                        'date': date,
                        'description': description,
                        'lat': new_gallery_full.get('lat'),
                        'lon': new_gallery_full.get('lon'),
                        'distance': new_gallery_full.get('distance'),
                        'denivele': new_gallery_full.get('denivele')
                    }
                    
                    # Mettre à jour avec les données GPX
                    updated_gallery = gpx_manager.update_gallery_from_gpx(gallery_base, gpx_data)
                    
                    # Générer un nom de fichier unique et le déplacer vers static/gpx
                    gpx_uuid = uuid.uuid4()
                    gpx_filename = f"{gpx_uuid}.gpx"
                    gpx_destination = os.path.join('static', 'gpx', gpx_filename)
                    
                    # Créer le dossier s'il n'existe pas
                    os.makedirs(os.path.dirname(gpx_destination), exist_ok=True)
                    
                    # Déplacer le fichier
                    shutil.move(tmp_file_path, gpx_destination)
                    
                    # Mettre à jour les données de la galerie
                    new_gallery_full['lat'] = updated_gallery['lat']
                    new_gallery_full['lon'] = updated_gallery['lon']
                    new_gallery_full['distance'] = updated_gallery['distance']
                    new_gallery_full['denivele'] = updated_gallery['denivele']
                    new_gallery_full['difficulty'] = updated_gallery['difficulty']
                    new_gallery_full['gpx_file'] = f"/static/gpx/{gpx_filename}"
                    new_gallery_full['gpx_metadata'] = updated_gallery['gpx_metadata']
                    
                    gpx_processed = True
                    app.logger.info(f"✅ GPX traité avec succès: {updated_gallery['distance']}km, {updated_gallery['denivele']}m D+")
                    
                finally:
                    # Nettoyer le fichier temporaire s'il existe encore
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)
                        
            except Exception as e:
                app.logger.error(f"Erreur lors du traitement du GPX: {str(e)}")
                app.logger.error(f"Traceback complet: {traceback.format_exc()}")
                flash("Erreur lors du traitement du fichier GPX", 'warning')
    
    # Si pas de GPX traité, utiliser la déduction automatique des coordonnées
    if not gpx_processed:
        # Ajouter les coordonnées GPS déduites automatiquement
        coords, lieu = deduire_coordonnees_gps(name, description, date)
        lat, lon = coords
        new_gallery_full['lat'] = lat
        new_gallery_full['lon'] = lon
    
    # Gestion de l'image de couverture
    if 'cover_image' in request.files:
        cover_file = request.files['cover_image']
        if cover_file and allowed_file(cover_file.filename):
            try:
                # Upload vers Cloudinary
                upload_result = cloudinary.uploader.upload(cover_file)
                new_gallery_full['cover_image'] = upload_result['secure_url']
            except Exception as e:
                app.logger.error(f"Erreur lors de l'upload Cloudinary: {str(e)}")
                app.logger.error(f"Traceback complet: {traceback.format_exc()}")
                flash("Erreur lors de l'upload de l'image de couverture", 'error')
    
    # Sauvegarder dans les deux systèmes
    try:
        # 1. Sauvegarder la galerie complète dans le fichier annuel
        save_single_gallery_to_year(gallery_id, new_gallery_full)
        
        # 2. Sauvegarder uniquement les champs de recherche dans galleries.json
        save_gallery_to_search_only(gallery_id, {
            'name': name,
            'date': date,
            'description': description,
            'year': date_obj.year,
            'month': date_obj.month,
            'day': date_obj.day
        })
        
        app.logger.info(f"✅ Galerie {gallery_id} sauvegardée dans les deux systèmes")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde des données: {str(e)}")
        app.logger.error(f"Traceback complet: {traceback.format_exc()}")
        flash('Erreur lors de la sauvegarde des données')
        return redirect(url_for(return_route, year=year))
    
    flash('Galerie créée avec succès', 'success')
    return redirect(url_for(return_route, year=year))

@app.route('/edit_gallery/<gallery_id>', methods=['POST'])
def edit_gallery(gallery_id):
    app.logger.info(f"Modification de la galerie {gallery_id}")
    app.logger.info(f"Données reçues: {request.form}")
    
    # Charger uniquement la galerie nécessaire en déterminant son année
    gallery = None
    gallery_year = None
    
    # D'abord essayer de trouver la galerie en chargeant les fichiers un par un
    for year_file in sorted([f for f in os.listdir('.') if f.startswith('galleries_') and f.endswith('.json') and f != 'galleries_index.json']):
        try:
            with open(year_file, 'r', encoding='utf-8') as f:
                year_galleries = json.load(f)
                if gallery_id in year_galleries:
                    gallery = year_galleries[gallery_id]
                    gallery_year = year_file.replace('galleries_', '').replace('.json', '')
                    break
        except Exception as e:
            app.logger.error(f"Erreur lors du chargement de {year_file}: {e}")
            continue
    
    if not gallery:
        flash('Galerie non trouvée')
        return redirect(url_for('year_view', year=2024))
    
    gallery['name'] = request.form.get('name', gallery['name']).strip()
    gallery['description'] = request.form.get('description', '').strip()
    
    # Mettre à jour la distance et le dénivelé
    distance = request.form.get('distance')
    denivele = request.form.get('denivele')
    if distance:
        gallery['distance'] = float(distance)
    elif 'distance' in gallery:
        del gallery['distance']
        
    if denivele:
        gallery['denivele'] = int(denivele)
    elif 'denivele' in gallery:
        del gallery['denivele']
    
    # Mettre à jour la date et gérer le changement d'année
    new_date = request.form.get('date')
    old_year = gallery_year
    new_year = None
    
    if new_date:
        gallery['date'] = new_date
        # PAS de formatted_date - champ inutile
        # Déterminer la nouvelle année
        new_year = datetime.strptime(new_date, '%Y-%m-%d').year
    
    # Si l'année a changé, supprimer de l'ancien fichier
    if new_year and new_year != int(old_year):
        # Supprimer de l'ancien fichier
        old_year_file = f"galleries_{old_year}.json"
        try:
            with open(old_year_file, 'r', encoding='utf-8') as f:
                old_galleries = json.load(f)
            if gallery_id in old_galleries:
                del old_galleries[gallery_id]
                with open(old_year_file, 'w', encoding='utf-8') as f:
                    json.dump(old_galleries, f, ensure_ascii=False, indent=2)
                app.logger.info(f"✅ {gallery_id} supprimée de {old_year_file}")
        except Exception as e:
            app.logger.error(f"Erreur lors de la suppression de {old_year_file}: {e}")
    
    try:
        save_single_gallery_to_year(gallery_id, gallery)
        
        # Mettre à jour galleries.json (search-only)
        update_gallery_in_search_only(gallery_id, {
            'name': gallery['name'],
            'date': gallery['date'],
            'description': gallery['description'],
            'year': gallery.get('year', datetime.strptime(gallery['date'], '%Y-%m-%d').year),
            'month': gallery.get('month', datetime.strptime(gallery['date'], '%Y-%m-%d').month),
            'day': gallery.get('day', datetime.strptime(gallery['date'], '%Y-%m-%d').day)
        })
        
        flash('Galerie mise à jour avec succès')
    except Exception as e:
        app.logger.error(f"Erreur lors de la sauvegarde: {str(e)}")
        app.logger.error(f"Traceback complet: {traceback.format_exc()}")
        flash('Erreur lors de la sauvegarde des modifications')
    
    return redirect(url_for('gallery', gallery_id=gallery_id))


@app.route('/admin/reload-search')
def reload_search():
    """Route admin pour recharger le moteur de recherche"""
    try:
        # Forcer la mise à jour
        update_galleries_json_search()
        return "Moteur de recherche rechargé avec succès !"
    except Exception as e:
        return f"Erreur: {str(e)}", 500

@app.route('/gallery/<gallery_id>')
def gallery(gallery_id):
    page = request.args.get('page', 1, type=int)
    per_page = app.config['PHOTOS_PER_PAGE']
    
    app.logger.info(f"🔍 Recherche de la galerie: {gallery_id}")
    
    # Essayer d'abord avec l'index pour trouver l'année de la galerie
    try:
        index = load_galleries_index()
        gallery_year = None
        
        app.logger.info(f"📋 Index chargé: {len(index)} années")
        
        # Chercher dans quel fichier se trouve la galerie
        for year, gallery_ids in index.items():
            if gallery_id in gallery_ids:
                gallery_year = int(year)
                app.logger.info(f"✅ Galerie trouvée dans l'année: {gallery_year}")
                break
        
        if gallery_year:
            # Chargement ultra-optimisé : uniquement le fichier de l'année
            galleries = load_gallery_data_for_year(gallery_year)
            app.logger.info(f"📁 Fichier {gallery_year} chargé: {len(galleries)} galeries")
        else:
            # Fallback : chargement complet
            galleries = load_gallery_data()
            app.logger.info(f"📁 Chargement complet: {len(galleries)} galeries")
    except Exception as e:
        # En cas d'erreur avec l'index, utiliser le chargement complet
        app.logger.error(f"❌ Erreur avec l'index: {e}")
        galleries = load_gallery_data()
    
    gallery = galleries.get(gallery_id)
    app.logger.info(f"🎯 Galerie trouvée: {gallery is not None}")
    
    if not gallery:
        app.logger.error(f"❌ Galerie non trouvée: {gallery_id}")
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
        corse_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/corse"
        optimized_background_url = get_cloudinary_background_url(corse_url)
        # Get image URL from Cloudinary
        gr20_thumbnail_url = cloudinary.CloudinaryImage("gr20_thumbnail").build_url(secure=True)
         
        return render_template('gallery.html', 
                            gallery=gallery_copy,
                            dev_mode=app.config['DEV_MODE'],
                            format_date=format_date,
                            return_page=return_page,
                            optimized_background_url=optimized_background_url,
                            gr20_thumbnail_url=gr20_thumbnail_url)
    else:
        # Optimize background image URL
        if gallery_copy.get('cover_image'):
            gallery_copy['optimized_background_url'] = get_cloudinary_background_url(gallery_copy['cover_image'])
            gallery_copy['cover_image'] = None # Remove the original image
        else:
            gallery_copy['optimized_background_url'] = None
 
        # Optimisation des URLs Cloudinary
        for photo in gallery_copy['photos']:
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
                            optimized_background_url=gallery_copy.get('optimized_background_url'))
   


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
                    # Construire l'URL complète pour gr20_thumbnail
                    gr20_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/gr20_thumbnail"
                    gallery['optimized_cover_url'] = get_cloudinary_background_url(gr20_url)
                else:
                    # Définir l'image de fond si elle n'est pas déjà définie
                    if not optimized_background_url and gallery.get('cover_image'):
                        optimized_background_url = get_cloudinary_background_url(gallery['cover_image'])

                    # Optimiser l'image de couverture pour la vignette (même logique que year_view)
                    if gallery.get('cover_image'):
                        gallery['optimized_cover_url'] = get_cloudinary_background_url(gallery['cover_image'])
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
    granier_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/granier"
    background_url = get_cloudinary_background_url(granier_url, page_type="years")
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
    from flask import send_file, Response
    try:
        response = send_file(file_path, as_attachment=True, download_name=filename)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        app.logger.error(f"Erreur lors du téléchargement de {filename}: {e}")
        return f"Erreur de téléchargement: {e}", 500

@app.route('/admin/logs')
def view_logs():
    """Affiche les logs récents de l'application (uniquement en dev)"""
    if not app.config.get('DEV_MODE', False):
        return "Non autorisé en production", 403
    
    try:
        # Lire les derniers logs depuis le fichier de logs
        log_file = 'app.log'
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Prendre les 50 dernières lignes
                recent_logs = lines[-50:]
                return '<pre>' + ''.join(recent_logs) + '</pre>'
        else:
            return "Fichier de logs non trouvé", 404
    except Exception as e:
        return f"Erreur de lecture des logs: {e}", 500

@app.route('/admin/sync-all-json')
def sync_all_json():
    """Page de synchronisation de tous les JSON (uniquement en dev)"""
    if not app.config.get('DEV_MODE', False):
        return "Non autorisé en production", 403
    
    import glob
    json_files = glob.glob('galleries_*.json')
    index_files = ['galleries_index.json', 'galleries_by_year.json', 'galleries_metadata.json']
    
    all_files = []
    for file_path in json_files + [f for f in index_files if os.path.exists(f)]:
        file_info = {
            'name': os.path.basename(file_path),
            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
        all_files.append(file_info)
    
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
    if year < 2008 or year > 2026:
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
                    galleries_by_month[month_key]['optimized_cover'] = get_cloudinary_background_url(gallery['cover_image'])
                    app.logger.info(f"Galerie ajoutée pour {year}: {gallery['name']}")
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de la galerie {gallery_id}: {str(e)}")
    
    # Trouver la première image de couverture disponible
    background_url = None
    if galleries_by_month:     
        app.logger.info("Recherche de l'image de fond")
        for month_data in galleries_by_month.values():
            if month_data['cover']:
                background_url = get_cloudinary_background_url(month_data['cover']) if month_data['cover'] else None
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
                        cover_image_url=background_url,  # Ajout pour compatibilité avec le template 2026
                        dev_mode=app.config['DEV_MODE'])

@app.route('/wheel-of-fortune')
def wheel_of_fortune():
    roue_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/roue"
    background_url = get_cloudinary_background_url(roue_url)
    wheel_images = [get_cloudinary_wheel_url(f"roue{i}") for i in range(1, 13)]
    return render_template('wheel_of_fortune.html', dev_mode=app.config['DEV_MODE'], wheel_images=wheel_images, background_url=background_url)


@app.route('/inmy')
def inmy_landing():
    if request.args.get('back') == 'true':
        return redirect(url_for('years'))
    slide_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/slide-img-fall"
    session['slide_url'] = get_cloudinary_background_url(slide_url)
    return render_template('inmy_cover.html', slide_url=session['slide_url'])


import re

def extract_year_from_text(text):
    """Extrait l'année d'un texte de page In My Life"""
    if not text:
        return 9999  # Valeur par défaut pour les pages sans année
    
    # Nettoyer le texte et convertir en minuscules
    clean_text = text.lower().strip()
    
    # Patterns spécifiques pour "années 90", "années 80", etc.
    decade_patterns = [
        r"années?\s+(\d{2})",  # "années 90", "année 80"
    ]
    
    # Patterns pour les années à 2 chiffres
    two_digit_patterns = [
        r"(\d{2})(?=\s|$)",  # Nombre à 2 chiffres suivi d'espace ou fin
        r"'(\d{2})",  # Années comme '76
    ]
    
    # Chercher d'abord les patterns "années XX"
    for pattern in decade_patterns:
        match = re.search(pattern, clean_text)
        if match:
            two_digit_year = int(match.group(1))
            # Convertir en année à 4 chiffres
            if 70 <= two_digit_year <= 99:  # 1970-1999
                return 1900 + two_digit_year
            elif 0 <= two_digit_year <= 30:  # 2000-2030
                return 2000 + two_digit_year
    
    # Chercher les années à 4 chiffres
    four_digit_patterns = [
        r'\b(19|20)\d{2}\b',  # Années 1900-2099 (pattern principal)
    ]
    
    for pattern in four_digit_patterns:
        match = re.search(pattern, clean_text)
        if match:
            year = int(match.group())
            if 1900 <= year <= 2030:
                return year
    
    # Si pas d'année à 4 chiffres, essayer les patterns à 2 chiffres
    for pattern in two_digit_patterns:
        match = re.search(pattern, clean_text)
        if match:
            two_digit_year = int(match.group(1) if match.groups() else match.group())
            # Convertir en année à 4 chiffres
            if 70 <= two_digit_year <= 99:  # 1970-1999
                return 1900 + two_digit_year
            elif 0 <= two_digit_year <= 30:  # 2000-2030
                return 2000 + two_digit_year
    
    return 9999  # Valeur par défaut si aucune année trouvée

def sort_pages_by_year_asc(pages):
    """Trie les pages par ordre d'année croissant (plus anciennes au début)"""
    def get_sort_key(page):
        year = extract_year_from_text(page.get('text', ''))
        return (year, page.get('id', 0))  # Année croissante, puis par ID
    
    return sorted(pages, key=get_sort_key)

@app.route('/inmy_life')
def inmy_life():
    page = request.args.get('page', 1, type=int)
    
    # Load texts from JSON file
    try:
        with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        # Format par défaut si le fichier n'existe pas
        data = {
            "pages": [
                {"id": 1, "text": "", "image": ""},
                {"id": 2, "text": "", "image": ""},
                {"id": 3, "text": "", "image": ""},
                {"id": 4, "text": "", "image": ""},
                {"id": 5, "text": "", "image": ""}
            ],
            "cover": {"text": "Merci d'avoir parcouru ces souvenirs..."}
        }
    
    # Déterminer le nombre total de pages (pages normales + couverture)
    pages_list = data.get('pages', [])
    
    # Trier les pages par ordre d'année croissant (plus anciennes au début)
    sorted_pages = sort_pages_by_year_asc(pages_list)
    
    total_pages = len(sorted_pages) + 1  # +1 pour la couverture
    
    # Validation du numéro de page
    if page < 1 or page > total_pages:
        return redirect(url_for('inmy_life', page=1))
    
    # Préparer les données pour le template
    page_data = None
    cover_text = data.get('cover', {}).get('text', '')
    
    if page <= len(sorted_pages):
        # Page normale : utiliser les pages triées
        page_data = sorted_pages[page - 1]  # -1 car les pages commencent à 1
        
        if page_data:
            image_url = page_data.get('image')
            if image_url:
                # Utiliser l'URL avec transformations Cloudinary optimisées pour In My Life
                page_image_url = get_cloudinary_background_url(image_url, "inmy_life")
            else:
                # Image par défaut basée sur le numéro de page
                default_url = f"https://res.cloudinary.com/dfuzvu8c5/image/upload/inmy_life_page{page}"
                page_image_url = get_cloudinary_background_url(default_url, "inmy_life")
    else:
        # Page de couverture (dernière page)
        page_data = {"text": cover_text}
        page_image_url = None
    
    # Navigation URLs
    prev_url = url_for('inmy_landing') if page == 1 else url_for('inmy_life', page=page-1)
    next_url = url_for('inmy_life', page=page+1) if page < total_pages else None
    
    # Image de fond pour la couverture
    slide_url = session.get('slide_url', get_cloudinary_background_url("https://res.cloudinary.com/dfuzvu8c5/image/upload/slide-img-fall"))
    
    return render_template('inmy_life.html', 
                         page=page,
                         total_pages=total_pages,
                         prev_url=prev_url,
                         next_url=next_url,
                         dev_mode=app.config['DEV_MODE'],
                         page_image_url=page_image_url if page <= len(pages_list) else None,
                         page_text=page_data.get('text', '') if page_data else '',
                         slide_url=slide_url,
                         is_cover_page=(page == total_pages))

@app.route('/save_inmy_life_text', methods=['POST'])
def save_inmy_life_text():
    try:
        data = request.get_json()
        page = data.get('page')
        text = data.get('text')
        is_cover = data.get('is_cover', False)
        
        if not page or text is None:
            return jsonify({'success': False, 'error': 'Page ou texte manquant'})
        
        # Charger le fichier JSON existant
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except FileNotFoundError:
            json_data = {"pages": [], "cover": {"text": ""}}
        
        # S'assurer que le format est correct
        if 'pages' not in json_data:
            json_data['pages'] = []
        if 'cover' not in json_data:
            json_data['cover'] = {"text": ""}
        
        if is_cover:
            # Sauvegarder le texte de la couverture
            json_data['cover']['text'] = text
        else:
            # Sauvegarder le texte de la page normale
            page_index = page - 1
            
            # S'assurer que la page existe
            while len(json_data['pages']) <= page_index:
                json_data['pages'].append({
                    "id": len(json_data['pages']) + 1,
                    "text": "",
                    "image": ""
                })
            
            json_data['pages'][page_index]['text'] = text
        
        # Sauvegarder dans le fichier
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
        
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
    save_single_gallery_to_year(gallery_id, gallery)
    
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
        save_single_gallery_to_year(gallery_id, gallery)
        
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
    """Route pour la carte interactive des randonnées - ULTRA-OPTIMISÉE"""
    # Ne charger aucune donnée côté serveur, tout sera chargé dynamiquement par JavaScript
    return render_template('map.html', hikes_json="[]", dev_mode=app.config.get('DEV_MODE', False))


@app.route('/api/hikes')
def get_hikes_api():
    """API pour récupérer les données des randonnées - OPTIMISÉE"""
    year = request.args.get('year')
    
    if year:
        # Charger une année spécifique
        try:
            year_int = int(year)
            galleries = load_gallery_data_for_year(year_int)
        except ValueError:
            galleries = load_gallery_data_for_year(2026)
    else:
        # Charger toutes les galeries de toutes les années
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
                'cover_image': get_optimized_cover_url(gallery.get('cover_image')) if gallery.get('cover_image') else None,  # Vignette 400x300
                'distance': gallery.get('distance', None),
                'denivele': gallery.get('denivele', None),
                'difficulty': gallery.get('difficulty', 'moyen'),
                'duration': gallery.get('duration', None),
                'gpx_file': gallery.get('gpx_file', None)
            }
            hikes.append(hike_data)
    
    # Trier par date (plus récent en premier)
    hikes.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify(hikes)


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
    if not file.filename.lower().endswith('.gpx'):
        return jsonify({'error': 'Le fichier doit être au format GPX'}), 400
    
    try:
        # Créer le dossier GPX s'il n'existe pas
        gpx_folder = os.path.join(app.static_folder, 'gpx')
        os.makedirs(gpx_folder, exist_ok=True)
        
        # Sauvegarder le fichier
        filename = secure_filename(f"{gallery_id}.gpx")
        filepath = os.path.join(gpx_folder, filename)
        file.save(filepath)
        
        # Valider le fichier GPX
        is_valid, error_msg = gpx_manager.validate_gpx_file(filepath)
        if not is_valid:
            os.remove(filepath)  # Supprimer le fichier invalide
            return jsonify({'error': f'Fichier GPX invalide: {error_msg}'}), 400
        
        # Parser le GPX et extraire les informations
        gpx_info = gpx_manager.parse_gpx_file(filepath)
        
        # Charger uniquement la galerie concernée depuis son fichier annuel (optimisation)
        gallery = None
        # Essayer de trouver l'année en regardant dans les fichiers annuels
        for year in range(2020, 2027):  # Adapter la plage si nécessaire
            year_file = f"galleries_{year}.json"
            if os.path.exists(year_file):
                try:
                    with open(year_file, 'r', encoding='utf-8') as f:
                        year_galleries = json.load(f)
                        if gallery_id in year_galleries:
                            gallery = year_galleries[gallery_id]
                            break
                except:
                    continue
        
        if gallery:
            gallery['gpx_file'] = f'/static/gpx/{filename}'
            
            # Mettre à jour les métadonnées depuis le GPX
            updated_gallery = gpx_manager.update_gallery_from_gpx(
                gallery, gpx_info
            )
            
            save_single_gallery_to_year(gallery_id, updated_gallery)
            
            return jsonify({
                'success': True,
                'gpx_url': f'/static/gpx/{filename}',
                'gpx_info': {
                    'name': gpx_info['name'],
                    'distance': gpx_info.get('total_distance'),
                    'elevation_gain': gpx_info.get('total_elevation_gain'),
                    'track_count': gpx_info.get('track_count'),
                    'point_count': gpx_info.get('total_points')
                }
            })
        else:
            os.remove(filepath)  # Nettoyer le fichier si la galerie n'existe pas
            return jsonify({'error': 'Galerie non trouvée'}), 404
            
    except Exception as e:
        app.logger.error(f"Erreur lors de l'upload du GPX: {str(e)}")
        # Nettoyer le fichier en cas d'erreur
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500


@app.route('/api/hike/<gallery_id>/gpx/info')
def get_hike_gpx_info(gallery_id):
    """Récupérer les informations détaillées du GPX d'une randonnée"""
    galleries = load_gallery_data()
    
    if gallery_id not in galleries:
        return jsonify({'error': 'Randonnée non trouvée'}), 404
    
    gallery = galleries[gallery_id]
    
    if 'gpx_file' not in gallery:
        return jsonify({'error': 'Pas de fichier GPX pour cette randonnée'}), 404
    
    try:
        # Construire le chemin complet du fichier
        gpx_path = os.path.join(app.static_folder, gallery['gpx_file'].replace('/static/', ''))
        
        if not os.path.exists(gpx_path):
            return jsonify({'error': 'Fichier GPX non trouvé'}), 404
        
        # Parser le GPX
        gpx_info = gpx_manager.parse_gpx_file(gpx_path)
        
        # Extraire les coordonnées pour la carte
        coordinates = gpx_manager.extract_track_coordinates(gpx_info)
        segments = gpx_manager.get_track_segments_for_leaflet(gpx_info)
        
        return jsonify({
            'gpx_info': gpx_info,
            'coordinates': coordinates,
            'segments': segments
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la lecture du GPX {gallery_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Cache simple pour éviter les rechargements multiples
_gallery_cache = {}
_cache_timestamp = {}
import time

def get_gallery_from_cache(gallery_id):
    """Récupère une galerie depuis le cache avec expiration de 5 minutes"""
    current_time = time.time()
    
    # Vérifier si le cache est valide
    if gallery_id in _gallery_cache and gallery_id in _cache_timestamp:
        if current_time - _cache_timestamp[gallery_id] < 300:  # 5 minutes
            return _gallery_cache[gallery_id]
    
    # Charger depuis l'année et mettre en cache
    try:
        # Essayer de trouver l'année depuis les fichiers d'index
        year = None
        if os.path.exists('galleries_index.json'):
            with open('galleries_index.json', 'r', encoding='utf-8') as f:
                index = json.load(f)
                for yr, gallery_ids in index.items():
                    if gallery_id in gallery_ids:
                        year = int(yr)
                        break
        
        if year:
            galleries = load_gallery_data_for_year(year)
        else:
            # Fallback : rechercher dans toutes les années
            galleries = {}
            for year_file in sorted([f for f in os.listdir('.') if f.startswith('galleries_') and f.endswith('.json')]):
                try:
                    with open(year_file, 'r', encoding='utf-8') as f:
                        year_galleries = json.load(f)
                        if gallery_id in year_galleries:
                            galleries = year_galleries
                            break
                except:
                    continue
        
        if gallery_id in galleries:
            _gallery_cache[gallery_id] = galleries[gallery_id]
            _cache_timestamp[gallery_id] = current_time
            return galleries[gallery_id]
    except:
        pass
    
    return None

@app.route('/api/hike/<gallery_id>/gpx/track')
def get_hike_gpx_track(gallery_id):
    """Récupérer les coordonnées de la trace GPX pour affichage sur carte - OPTIMISÉ AVEC CACHE"""
    # Utiliser le cache pour éviter les rechargements
    gallery = get_gallery_from_cache(gallery_id)
    
    if not gallery:
        return jsonify({'error': 'Randonnée non trouvée'}), 404
    
    if 'gpx_file' not in gallery:
        return jsonify({'error': 'Pas de fichier GPX pour cette randonnée'}), 404
    
    try:
        # Construire le chemin complet du fichier
        gpx_path = os.path.join(app.static_folder, gallery['gpx_file'].replace('/static/', ''))
        
        if not os.path.exists(gpx_path):
            return jsonify({'error': 'Fichier GPX non trouvé'}), 404
        
        # Parser le GPX et extraire les segments
        gpx_info = gpx_manager.parse_gpx_file(gpx_path)
        segments = gpx_manager.get_track_segments_for_leaflet(gpx_info)
        
        return jsonify({
            'segments': segments,
            'stats': {
                'total_distance': gpx_info.get('total_distance'),
                'elevation_gain': gpx_info.get('total_elevation_gain'),
                'track_count': gpx_info.get('track_count')
            }
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la lecture de la trace GPX {gallery_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/hike/<gallery_id>/gpx/delete', methods=['DELETE'])
def delete_hike_gpx(gallery_id):
    """Supprimer le fichier GPX d'une randonnée"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    galleries = load_gallery_data()
    
    if gallery_id not in galleries:
        return jsonify({'error': 'Randonnée non trouvée'}), 404
    
    gallery = galleries[gallery_id]
    
    if 'gpx_file' not in gallery:
        return jsonify({'error': 'Pas de fichier GPX pour cette randonnée'}), 404
    
    try:
        # Supprimer le fichier physique
        gpx_path = os.path.join(app.static_folder, gallery['gpx_file'].replace('/static/', ''))
        if os.path.exists(gpx_path):
            os.remove(gpx_path)
        
        # Supprimer la référence dans la galerie
        del gallery['gpx_file']
        if 'gpx_metadata' in gallery:
            del gallery['gpx_metadata']
        
        save_single_gallery_to_year(gallery_id, gallery)
        
        return jsonify({'success': True})
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la suppression du GPX {gallery_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/hike/<gallery_id>/gpx/export')
def export_hike_gpx(gallery_id):
    """Exporter le fichier GPX d'une randonnée"""
    galleries = load_gallery_data()
    
    if gallery_id not in galleries:
        return jsonify({'error': 'Randonnée non trouvée'}), 404
    
    gallery = galleries[gallery_id]
    
    if 'gpx_file' not in gallery:
        return jsonify({'error': 'Pas de fichier GPX pour cette randonnée'}), 404
    
    try:
        # Construire le chemin complet du fichier
        gpx_path = os.path.join(app.static_folder, gallery['gpx_file'].replace('/static/', ''))
        
        if not os.path.exists(gpx_path):
            return jsonify({'error': 'Fichier GPX non trouvé'}), 404
        
        # Retourner le fichier pour téléchargement
        return send_file(
            gpx_path,
            as_attachment=True,
            download_name=f"{gallery.get('name', gallery_id)}.gpx",
            mimetype='application/gpx+xml'
        )
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'export du GPX {gallery_id}: {str(e)}")
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
        
        save_single_gallery_to_year(gallery_id, galleries[gallery_id])
        
        return jsonify({'success': True, 'message': 'Coordonnées mises à jour'})
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la mise à jour des coordonnées: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload_inmy_life_photo', methods=['POST'])
def upload_inmy_life_photo():
    """Upload une nouvelle photo pour une page spécifique de In My Life"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'Aucune image sélectionnée'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Nom de fichier vide'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Type de fichier non autorisé'}), 400
        
        page = request.form.get('page', type=int)
        
        if not page or page < 1:
            return jsonify({'error': 'Numéro de page invalide'}), 400
        
        # Upload vers Cloudinary
        upload_result = cloudinary.uploader.upload(file)
        image_url = upload_result['secure_url']
        
        # Charger les données existantes
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"pages": [], "cover": {"text": ""}}
        
        # Vérifier si on essaie de modifier la couverture
        total_pages = len(data.get('pages', [])) + 1  # +1 pour la couverture
        if page >= total_pages:
            return jsonify({'error': 'Impossible de modifier la photo de la couverture'}), 400
        
        # Vérifier si la page existe déjà dans le tableau "pages"
        page_index = page - 1
        
        # Si le format JSON est différent (ancienne structure), adapter
        if 'pages' in data and isinstance(data['pages'], list):
            # Si la page n'existe pas encore, créer une entrée
            while len(data['pages']) <= page_index:
                data['pages'].append({"id": len(data['pages']) + 1, "text": "", "image": ""})
            
            # Mettre à jour l'image de la page
            data['pages'][page_index]['image'] = image_url
        else:
            # Ancien format de données, convertir au nouveau format
            data = {
                "pages": [],
                "cover": {"text": data.get('cover', {}).get('text', "")}
            }
            for i in range(1, 6):
                data['pages'].append({
                    "id": i,
                    "text": data.get(f'text{i}', ''),
                    "image": ""
                })
            data['pages'][page_index]['image'] = image_url
        
        # Sauvegarder les données
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        return jsonify({'success': True, 'image_url': image_url})
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'upload de la photo: {str(e)}")
        return jsonify({'error': f'Erreur lors de l\'upload: {str(e)}'}), 500

@app.route('/add_inmy_life_page', methods=['POST'])
def add_inmy_life_page():
    """Ajoute une nouvelle page avant la couverture"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'Aucune image sélectionnée'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Nom de fichier vide'}), 400
        
        text = request.form.get('text', '')
        
        # Upload vers Cloudinary
        upload_result = cloudinary.uploader.upload(file)
        image_url = upload_result['secure_url']
        
        # Charger les données existantes
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"pages": [], "cover": {"text": ""}}
        
        # S'assurer que le format est correct
        if 'pages' not in data:
            data['pages'] = []
        if 'cover' not in data:
            data['cover'] = {"text": ""}
        
        # Ajouter la nouvelle page avec un ID temporaire
        new_page = {
            "id": len(data['pages']) + 1,
            "text": text,
            "image": image_url
        }
        
        # Ajouter la page temporairement
        data['pages'].append(new_page)
        
        # Toutes les pages par ordre d'année croissant (plus anciennes au début)
        sorted_pages = sort_pages_by_year_asc(data['pages'])
        
        # Trouver la position de la nouvelle page dans l'ordre trié
        new_page_position = None
        for i, page in enumerate(sorted_pages):
            if page['id'] == new_page['id']:
                new_page_position = i + 1  # +1 car les pages commencent à 1
                break
        
        # Mettre à jour les IDs selon le nouvel ordre
        for i, page in enumerate(sorted_pages):
            page['id'] = i + 1
        
        # Sauvegarder avec les pages triées et les IDs mis à jour
        data['pages'] = sorted_pages
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        # Rediriger vers la nouvelle page à sa position correcte
        return jsonify({
            'success': True, 
            'page_number': new_page_position if new_page_position else len(sorted_pages),
            'message': 'Page ajoutée avec succès'
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'ajout de la page: {str(e)}")
        return jsonify({'error': f'Erreur lors de l\'ajout: {str(e)}'}), 500

@app.route('/delete_inmy_life_page', methods=['POST'])
def delete_inmy_life_page():
    """Supprime une page spécifique"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    try:
        page_data = request.get_json()
        page_num = page_data.get('page', type=int)
        
        if not page_num or page_num < 1:
            return jsonify({'error': 'Numéro de page invalide'}), 400
        
        # Charger les données existantes
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return jsonify({'error': 'Fichier de données non trouvé'}), 404
        
        # Vérifier si le format est correct
        if 'pages' not in data or not isinstance(data['pages'], list):
            return jsonify({'error': 'Format de données invalide'}), 400
        
        # Vérifier que la page existe
        if page_num > len(data['pages']):
            return jsonify({'error': 'Page non trouvée'}), 404
        
        # Supprimer la page (index = page_num - 1)
        data['pages'].pop(page_num - 1)
        
        # Réorganiser les IDs des pages restantes
        for i, page in enumerate(data['pages']):
            page['id'] = i + 1
        
        # Sauvegarder les données
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        return jsonify({
            'success': True,
            'message': f'Page {page_num} supprimée avec succès'
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la suppression de la page: {str(e)}")
        return jsonify({'error': f'Erreur lors de la suppression: {str(e)}'}), 500

@app.route('/edit_inmy_life_page', methods=['POST'])
def edit_inmy_life_page():
    """Édite une page spécifique (image et texte)"""
    if not app.config['DEV_MODE']:
        return jsonify({'error': 'Non autorisé en production'}), 403
    
    try:
        page_num = request.form.get('page', type=int)
        
        if not page_num or page_num < 1:
            return jsonify({'error': 'Numéro de page invalide'}), 400
        
        # Charger les données existantes
        try:
            with open('inmy_life_texts.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return jsonify({'error': 'Fichier de données non trouvé'}), 404
        
        # Vérifier si le format est correct
        if 'pages' not in data or not isinstance(data['pages'], list):
            return jsonify({'error': 'Format de données invalide'}), 400
        
        # Vérifier que la page existe
        if page_num > len(data['pages']):
            return jsonify({'error': 'Page non trouvée'}), 404
        
        # Mettre à jour le texte
        text = request.form.get('text', '')
        data['pages'][page_num - 1]['text'] = text
        
        # Mettre à jour l'image si fournie
        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            upload_result = cloudinary.uploader.upload(file)
            data['pages'][page_num - 1]['image'] = upload_result['secure_url']
        
        # Sauvegarder les données
        with open('inmy_life_texts.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        return jsonify({
            'success': True,
            'message': f'Page {page_num} mise à jour avec succès'
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors de l'édition de la page: {str(e)}")
        return jsonify({'error': f'Erreur lors de l\'édition: {str(e)}'}), 500 

@app.route('/stats')
def stats():
    """Page des statistiques des randonnées"""
    granier_url = "https://res.cloudinary.com/dfuzvu8c5/image/upload/granier"
    background_url = get_cloudinary_background_url(granier_url, page_type="years")
    return render_template('stats.html', dev_mode=app.config['DEV_MODE'], background_url=background_url)

@app.route('/api/stats')
def api_stats():
    """API pour récupérer les statistiques"""
    try:
        galleries = load_gallery_data()
        
        # Organiser par année
        yearly_stats = {}
        
        for gallery_id, gallery in galleries.items():
            try:
                date = datetime.strptime(gallery['date'], '%Y-%m-%d')
                year = date.year
                
                if year not in yearly_stats:
                    yearly_stats[year] = {
                        'year': year,
                        'hikes': 0,
                        'photos': 0,
                        'totalKm': 0,
                        'elevation': 0
                    }
                
                yearly_stats[year]['hikes'] += 1
                yearly_stats[year]['photos'] += len(gallery.get('photos', []))
                yearly_stats[year]['totalKm'] += gallery.get('distance', 0) or 0
                yearly_stats[year]['elevation'] += gallery.get('denivele', 0) or 0
                
            except Exception as e:
                app.logger.error(f"Erreur lors du traitement de {gallery_id}: {e}")
                continue
        
        # Convertir en liste et trier par année
        yearly_data = sorted(yearly_stats.values(), key=lambda x: x['year'])
        
        # Calculer les totaux
        total_stats = {
            'totalHikes': sum(y['hikes'] for y in yearly_data),
            'totalPhotos': sum(y['photos'] for y in yearly_data),
            'totalKm': round(sum(y['totalKm'] for y in yearly_data), 1),
            'totalElevation': sum(y['elevation'] for y in yearly_data),
            'yearsActive': len(yearly_data),
            'avgPhotosPerHike': 0,
            'mostActiveYear': max(yearly_data, key=lambda x: x['hikes']) if yearly_data else None,
            'mostPhotogenicYear': max(yearly_data, key=lambda x: x['photos']) if yearly_data else None
        }
        
        if total_stats['totalHikes'] > 0:
            total_stats['avgPhotosPerHike'] = round(total_stats['totalPhotos'] / total_stats['totalHikes'])
        
        return jsonify({
            'yearlyData': yearly_data,
            'totalStats': total_stats
        })
        
    except Exception as e:
        app.logger.error(f"Erreur lors du calcul des statistiques: {str(e)}")
        return jsonify({'error': str(e)}), 500
        
if __name__ == '__main__':
    app.run(debug=True)
