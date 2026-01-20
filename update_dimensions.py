#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour mettre à jour les dimensions manquantes dans tous les fichiers galleries JSON
Utilise l'API Cloudinary pour récupérer les dimensions et les stocker directement
"""

import json
import os
import cloudinary
import cloudinary.api
from dotenv import load_dotenv
import time
import logging

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

def get_photo_dimensions_from_api(photo_id):
    """Récupère les dimensions depuis l'API Cloudinary"""
    try:
        result = cloudinary.api.resource(photo_id)
        return {
            'width': result.get('width', 0),
            'height': result.get('height', 0)
        }
    except Exception as e:
        logger.error(f"Erreur API pour {photo_id}: {e}")
        return {'width': 0, 'height': 0}

def extract_photo_id_from_url(url):
    """Extrait le photo_id depuis l'URL Cloudinary"""
    try:
        # Format: https://res.cloudinary.com/cloud_name/image/upload/v1234567890/public_id.jpg
        return url.split('/')[-1].split('.')[0]
    except Exception:
        return None

def update_gallery_file(file_path, dry_run=True):
    """Met à jour un fichier gallery avec les dimensions manquantes"""
    logger.info(f"Traitement de {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        galleries = json.load(f)
    
    updated_photos = 0
    total_photos_checked = 0
    
    for gallery_id, gallery in galleries.items():
        if 'photos' not in gallery:
            continue
            
        for photo in gallery['photos']:
            total_photos_checked += 1
            
            # Vérifier si les dimensions sont déjà présentes
            if 'width' in photo and 'height' in photo and photo['width'] > 0 and photo['height'] > 0:
                continue
            
            # Extraire le photo_id depuis l'URL
            photo_id = extract_photo_id_from_url(photo.get('url', ''))
            if not photo_id:
                logger.warning(f"Impossible d'extraire photo_id depuis: {photo.get('url', '')}")
                continue
            
            # Récupérer les dimensions depuis l'API
            dimensions = get_photo_dimensions_from_api(photo_id)
            
            if dimensions['width'] > 0 and dimensions['height'] > 0:
                if not dry_run:
                    photo['width'] = dimensions['width']
                    photo['height'] = dimensions['height']
                updated_photos += 1
                logger.info(f"✅ {photo_id}: {dimensions['width']}x{dimensions['height']}")
            else:
                logger.warning(f"❌ {photo_id}: dimensions non récupérées")
            
            # Pause pour éviter de surcharger l'API
            time.sleep(0.1)
    
    # Sauvegarder le fichier si des modifications ont été faites
    if updated_photos > 0 and not dry_run:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(galleries, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 {file_path} mis à jour ({updated_photos} photos)")
    
    return total_photos_checked, updated_photos

def main():
    """Fonction principale"""
    dry_run = True  # Mettre à False pour exécuter réellement les modifications
    
    logger.info("=== MISE À JOUR DES DIMENSIONS DES PHOTOS ===")
    logger.info(f"Mode: {'DRY RUN (simulation)' if dry_run else 'EXÉCUTION RÉELLE'}")
    
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
    logger.info(f"Photos à mettre à jour: {total_updated}")
    
    if dry_run and total_updated > 0:
        logger.info(f"\n⚠️  Mode DRY RUN - Aucune modification effectuée")
        logger.info(f"Pour exécuter réellement, modifiez dry_run = False dans le script")
    elif not dry_run:
        logger.info(f"\n✅ Mise à jour terminée - {total_updated} photos modifiées")
    else:
        logger.info(f"\n✅ Toutes les photos ont déjà leurs dimensions!")

if __name__ == '__main__':
    main()
