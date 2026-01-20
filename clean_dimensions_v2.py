#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script simple pour nettoyer les dimensions des fichiers JSON.
"""

import json
import os
import glob

def clean_json_file(file_path):
    """Nettoie les dimensions d'un fichier JSON."""
    print(f"🔧 Nettoyage de {file_path}...")
    
    try:
        # Lire le fichier
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Compter les modifications
        removed_fields = 0
        photos_processed = 0
        
        # Parcourir toutes les galeries
        for gallery_id, gallery in data.items():
            if 'photos' in gallery and isinstance(gallery['photos'], list):
                for photo in gallery['photos']:
                    photos_processed += 1
                    
                    # Supprimer width
                    if 'width' in photo:
                        del photo['width']
                        removed_fields += 1
                        print(f"  ❌ Supprimé width de {photo.get('url', 'unknown')[:50]}...")
                    
                    # Supprimer height  
                    if 'height' in photo:
                        del photo['height']
                        removed_fields += 1
                        print(f"  ❌ Supprimé height de {photo.get('url', 'unknown')[:50]}...")
        
        # Sauvegarder le fichier modifié
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ {file_path}: {photos_processed} photos, {removed_fields} champs supprimés")
        return True
        
    except Exception as e:
        print(f"❌ Erreur avec {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Fonction principale."""
    print("🧹 NETTOYAGE DES DIMENSIONS DES JSON")
    print("=" * 60)
    
    # Trouver tous les fichiers galleries_*.json
    json_files = glob.glob('galleries_*.json')
    
    if not json_files:
        print("❌ Aucun fichier galleries_YYYY.json trouvé")
        return
    
    print(f"📁 Fichiers trouvés: {len(json_files)}")
    print()
    
    success_count = 0
    
    for file_path in sorted(json_files):
        if clean_json_file(file_path):
            success_count += 1
        print()
    
    print("=" * 60)
    print(f"🎯 TERMINÉ: {success_count}/{len(json_files)} fichiers nettoyés avec succès")
    print("🚀 Toutes les dimensions ont été supprimées !")

if __name__ == "__main__":
    main()
