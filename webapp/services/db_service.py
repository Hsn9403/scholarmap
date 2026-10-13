"""
Service pour récupérer les données depuis la base de données
"""
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, defer
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.models import Scientist, Publication, Patent, Corporate, SearchHistory
from src.logger import logger


class DatabaseService:
    """Service pour interagir avec la base de données"""

    def __init__(self):
        """Initialize database connection — utilise le engine partagé (pool unique)."""
        from src.database.database import engine as _shared_engine, SessionLocal
        self.session = SessionLocal()

    def get_scientist_by_name(self, name: str) -> Optional[Scientist]:
        """
        Récupérer un scientifique par son nom

        Args:
            name: Nom du scientifique

        Returns:
            Scientist object ou None
        """
        try:
            # Get all matching scientists
            scientists = self.session.query(Scientist).options(
                defer(Scientist.graph_html)
            ).filter(
                Scientist.name.ilike(f'%{name}%')
            ).all()

            # Fallback: try with accent-stripped name (handles "Clàire" → "Claire")
            if not scientists:
                from src.helpers import strip_accents_basic
                normalized = strip_accents_basic(name)
                if normalized != name:
                    scientists = self.session.query(Scientist).options(
                        defer(Scientist.graph_html)
                    ).filter(
                        Scientist.name.ilike(f'%{normalized}%')
                    ).all()

            # Fallback: try normalized_name column (slug)
            if not scientists:
                from src.helpers import slug
                scientists = self.session.query(Scientist).options(
                    defer(Scientist.graph_html)
                ).filter(
                    Scientist.normalized_name == slug(name)
                ).all()

            if not scientists:
                return None

            # If multiple results, prefer the one with scholar_id and most data
            if len(scientists) > 1:
                # Sort by: has scholar_id, h_index value, number of publications
                scientists_scored = []
                for s in scientists:
                    score = 0
                    if s.scholar_id:
                        score += 1000
                    if s.h_index:
                        score += s.h_index
                    score += len(s.publications) if s.publications else 0
                    scientists_scored.append((score, s))

                scientists_scored.sort(key=lambda x: x[0], reverse=True)
                return scientists_scored[0][1]

            return scientists[0]
        except Exception as e:
            logger.error(f"Error getting scientist {name}: {e}")
            return None

    def has_search_history(self, name: str) -> bool:
        """
        Vérifie si un chercheur a déjà été analysé (présent dans search_history).

        Différent de get_scientist_by_name qui inclut les co-auteurs stockés
        en base lors des analyses d'autres chercheurs.
        """
        try:
            scientist = self.get_scientist_by_name(name)
            if not scientist:
                return False
            count = self.session.query(SearchHistory)\
                .filter(SearchHistory.scientist_id == scientist.id)\
                .count()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking search history for {name}: {e}")
            return False

    def get_scientist_data_for_report(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Récupérer toutes les données d'un scientifique pour le rapport

        Args:
            name: Nom du scientifique

        Returns:
            Dict avec toutes les données formatées
        """
        try:
            scientist = self.get_scientist_by_name(name)
            if not scientist:
                logger.warning(f"Scientist not found: {name}")
                return None

            # recent_publications : préférer le comptage depuis le graphe HTML
            # (plus fiable que les publications en DB qui peuvent être incomplètes)
            from services.report_service import (
                _count_recent_publications_from_graph,
                find_graph_for_researcher,
            )
            from datetime import datetime
            current_year = datetime.now().year

            recent_pubs_graph = _count_recent_publications_from_graph(scientist.name)
            if recent_pubs_graph > 0:
                recent_pubs = recent_pubs_graph
            else:
                recent_pubs = len([p for p in scientist.publications if p.year and p.year >= current_year - 1])

            # Excel report : ajouter l'URL si le fichier existe
            from pathlib import Path
            from src.helpers import slug as make_slug
            slugified = make_slug(scientist.name)
            excel_path = Path(__file__).parent.parent / "static" / "reports" / f"{slugified}_report.xlsx"
            excel_report = f"{slugified}_report.xlsx" if excel_path.exists() else None

            first_pub_year = min(
                (p.year for p in scientist.publications if p.year),
                default=None
            )

            # Extract openalex_id from scholar_url or scholar_id if stored there
            openalex_id = ""
            if scientist.scholar_url and "openalex.org" in scientist.scholar_url:
                openalex_id = scientist.scholar_url
            elif scientist.scholar_id and "openalex.org" in scientist.scholar_id:
                openalex_id = scientist.scholar_id

            return {
                'researcher': {
                    'name': scientist.name,
                    'affiliation': scientist.affiliation,
                    'h_index': scientist.h_index,
                    'scholar_id': scientist.scholar_id,
                    'scholar_url': scientist.scholar_url,
                    'openalex_id': openalex_id,
                    'patents_count': len(scientist.patents),
                    'recent_publications': recent_pubs,
                    'total_publications': len(scientist.publications),
                    'first_publication_year': first_pub_year,
                },
                'coauthors': [],  # TODO: Implement coauthors from DB
                'corporate_connections': [],  # TODO: Implement from DB
                'summary': {
                    'total_coauthors': 0,
                    'disambiguated_coauthors': 0,
                    'corporate_connections_found': 0
                },
                'excel_report': excel_report,
                'graph_url': find_graph_for_researcher(scientist.name),
            }
        except Exception as e:
            logger.error(f"Error getting scientist data: {e}", exc_info=True)
            return None

    def add_search_history(self, scientist_id: int, session_id: Optional[str] = None) -> bool:
        """
        Enregistrer une recherche dans l'historique

        Args:
            scientist_id: ID du scientifique recherché
            session_id: ID de session optionnel pour tracking

        Returns:
            True si l'enregistrement a réussi, False sinon
        """
        try:
            search_entry = SearchHistory(
                scientist_id=scientist_id,
                session_id=session_id,
            )
            self.session.add(search_entry)
            self.session.commit()
            logger.info(f"Added search history entry for scientist {scientist_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding search history: {e}", exc_info=True)
            self.session.rollback()
            return False

    def close(self):
        """Fermer la session"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_scientist_from_db(name: str) -> Optional[Dict[str, Any]]:
    """
    Helper function pour récupérer les données d'un scientifique

    Args:
        name: Nom du scientifique

    Returns:
        Dict avec les données ou None
    """
    with DatabaseService() as db:
        return db.get_scientist_data_for_report(name)
