#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script intelligent pour mettre à jour les dimensions manquantes dans les fichiers galleries JSON
Gère les rate limits Cloudinary et permet la reprise progressive
"""

import json
import os
import cloudinary
import cloudinary.api
from dotenv import load_dotenv
import time
import logging
from datetime import datetime, timedelta

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Configuration Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# Fichier de suivi pour la reprise
PROGRESS_FILE = 'dimensions_update_progress.json'

def load_progress():
    """Charge la progression précédente"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'processed_photos': [], 'start_time': None}

def save_progress(progress):
    """Sauvegarde la progression"""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def get_photo_dimensions_from_api(photo_id, max_retries=3):
    """Récupère les dimensions depuis l'API Cloudinary avec gestion des erreurs"""
    for attempt in range(max_retries):
        try:
            result = cloudinary.api.resource(photo_id)
            return {
                'width': result.get('width', 0),
                'height': result.get('height', 0),
                'success': True
            }
        except Exception as e:
            error_str = str(e)
            
            # Rate limit - attendre jusqu'au reset
            if 'Rate Limit Exceeded' in error_str or 'Error 420' in error_str:
                logger.warning(f"⏰ Rate limit atteint - Pause prolongée...")
                # Attendre 1 heure (ou plus selon le message d'erreur)
                wait_time = 3600  # 1 heure
                logger.info(f"⏳ Attente de {wait_time//60} minutes...")
                time.sleep(wait_time)
                continue
            
            # Autres erreurs
            logger.error(f"Erreur API pour {photo_id}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponentiel
            else:
                return {'width': 0, 'height': 0, 'success': False}
    
    return {'width': 0, 'height': 0, 'success': False}

def extract_photo_id_from_url(url):
    """Extrait le photo_id depuis l'URL Cloudinary"""
    try:
        # Format: https://res.cloudinary.com/cloud_name/image/upload/v1234567890/public_id.jpg
        return url.split('/')[-1].split('.')[0]
    except Exception:
        return None

def update_gallery_file(file_path, dry_run=True, batch_size=50):
    """Met à jour un fichier gallery par lots pour respecter les rate limits"""
    logger.info(f"Traitement de {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        galleries = json.load(f)
    
    progress = load_progress()
    updated_photos = 0
    total_photos_checked = 0
    photos_to_update = []
    
    # Collecter les photos à mettre à jour
    for gallery_id, gallery in galleries.items():
        if 'photos' not in gallery:
            continue
            
        for photo in gallery['photos']:
            total_photos_checked += 1
            photo_id = extract_photo_id_from_url(photo.get('url', ''))
            
            # Vérifier si déjà traitée ou déjà complète
            if not photo_id or photo_id in progress['processed_photos']:
                continue
                
            if 'width' in photo and 'height' in photo and photo['width'] > 0 and photo['height'] > 0:
                progress['processed_photos'].append(photo_id)
                continue
            
            photos_to_update.append({
                'gallery_id': gallery_id,
                'photo': photo,
                'photo_id': photo_id
            })
    
    logger.info(f"Photos à mettre à jour dans {file_path}: {len(photos_to_update)}")
    
    # Traiter par lots
    for i in range(0, len(photos_to_update), batch_size):
        batch = photos_to_update[i:i + batch_size]
        logger.info(f"Traitement du lot {i//batch_size + 1}/{(len(photos_to_update)-1)//batch_size + 1} ({len(batch)} photos)")
        
        for item in batch:
            photo = item['photo']
            photo_id = item['photo_id']
            
            # Récupérer les dimensions
            dimensions = get_photo_dimensions_from_api(photo_id)
            
            if dimensions['success'] and dimensions['width'] > 0 and dimensions['height'] > 0:
                if not dry_run:
                    photo['width'] = dimensions['width']
                    photo['height'] = dimensions['height']
                updated_photos += 1
                logger.info(f"✅ {photo_id}: {dimensions['width']}x{dimensions['height']}")
            else:
                logger.warning(f"❌ {photo_id}: dimensions non récupérées")
            
            # Marquer comme traitée
            progress['processed_photos'].append(photo_id)
            
            # Pause entre les appels API
            time.sleep(0.2)  # 5 appels/secondes max
        
        # Sauvegarder la progression après chaque lot
        save_progress(progress)
        
        # Pause entre les lots
        if i + batch_size < len(photos_to_update):
            logger.info("⏸️ Pause de 10 secondes entre les lots...")
            time.sleep(10)
    
    # Sauvegarder le fichier si des modifications ont été faites
    if updated_photos > 0 and not dry_run:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(galleries, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 {file_path} mis à jour ({updated_photos} photos)")
    
    return total_photos_checked, updated_photos

def main():
    """Fonction principale"""
    dry_run = True  # Mettre à False pour exécuter réellement les modifications
    
    logger.info("=== MISE À JOUR INTELLIGENTE DES DIMENSIONS ===")
    logger.info(f"Mode: {'DRY RUN (simulation)' if dry_run else 'EXÉCUTION RÉELLE'}")
    
    progress = load_progress()
    if progress['start_time']:
        logger.info(f"Reprise de la progression précédente")
    else:
        progress['start_time'] = datetime.now().isoformat()
        save_progress(progress)
    
    total_photos = 0
    total_updated = 0
    files_processed = 0
    
    # Traiter tous les fichiers galleries_YYYY.json
    for file in sorted(os.listdir('.')):
        if file.startswith('galleries_') and file.endswith('.json') and file not in ['galleries_index.json', 'galleries_metadata.json']:
            photos_checked, photos_updated = update_gallery_file(file, dry_run)
            total_photos += photos_checked
            total_updated += photos_updated
            files_processed += 1
    
    logger.info(f"\n=== RÉSULTATS ===")
    logger.info(f"Fichiers traités: {files_processed}")
    logger.info(f"Photos vérifiées: {total_photos}")
    logger.info(f"Photos mises à jour: {total_updated}")
    logger.info(f"Photos déjà traitées: {len(progress['processed_photos'])}")
    
    if dry_run and total_updated > 0:
        logger.info(f"\n⚠️  Mode DRY RUN - Aucune modification effectuée")
        logger.info(f"Pour exécuter réellement, modifiez dry_run = False dans le script")
    elif not dry_run:
        logger.info(f"\n✅ Mise à jour terminée - {total_updated} photos modifiées")
        # Nettoyer le fichier de progression
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            logger.info("🗑️ Fichier de progression supprimé")
    else:
        logger.info(f"\n✅ Toutes les photos ont déjà leurs dimensions!")

if __name__ == '__main__':
    main()
