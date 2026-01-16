#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vérifie les cover_image pour chaque mois 2025
"""

import json
from datetime import datetime

# Charger les données
with open('galleries.json', 'r', encoding='utf-8') as f:
    galleries = json.load(f)

MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

def check_covers_2025():
    """Vérifie les cover_image pour chaque mois 2025"""
    
    print("🖼️ Cover images par mois pour 2025:\n")
    
    galleries_by_month = {}
    
    # Simuler la logique de year_view
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2025:
                month_key = f"{MOIS_FR[date.month-1]} {date.year}"
                
                if month_key not in galleries_by_month:
                    galleries_by_month[month_key] = {
                        'galleries': [],
                        'cover': None,
                        'first_gallery_with_cover': None
                    }
                
                galleries_by_month[month_key]['galleries'].append({
                    'id': gallery_id,
                    'name': gallery.get('name', 'Sans nom'),
                    'date': gallery['date'],
                    'has_cover': bool(gallery.get('cover_image'))
                })
                
                # Logique de sélection de la cover
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                    galleries_by_month[month_key]['first_gallery_with_cover'] = gallery_id
                    
        except Exception as e:
            print(f"❌ Erreur galerie {gallery_id}: {e}")
    
    # Afficher les résultats
    for month_key in MOIS_FR:
        month_full = f"{month_key} 2025"
        if month_full in galleries_by_month:
            month_data = galleries_by_month[month_full]
            print(f"🗓️  {month_key}:")
            print(f"   📸 Cover: {'✅' if month_data['cover'] else '❌ Aucune'}")
            if month_data['cover']:
                print(f"   🎯 Galerie: {month_data['first_gallery_with_cover']}")
                print(f"   🔗 URL: {month_data['cover']}")
            print(f"   📊 Total galeries: {len(month_data['galleries'])}")
            
            # Galeries avec cover
            with_cover = [g for g in month_data['galleries'] if g['has_cover']]
            if with_cover:
                print(f"   📝 Galeries avec cover: {len(with_cover)}")
                for g in with_cover[:3]:  # Limiter à 3
                    print(f"      - {g['name']} ({g['date']})")
            print()
    
    # Image de fond choisie
    print("🎨 Image de fond choisie pour 2025:")
    background_url = None
    chosen_month = None
    
    for month_key in MOIS_FR:
        month_full = f"{month_key} 2025"
        if month_full in galleries_by_month:
            month_data = galleries_by_month[month_full]
            if month_data['cover']:
                background_url = month_data['cover']
                chosen_month = month_key
                print(f"✅ {month_key} → {background_url}")
                break
    
    if not background_url:
        print("❌ Aucune image de fond trouvée - tous les mois sans cover_image")

if __name__ == '__main__':
    check_covers_2025()
