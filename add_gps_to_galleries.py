#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour ajouter des coordonnées GPS aux galeries existantes
Usage: python add_gps_to_galleries.py
"""

import json

# Coordonnées GPS des principaux sommets de la région (Chartreuse, Vercors, etc.)
KNOWN_LOCATIONS = {
    # Chartreuse
    'chamechaude': {'lat': 45.2833, 'lon': 5.7833, 'elevation': 2082},
    'dent de crolles': {'lat': 45.3167, 'lon': 5.8500, 'elevation': 2062},
    'granier': {'lat': 45.4333, 'lon': 5.9167, 'elevation': 1933},
    'grande sure': {'lat': 45.2500, 'lon': 5.7000, 'elevation': 1920},
    'charmant som': {'lat': 45.2833, 'lon': 5.7500, 'elevation': 1867},
    'petit som': {'lat': 45.2667, 'lon': 5.7333, 'elevation': 1772},
    'pinet': {'lat': 45.3333, 'lon': 5.8000, 'elevation': 1867},
    
    # Vercors
    'moucherotte': {'lat': 45.1500, 'lon': 5.6333, 'elevation': 1901},
    'grand veymont': {'lat': 44.8667, 'lon': 5.5167, 'elevation': 2341},
    
    # Belledonne
    'croix de belledonne': {'lat': 45.3000, 'lon': 6.0833, 'elevation': 2926},
    'rocher blanc': {'lat': 45.1833, 'lon': 6.0167, 'elevation': 2928},
    
    # Autres
    'pilat': {'lat': 45.3667, 'lon': 4.6000, 'elevation': 1432},
}

def normalize_name(name):
    """Normaliser un nom de sommet pour la recherche"""
    return name.lower().strip()

def find_coordinates(gallery_name):
    """Trouver les coordonnées d'une galerie basée sur son nom"""
    normalized = normalize_name(gallery_name)
    
    # Chercher une correspondance dans les locations connues
    for location, coords in KNOWN_LOCATIONS.items():
        if location in normalized:
            return coords
    
    return None

def add_gps_to_galleries():
    """Ajouter des coordonnées GPS aux galeries existantes"""
    
    print("Chargement de galleries.json...")
    try:
        with open('galleries.json', 'r', encoding='utf-8') as f:
            galleries = json.load(f)
    except FileNotFoundError:
        print("❌ Fichier galleries.json non trouvé!")
        return
    
    print(f"✓ {len(galleries)} galeries chargées\n")
    
    updated_count = 0
    not_found = []
    
    for gallery_id, gallery in galleries.items():
        name = gallery.get('name', '')
        
        # Vérifier si la galerie a déjà des coordonnées
        if 'lat' in gallery and 'lon' in gallery:
            print(f"⏭️  {name}: Coordonnées déjà présentes")
            continue
        
        # Chercher les coordonnées
        coords = find_coordinates(name)
        
        if coords:
            gallery['lat'] = coords['lat']
            gallery['lon'] = coords['lon']
            if 'elevation' in coords:
                gallery['elevation'] = coords['elevation']
            
            # Estimer des valeurs par défaut pour les autres champs
            if 'difficulty' not in gallery:
                # Basé sur l'élévation
                elevation = coords.get('elevation', 0)
                if elevation > 2500:
                    gallery['difficulty'] = 'difficile'
                elif elevation > 2000:
                    gallery['difficulty'] = 'moyen'
                else:
                    gallery['difficulty'] = 'facile'
            
            print(f"✓ {name}: Coordonnées ajoutées ({coords['lat']}, {coords['lon']})")
            updated_count += 1
        else:
            print(f"⚠️  {name}: Coordonnées non trouvées")
            not_found.append(name)
    
    # Sauvegarder le fichier mis à jour
    if updated_count > 0:
        print(f"\n💾 Sauvegarde de {updated_count} galeries mises à jour...")
        with open('galleries.json', 'w', encoding='utf-8') as f:
            json.dump(galleries, f, ensure_ascii=False, indent=4)
        print("✓ Fichier sauvegardé!")
    
    # Afficher le résumé
    print(f"\n{'='*60}")
    print(f"📊 RÉSUMÉ")
    print(f"{'='*60}")
    print(f"Total de galeries: {len(galleries)}")
    print(f"Galeries mises à jour: {updated_count}")
    print(f"Galeries non trouvées: {len(not_found)}")
    
    if not_found:
        print(f"\n⚠️  Galeries sans coordonnées:")
        for name in not_found:
            print(f"   - {name}")
        print("\n💡 Vous pouvez ajouter manuellement les coordonnées pour ces galeries")

def add_location_manually(gallery_id, lat, lon, **kwargs):
    """Ajouter manuellement des coordonnées à une galerie"""
    with open('galleries.json', 'r', encoding='utf-8') as f:
        galleries = json.load(f)
    
    if gallery_id not in galleries:
        print(f"❌ Galerie {gallery_id} non trouvée")
        return
    
    galleries[gallery_id]['lat'] = lat
    galleries[gallery_id]['lon'] = lon
    
    # Ajouter des informations supplémentaires
    for key, value in kwargs.items():
        galleries[gallery_id][key] = value
    
    with open('galleries.json', 'w', encoding='utf-8') as f:
        json.dump(galleries, f, ensure_ascii=False, indent=4)
    
    print(f"✓ Coordonnées ajoutées pour {galleries[gallery_id]['name']}")

if __name__ == "__main__":
    print("="*60)
    print("🗺️  AJOUT DE COORDONNÉES GPS AUX GALERIES")
    print("="*60)
    print()
    
    add_gps_to_galleries()
    
    print("\n" + "="*60)
    print("Terminé!")
    print("="*60)
    
    # Exemple d'utilisation pour ajout manuel
    print("\n💡 Pour ajouter manuellement des coordonnées:")
    print("   add_location_manually('gallery_id', 45.123, 5.456, distance=10.5, denivele=800)")