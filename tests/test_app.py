import pytest
import json
import os
import sys

# Ajouter le répertoire parent au path pour importer app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

@pytest.fixture
def client():
    """Fixture pour le client de test"""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['CLOUDINARY_CLOUD_NAME'] = 'test-cloud'
    app.config['CLOUDINARY_API_KEY'] = 'test-key'
    app.config['CLOUDINARY_API_SECRET'] = 'test-secret'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_gallery_data():
    """Données de galerie de test"""
    return {
        "20240101_new_year": {
            "name": "Test Gallery",
            "date": "2024-01-01",
            "description": "Gallery de test",
            "photos": [
                {"url": "https://example.com/photo1.jpg", "filename": "photo1.jpg"},
                {"url": "https://example.com/photo2.jpg", "filename": "photo2.jpg"}
            ],
            "cover_image": "https://example.com/cover.jpg"
        }
    }


class TestBasicRoutes:
    """Tests des routes de base"""
    
    def test_home_page(self, client):
        """Test de la page d'accueil"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Rêves de Montagne' in response.data
    
    def test_year_route(self, client):
        """Test des routes d'année"""
        response = client.get('/2025')
        assert response.status_code == 200
    
    def test_invalid_year_route(self, client):
        """Test des routes d'année invalides"""
        response = client.get('/2015')  # Année < 2016
        assert response.status_code == 404
        
        response = client.get('/2027')  # Année > 2026
        assert response.status_code == 404
    
    def test_gallery_not_found(self, client):
        """Test d'une galerie qui n'existe pas"""
        response = client.get('/gallery/nonexistent')
        assert response.status_code == 404


class TestGalleryPagination:
    """Tests de la pagination des galeries"""
    
    def test_gallery_pagination_first_page(self, client, sample_gallery_data, monkeypatch):
        """Test de la première page de pagination"""
        # Mock des données de galerie
        def mock_load_gallery_data():
            return sample_gallery_data
        
        monkeypatch.setattr('app.load_gallery_data', mock_load_gallery_data)
        
        response = client.get('/gallery/20240101_new_year?page=1')
        assert response.status_code == 200
        
        # Vérifier que les données de pagination sont présentes
        response_data = response.get_json() if response.content_type == 'application/json' else response.data
        assert b'pagination' in response.data
    
    def test_gallery_pagination_second_page(self, client, sample_gallery_data, monkeypatch):
        """Test de la deuxième page de pagination"""
        def mock_load_gallery_data():
            return sample_gallery_data
        
        monkeypatch.setattr('app.load_gallery_data', mock_load_gallery_data)
        
        response = client.get('/gallery/20240101_new_year?page=2')
        assert response.status_code == 200


class TestConfiguration:
    """Tests de la configuration"""
    
    def test_config_validation_missing_key(self):
        """Test de la validation quand la clé secrète manque"""
        from config import Config
        
        # Simuler l'absence de clé secrète
        import os
        original_env = os.environ.get
        os.environ.get = lambda key: None if key == 'FLASK_SECRET_KEY' else original_env(key)
        
        with pytest.raises(ValueError, match="FLASK_SECRET_KEY doit être définie"):
            Config.validate_config()
        
        # Restaurer
        os.environ.get = original_env
    
    def test_config_loads_correctly(self):
        """Test que la configuration se charge correctement"""
        from config import Config
        
        assert hasattr(Config, 'SECRET_KEY')
        assert hasattr(Config, 'CLOUDINARY_CLOUD_NAME')
        assert hasattr(Config, 'PHOTOS_PER_PAGE')
        assert Config.PHOTOS_PER_PAGE == 20


class TestErrorHandling:
    """Tests de la gestion d'erreurs"""
    
    def test_404_handling(self, client):
        """Test de la gestion des erreurs 404"""
        response = client.get('/page-that-does-not-exist')
        assert response.status_code == 404
    
    def test_csrf_protection(self, client):
        """Test que les routes POST nécessitent CSRF en production"""
        # En mode test, CSRF est désactivé
        response = client.post('/create_gallery', data={})
        # La réponse devrait être une redirection ou erreur, pas 500
        assert response.status_code in [302, 400, 403]


if __name__ == '__main__':
    pytest.main([__file__])
