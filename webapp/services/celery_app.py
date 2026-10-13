"""
Configuration Celery pour Scholarmap Webapp

Celery gère les tâches asynchrones (analyses longues) avec Redis comme broker.
"""
import os
from celery import Celery
from pathlib import Path

# Charger la configuration
webapp_dir = Path(__file__).parent.parent
os.chdir(str(webapp_dir))

# Importer la config Flask
import sys
sys.path.insert(0, str(webapp_dir))
from config import get_config

config = get_config()

# Créer l'application Celery (optionnel si USE_CELERY=false)
try:
    if config.USE_CELERY:
        celery_app = Celery(
            'sci_diligence_webapp',
            broker=config.CELERY_BROKER_URL,
            backend=config.CELERY_RESULT_BACKEND,
            include=['webapp.services.tasks']  # Où trouver les tâches
        )
    else:
        # Mode dev : pas de Celery
        celery_app = None
except Exception as e:
    # Si Redis n'est pas disponible, désactiver Celery
    print(f"Warning: Celery disabled - {e}")
    celery_app = None

# Configuration Celery (seulement si activé)
if celery_app:
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,  # Important pour tracking du statut
        task_send_sent_event=True,  # Pour monitoring
        worker_prefetch_multiplier=1,  # Une tâche à la fois
        task_acks_late=True,  # Acknowledge après completion
        task_reject_on_worker_lost=True,
        result_expires=3600,  # Results expire après 1h
    )

if __name__ == '__main__':
    celery_app.start()
