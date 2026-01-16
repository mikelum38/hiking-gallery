#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour déboguer le choix de l'image de fond
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

def debug_background_2025():
    """Déboguer le choix de l'image de fond pour 2025"""
    
    print("🔍 Analyse des galeries 2025 pour l'image de fond:\n")
    
    galleries_by_month = {}
    
    for gallery_id, gallery in galleries.items():
        try:
            date = datetime.strptime(gallery['date'], '%Y-%m-%d')
            if date.year == 2025:
                month_key = f"{MOIS_FR[date.month-1]} {date.year}"
                
                if month_key not in galleries_by_month:
                    galleries_by_month[month_key] = {
                        'galleries': [],
                        'cover': None,
                        'first_gallery': None
                    }
                
                galleries_by_month[month_key]['galleries'].append({
                    'id': gallery_id,
                    'name': gallery.get('name', 'Sans nom'),
                    'cover_image': gallery.get('cover_image'),
                    'date': gallery['date']
                })
                
                # Prendre la première galerie avec cover_image
                if not galleries_by_month[month_key]['cover'] and gallery.get('cover_image'):
                    galleries_by_month[month_key]['cover'] = gallery['cover_image']
                    galleries_by_month[month_key]['first_gallery'] = gallery_id
                    
        except Exception as e:
            print(f"❌ Erreur galerie {gallery_id}: {e}")
    
    # Afficher l'analyse
    print("📅 Mois avec galeries en 2025:")
    for month_key in MOIS_FR:
        month_full = f"{month_key} 2025"
        if month_full in galleries_by_month:
            month_data = galleries_by_month[month_full]
            print(f"\n🗓️  {month_key}:")
            print(f"   📸 Cover: {month_data['cover'] or 'Aucune'}")
            print(f"   🎯 Première galerie: {month_data['first_gallery'] or 'Aucune'}")
            print(f"   📊 Nombre de galeries: {len(month_data['galleries'])}")
    
    # Simuler le choix de l'image de fond
    print("\n🎨 Simulation du choix de l'image de fond:")
    background_url = None
    chosen_month = None
    
    for month_key in MOIS_FR:
        month_full = f"{month_key} 2025"
        if month_full in galleries_by_month:
            month_data = galleries_by_month[month_full]
            if month_data['cover']:
                background_url = month_data['cover']
                chosen_month = month_key
                print(f"✅ {month_key} choisi avec l'image: {background_url}")
                break
    
    if not background_url:
        print("❌ Aucune image de fond trouvée pour 2025")
    
    print(f"\n🏆 Résultat final: {chosen_month or 'Aucun'} → {background_url or 'Aucune image'}")

if __name__ == '__main__':
    debug_background_2025()
