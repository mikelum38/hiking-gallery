import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration de l'application"""
    
    # Sécurité
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')
    
    # Application
    DEV_MODE = os.environ.get('DEV_MODE', 'false').lower() == 'true'
    ENV = os.environ.get('FLASK_ENV', 'production')
    
    # Uploads - Augmenté pour 45 photos (environ 500MB)
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Pagination
    PHOTOS_PER_PAGE = 20
    
    # URLs externes
    CHATBOT_URL = os.environ.get('CHATBOT_URL', 'https://chatbot-jitt.onrender.com')
    
    # Monitoring
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    ENABLE_SENTRY = os.environ.get('ENABLE_SENTRY', 'false').lower() == 'true'
    
    @staticmethod
    def validate_config():
        """Valide que toutes les configurations requises sont présentes"""
        required_vars = [
            'FLASK_SECRET_KEY',
            'CLOUDINARY_CLOUD_NAME', 
            'CLOUDINARY_API_KEY',
            'CLOUDINARY_API_SECRET'
        ]
        
        missing = [var for var in required_vars if not os.environ.get(var)]
        if missing:
            raise ValueError(f"Variables d'environnement manquantes: {', '.join(missing)}")
        
        return True


class DevelopmentConfig(Config):
    """Configuration pour le développement"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Configuration pour la production"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Configuration pour les tests"""
    DEBUG = True
    TESTING = True
    SECRET_KEY = 'test-secret-key'  # Clé de test


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig
}
