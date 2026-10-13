"""
Tâches Celery pour les analyses de chercheurs

Ces tâches s'exécutent en arrière-plan et peuvent être surveillées via leur task_id.
"""
from celery import current_task
from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Setup path pour imports
webapp_dir = Path(__file__).parent.parent
sys.path.insert(0, str(webapp_dir))

from services.celery_app import celery_app
from services.researcher_analyzer import analyze_researcher, AnalysisProgress
from src.logger import logger


# Ne définir la tâche que si Celery est activé
if celery_app is None:
    # Mode dev/demo sans Celery - pas de tâche définie
    analyze_researcher_task = None
else:
    # Mode production avec Celery
    @celery_app.task(bind=True, name='webapp.analyze_researcher')
    def analyze_researcher_task(
        self,
        researcher_name: str,
        scholar_id: Optional[str] = None,
        max_coauthors: int = 5
    ) -> Dict[str, Any]:
        """
        Tâche Celery pour analyser un chercheur

        Args:
            self: Tâche Celery (bind=True permet d'accéder à self.update_state)
            researcher_name: Nom du chercheur
            scholar_id: ID Scholar optionnel
            max_coauthors: Nombre max de co-auteurs

        Returns:
            Dict avec les résultats de l'analyse
        """
        logger.info(f"Starting analysis for: {researcher_name}")

        def progress_callback(progress: AnalysisProgress):
            """
            Callback appelé pour chaque update de progression

            Met à jour l'état de la tâche Celery pour que le frontend
            puisse poller le statut.
            """
            # Update Celery task state
            self.update_state(
                state='PROGRESS',
                meta={
                    'step': progress.step,
                    'total_steps': progress.total_steps,
                    'progress': progress.progress,
                    'message': progress.message,
                    'status': progress.status,
                    'data': progress.data
                }
            )
            logger.info(f"[{progress.progress}%] {progress.message}")

        try:
            # Lancer l'analyse avec callback de progression
            result = analyze_researcher(
                researcher_name=researcher_name,
                scholar_id=scholar_id,
                max_coauthors=max_coauthors,
                progress_callback=progress_callback
            )

            logger.info(f"Analysis completed for: {researcher_name}")
            return result

        except Exception as e:
            logger.error(f"Analysis failed for {researcher_name}: {e}", exc_info=True)
            # Update state to FAILURE
            self.update_state(
                state='FAILURE',
                meta={
                    'progress': 0,
                    'message': f"Error: {str(e)}",
                    'status': 'error'
                }
            )
            raise


# Helper pour lancer une analyse sans Celery (pour tests)
def analyze_researcher_sync(
    researcher_name: str,
    scholar_id: Optional[str] = None,
    max_coauthors: int = 5
) -> Dict[str, Any]:
    """
    Analyse synchrone (sans Celery) pour tests

    Usage:
        result = analyze_researcher_sync("Alice Nedelec")
    """
    return analyze_researcher(
        researcher_name=researcher_name,
        scholar_id=scholar_id,
        max_coauthors=max_coauthors,
        progress_callback=None  # Pas de callback pour version sync
    )
