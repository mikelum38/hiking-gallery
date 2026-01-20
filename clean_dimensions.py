#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour nettoyer les dimensions inutiles des fichiers JSON de galeries.
Supprime tous les champs 'width' et 'height' des photos.
"""

import json
import os
import glob

def clean_dimensions_from_json(file_path):
    """Nettoie les dimensions d'un fichier JSON de galeries."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            galleries = json.load(f)
        
        modified_count = 0
        photo_count = 0
        
        for gallery_id, gallery in galleries.items():
            if 'photos' in gallery:
                for photo in gallery['photos']:
                    photo_count += 1
                    # Supprimer les champs width et height
                    if 'width' in photo:
                        del photo['width']
                        modified_count += 1
                    if 'height' in photo:
                        del photo['height']
                        modified_count += 1
        
        # Sauvegarder le fichier nettoyé
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(galleries, f, ensure_ascii=False, indent=2)
        
        print(f"✅ {file_path}: {photo_count} photos, {modified_count} champs supprimés")
        return True
        
    except Exception as e:
        print(f"❌ Erreur avec {file_path}: {e}")
        return False

def main():
    """Fonction principale."""
    print("🧹 Nettoyage des dimensions des fichiers JSON...")
    print("=" * 50)
    
    # Trouver tous les fichiers galleries_YYYY.json
    json_files = glob.glob('galleries_*.json')
    
    if not json_files:
        print("❌ Aucun fichier galleries_YYYY.json trouvé")
        return
    
    total_files = 0
    success_files = 0
    
    for file_path in sorted(json_files):
        total_files += 1
        if clean_dimensions_from_json(file_path):
            success_files += 1
    
    print("=" * 50)
    print(f"🎯 Terminé: {success_files}/{total_files} fichiers traités avec succès")
    print("🚀 Les dimensions sont maintenant complètement supprimées !")

if __name__ == "__main__":
    main()
