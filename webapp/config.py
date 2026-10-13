"""
Configuration de la webapp Scholarmap

Ce fichier centralise toute la configuration de l'application.
IMPORTANT : Les valeurs sensibles (clés API, DB password) doivent être dans .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Config:
    """Configuration de base pour la webapp"""

    # --- Flask Configuration ---
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # --- Database Configuration (même DB que le projet principal) ---
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/sci_diligence')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Celery Configuration (task queue pour analyses asynchrones) ---
    CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # --- Mode de développement (sans Redis/Celery) ---
    USE_CELERY = os.getenv('USE_CELERY', 'False').lower() == 'true'

    # --- Application Paths ---
    BASE_DIR = Path(__file__).parent.parent  # Racine du projet
    WEBAPP_DIR = Path(__file__).parent  # Dossier webapp
    TEMPLATES_DIR = WEBAPP_DIR / 'templates'
    STATIC_DIR = WEBAPP_DIR / 'static'

    # --- API Keys (héritées du projet principal) ---
    SERPAPI_KEY = os.getenv('SERPAPI_KEY')

    # --- Analysis Configuration ---
    # Timeout maximum pour une analyse (en secondes)
    ANALYSIS_TIMEOUT = int(os.getenv('ANALYSIS_TIMEOUT', '270'))  # 4.5 minutes (sous gunicorn 300s)

    # Mode strict par défaut (utilise mvp_researcher_to_corporate_STRICT.py)
    USE_STRICT_MODE = os.getenv('USE_STRICT_MODE', 'True').lower() == 'true'


class DevelopmentConfig(Config):
    """Configuration pour le développement"""
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    USE_CELERY = False  # Pas de Celery en dev par défaut


class ProductionConfig(Config):
    """Configuration pour la production"""
    DEBUG = False
    # USE_CELERY peut être désactivé pour demo (sans Redis)
    USE_CELERY = os.getenv('USE_CELERY', 'False').lower() == 'true'
    # En production, SECRET_KEY DOIT être définie dans .env
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY')


# Configuration par défaut (basée sur FLASK_ENV)
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Retourne la configuration appropriée selon l'environnement"""
    env = os.getenv('FLASK_ENV', 'development')
    cfg = config.get(env, config['default'])
    # Vérifié ici et non dans le corps de la classe, sinon l'import plante aussi en dev
    if cfg is ProductionConfig and not cfg.SECRET_KEY:
        raise ValueError("FLASK_SECRET_KEY must be set in production!")
    return cfg
