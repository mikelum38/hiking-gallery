#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de test pour vérifier que Sentry fonctionne correctement
"""

import os
import sys

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

def test_sentry_integration():
    """Test l'intégration Sentry"""
    
    with app.test_client() as client:
        print("🧪 Test 1: Route normale")
        response = client.get('/')
        print(f"   Status: {response.status_code}")
        
        print("\n🧪 Test 2: Route qui génère une erreur")
        try:
            response = client.get('/test-sentry')
            print(f"   Status: {response.status_code}")
        except Exception as e:
            print(f"   ✅ Erreur capturée: {e}")
            
        print("\n🧪 Test 3: Route inexistante")
        response = client.get('/route-inexistante')
        print(f"   Status: {response.status_code}")
        
    print("\n📊 Vérifiez votre dashboard Sentry:")
    print("   https://votre-org.sentry.io/projects/hiking-gallery/")
    print("\n⏱️ Attendez 1-2 minutes pour la synchronisation...")

if __name__ == '__main__':
    test_sentry_integration()
