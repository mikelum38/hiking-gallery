#!/usr/bin/env python3
"""
Script de test pour vérifier l'intégration des distances et dénivelés
"""

import json
import os
from app import load_gallery_data, save_gallery_data

def test_distance_integration():
    """Teste l'ajout de distance et dénivelé à une galerie existante"""
    
    print("🧪 Test d'intégration des distances et dénivelés...")
    
    # Charger les données existantes
    galleries = load_gallery_data()
    
    # Trouver une galerie de test
    test_gallery_id = None
    for gid, gallery in galleries.items():
        if 'distance' not in gallery and 'denivele' not in gallery:
            test_gallery_id = gid
            break
    
    if not test_gallery_id:
        print("❌ Aucune galerie trouvée pour le test")
        return
    
    print(f"✅ Galerie de test trouvée : {galleries[test_gallery_id]['name']}")
    
    # Ajouter des données de test
    galleries[test_gallery_id]['distance'] = 15.5
    galleries[test_gallery_id]['denivele'] = 850
    
    # Sauvegarder
    try:
        save_gallery_data(galleries)
        print("✅ Données sauvegardées avec succès")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")
        return
    
    # Vérifier la sauvegarde
    galleries_reloaded = load_gallery_data()
    test_gallery = galleries_reloaded[test_gallery_id]
    
    if test_gallery.get('distance') == 15.5 and test_gallery.get('denivele') == 850:
        print("✅ Intégration réussie !")
        print(f"   - Distance : {test_gallery.get('distance')} km")
        print(f"   - Dénivelé : {test_gallery.get('denivele')} m")
    else:
        print("❌ Échec de l'intégration")
    
    # Nettoyer les données de test
    del galleries[test_gallery_id]['distance']
    del galleries[test_gallery_id]['denivele']
    save_gallery_data(galleries)
    print("🧹 Données de test nettoyées")

if __name__ == "__main__":
    test_distance_integration()
