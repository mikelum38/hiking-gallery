#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour estimer le nombre d'appels API nécessaires et planifier la mise à jour
"""

import json
import os

def estimate_api_calls():
    """Estime le nombre d'appels API nécessaires"""
    total_photos = 0
    photos_without_dims = 0
    files_with_missing = []
    
    print("=== ESTIMATION DES APPELS API NÉCESSAIRES ===\n")
    
    for file in sorted(os.listdir('.')):
        if file.startswith('galleries_') and file.endswith('.json') and file not in ['galleries_index.json', 'galleries_metadata.json']:
            print(f'Analyse de {file}...', end=' ')
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    galleries = json.load(f)
                
                file_total = 0
                file_missing = 0
                for gallery_id, gallery in galleries.items():
                    if 'photos' in gallery:
                        for photo in gallery['photos']:
                            file_total += 1
                            total_photos += 1
                            if 'width' not in photo or 'height' not in photo or photo['width'] == 0 or photo['height'] == 0:
                                file_missing += 1
                                photos_without_dims += 1
                
                if file_missing > 0:
                    files_with_missing.append((file, file_missing))
                    print(f'{file_missing}/{file_total} photos sans dimensions')
                else:
                    print('✅ Toutes complètes')
                    
            except Exception as e:
                print(f'ERREUR: {e}')
    
    print(f'\n=== RÉSUMÉ ===')
    print(f'Total photos: {total_photos}')
    print(f'Photos sans dimensions: {photos_without_dims}')
    print(f'Pourcentage: {(photos_without_dims/total_photos*100):.1f}%')
    print(f'Appels API nécessaires: {photos_without_dims}')
    
    # Estimation du temps
    api_per_hour = 500  # Limite Cloudinary
    api_per_second = 5  # Sécurité
    hours_needed = photos_without_dims / api_per_hour
    seconds_needed = photos_without_dims / api_per_second
    
    print(f'\n=== ESTIMATION TEMPS ===')
    print(f'Limite Cloudinary: {api_per_hour} appels/heure')
    print(f'Notre limite: {api_per_second} appels/seconde')
    print(f'Temps minimum: {hours_needed:.1f} heures')
    print(f'Temps avec notre limite: {seconds_needed/3600:.1f} heures')
    
    if photos_without_dims > 0:
        print(f'\n=== RECOMMANDATION ===')
        if photos_without_dims <= 100:
            print("✅ Peut être fait en une seule session")
        elif photos_without_dims <= 500:
            print("⚠️  Faire en 2-3 sessions pour éviter les rate limits")
        else:
            print("🔄 Utiliser le script intelligent avec reprise automatique")
            print("   → python update_dimensions_smart.py")
    
    if files_with_missing:
        print(f'\nFichiers avec photos sans dimensions:')
        for file, count in files_with_missing:
            print(f'  {file}: {count} photos')

if __name__ == '__main__':
    estimate_api_calls()
