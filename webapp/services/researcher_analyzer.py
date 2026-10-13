"""
Service d'analyse de chercheurs

Wrapper autour de mvp_researcher_to_corporate_STRICT.py pour intégration webapp.
Ce service est conçu pour être appelé par Celery (async) et retourner des updates de progression.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
import json

# Ajouter le dossier racine au PYTHONPATH pour importer les modules du projet
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import logger
from src.scholar.client import ScholarClient
from src.scholar.openalex_fallback import build_scholar_data_from_openalex
from src.patents.client import PatentsClient
from src.pathfinding.ror_client import RORClient
from src.pathfinding.openalex_client import OpenAlexClient
from src.pathfinding.strict_disambiguator import disambiguate_coauthor_strict, DisambiguationResult
from src.pathfinding.evidence_schema import (
    Evidence, EvidenceLevel, EvidenceType, CorporateConnection,
    create_patent_evidence
)
from src.clinical_trials import ClinicalTrialsClient
from src.export import ExcelExporter
from src.helpers import slug
import re

# Import des fonctions STRICT pour la recherche de corporates
from src.pathfinding.strict_corporate_scanner import (
    get_corporates_via_patents_STRICT,
    get_corporates_via_publications_STRICT,
    get_corporates_via_clinical_trials_STRICT
)


@dataclass
class AnalysisProgress:
    """Status de progression d'une analyse"""
    step: int  # 1-4
    total_steps: int  # 4
    progress: int  # 0-100
    message: str
    status: str  # 'processing', 'completed', 'error'
    data: Optional[Dict[str, Any]] = None


class ResearcherAnalyzer:
    """
    Analyseur de chercheurs

    Encapsule la logique de mvp_researcher_to_corporate_STRICT.py
    pour être utilisé dans la webapp avec support de progression.
    """

    def __init__(self):
        """Initialiser les clients API"""
        self.scholar = ScholarClient()
        self.patents = PatentsClient()
        self.openalex = OpenAlexClient()
        self.ror = RORClient()
        self.clinical_trials = ClinicalTrialsClient()

    def analyze(
        self,
        researcher_name: str,
        scholar_id: Optional[str] = None,
        max_coauthors: int = 5,
        progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
    ) -> Dict[str, Any]:
        """
        Analyser un chercheur et trouver ses liens avec des corporates

        Args:
            researcher_name: Nom du chercheur
            scholar_id: ID Scholar (optionnel, sinon recherche automatique)
            max_coauthors: Nombre max de co-auteurs à analyser
            progress_callback: Fonction appelée pour chaque update de progression

        Returns:
            Dict avec les résultats de l'analyse

        Raises:
            Exception: Si erreur durant l'analyse
        """
        try:
            # STEP 1: Get researcher's Scholar profile
            self._update_progress(
                progress_callback,
                step=1,
                progress=10,
                message="Searching for Scholar profile...",
                status="processing"
            )

            main_researcher_openalex = None

            if scholar_id:
                scholar_data = self.scholar.fetch_author_data(scholar_id, num_articles=10)
            else:
                candidates = self.scholar.find_candidates(researcher_name, num=5)

                if not candidates:
                    # No Scholar profile — try OpenAlex as fallback
                    logger.info(
                        f"No Scholar profile for '{researcher_name}', "
                        "trying OpenAlex fallback..."
                    )
                    self._update_progress(
                        progress_callback,
                        step=1,
                        progress=15,
                        message="No Scholar profile found — searching OpenAlex...",
                        status="processing"
                    )
                    scholar_data = build_scholar_data_from_openalex(
                        researcher_name=researcher_name,
                        openalex_client=self.openalex,
                        max_publications=50,
                    )
                    if not scholar_data:
                        self._update_progress(
                            progress_callback,
                            step=1,
                            progress=100,
                            message=f"Researcher not found: {researcher_name}",
                            status="error"
                        )
                        raise ValueError(f"Researcher not found: {researcher_name}")

                    # author_id is already the OpenAlex URL — reuse the cached author
                    main_researcher_openalex = self.openalex.get_author(scholar_data.author_id)

                else:
                    # Si plusieurs candidats, retourner pour disambiguation
                    if len(candidates) > 1:
                        self._update_progress(
                            progress_callback,
                            step=1,
                            progress=50,
                            message="Multiple profiles found - disambiguation needed",
                            status="disambiguation_needed",
                            data={
                                "candidates": [
                                    {
                                        "scholar_id": c.author_id,
                                        "title": c.title,  # Contains name + affiliation
                                        "link": c.link,
                                        "snippet": c.snippet
                                    }
                                    for c in candidates
                                ]
                            }
                        )
                        # Pour la webapp, on retourne les candidats
                        # TODO: Gérer la sélection dans le frontend
                        return {
                            "status": "disambiguation_needed",
                            "candidates": [asdict(c) for c in candidates]
                        }

                    scholar_data = self.scholar.fetch_author_data(candidates[0].author_id, num_articles=10)

            logger.info(f"Profile found: {scholar_data.name}")
            self._update_progress(
                progress_callback,
                step=1,
                progress=25,
                message=f"Profile found: {scholar_data.name}",
                status="processing"
            )

            # Get main researcher's OpenAlex ID (skip if already set by OpenAlex fallback)
            if main_researcher_openalex is None:
                main_researcher_openalex = self.openalex.search_author(scholar_data.name)
                if not main_researcher_openalex:
                    logger.warning(f"Main researcher not found in OpenAlex: {scholar_data.name}")
                    # Continue anyway (certains chercheurs peuvent ne pas être dans OpenAlex)

            main_researcher_openalex_id = main_researcher_openalex["id"] if main_researcher_openalex else None

            # STEP 2: Disambiguate co-authors
            self._update_progress(
                progress_callback,
                step=2,
                progress=30,
                message="Analyzing co-authors...",
                status="processing"
            )

            coauthors_to_scan = scholar_data.coauthors[:max_coauthors]
            disambiguated_coauthors: List[Dict[str, Any]] = []

            for i, coauthor in enumerate(coauthors_to_scan, 1):
                progress = 30 + int((i / len(coauthors_to_scan)) * 20)  # 30-50%
                self._update_progress(
                    progress_callback,
                    step=2,
                    progress=progress,
                    message=f"Analyzing co-author {i}/{len(coauthors_to_scan)}: {coauthor.name}",
                    status="processing"
                )

                # Disambiguation logic (simplifié pour MVP webapp)
                # Both Scholar-sourced (have scholar_id) and OpenAlex-sourced (scholar_id=None)
                # co-authors go through OpenAlex name disambiguation.
                # OpenAlex-sourced names are already full names (not abbreviated), so
                # disambiguation works well even without a Scholar ID hint.
                result = disambiguate_coauthor_strict(
                    main_researcher_name=scholar_data.name,
                    coauthor_partial_name=coauthor.name,
                    openalex_client=self.openalex,
                    interactive=False  # Non-interactif pour webapp
                )

                if result.status == "RESOLVED":
                    disambiguated_coauthors.append({
                        "name": result.resolved_name,
                        "original_name": coauthor.name,
                        "scholar_id": coauthor.scholar_id,
                        "openalex_id": result.openalex_id
                    })
                else:
                    # Use original name as fallback (full name from OpenAlex is usable as-is)
                    logger.warning(f"  → Using original name (OpenAlex disambiguation {result.status})")
                    disambiguated_coauthors.append({
                        "name": coauthor.name,
                        "original_name": coauthor.name,
                        "scholar_id": coauthor.scholar_id,
                        "openalex_id": None
                    })

            # STEP 3: Search for corporate connections
            self._update_progress(
                progress_callback,
                step=3,
                progress=55,
                message="Searching for corporate connections...",
                status="processing"
            )

            # Scan pour les corporates via les 3 sources
            all_connections: List[CorporateConnection] = []

            for i, coauthor_data in enumerate(disambiguated_coauthors, 1):
                coauthor_name = coauthor_data["name"]
                coauthor_openalex_id = coauthor_data.get("openalex_id")

                # Update progress
                progress = 55 + int((i / len(disambiguated_coauthors)) * 25)
                self._update_progress(
                    progress_callback,
                    step=3,
                    progress=progress,
                    message=f"Scanning co-author {i}/{len(disambiguated_coauthors)}: {coauthor_name}",
                    status="processing"
                )

                logger.info(f"[{i}/{len(disambiguated_coauthors)}] Scanning: {coauthor_name}")

                all_evidence: List[Evidence] = []

                # SOURCE 1: Patents (from DB)
                logger.info(f"  [1/3] Checking patents...")
                try:
                    patent_evidence = get_corporates_via_patents_STRICT(
                        coauthor_name=coauthor_name,
                        coauthor_openalex_id=coauthor_openalex_id,
                        patents_client=self.patents,
                        ror_client=self.ror,
                        use_db=True  # Use database instead of SerpAPI
                    )
                    all_evidence.extend(patent_evidence)
                    logger.info(f"    Found {len(patent_evidence)} patent evidence(s)")
                except Exception as e:
                    logger.error(f"    Error checking patents: {e}")

                # SOURCE 2: Publication affiliations
                if coauthor_openalex_id:
                    logger.info(f"  [2/3] Checking publication affiliations...")
                    try:
                        pub_evidence = get_corporates_via_publications_STRICT(
                            main_researcher_openalex_id=main_researcher_openalex_id,
                            coauthor_name=coauthor_name,
                            coauthor_openalex_id=coauthor_openalex_id,
                            openalex_client=self.openalex,
                            ror_client=self.ror
                        )
                        all_evidence.extend(pub_evidence)
                        logger.info(f"    Found {len(pub_evidence)} publication evidence(s)")
                    except Exception as e:
                        logger.error(f"    Error checking publications: {e}")
                else:
                    logger.info(f"  [2/3] Skipping publications (no OpenAlex ID)")

                # SOURCE 3: ClinicalTrials
                logger.info(f"  [3/3] Checking ClinicalTrials.gov...")
                try:
                    ct_evidence = get_corporates_via_clinical_trials_STRICT(
                        coauthor_name=coauthor_name,
                        clinical_trials_client=self.clinical_trials,
                        ror_client=self.ror
                    )
                    all_evidence.extend(ct_evidence)
                    logger.info(f"    Found {len(ct_evidence)} clinical trial evidence(s)")
                except Exception as e:
                    logger.error(f"    Error checking clinical trials: {e}")

                # Group evidence by corporate
                from collections import defaultdict
                corporates_map: Dict[str, List[Evidence]] = defaultdict(list)

                for evidence in all_evidence:
                    # Only keep Level A or B
                    if evidence.verdict in [EvidenceLevel.LEVEL_A, EvidenceLevel.LEVEL_B]:
                        # Extract corporate name from raw_data
                        corporate_name = None
                        if evidence.raw_data:
                            corporate_name = evidence.raw_data.get("assignee") or evidence.raw_data.get("institution_name")

                        if corporate_name:
                            corporates_map[corporate_name].append(evidence)

                # Create CorporateConnection objects
                for corporate_name, evidence_list in corporates_map.items():
                    # Get best evidence level
                    best_level = min(
                        (e.verdict for e in evidence_list),
                        key=lambda x: ["LEVEL_A", "LEVEL_B", "LEVEL_C"].index(x.value)
                    )

                    # Calculate overall confidence
                    overall_confidence = sum(e.confidence for e in evidence_list) / len(evidence_list)

                    connection = CorporateConnection(
                        researcher=scholar_data.name,
                        coauthor=coauthor_name,
                        coauthor_openalex_id=coauthor_openalex_id,
                        corporate=corporate_name,
                        corporate_ror_id=None,  # TODO: Enrichir avec ROR ID
                        evidence_list=evidence_list,
                        overall_confidence=overall_confidence,
                        best_evidence_level=best_level
                    )

                    all_connections.append(connection)
                    logger.info(f"  ✓ {corporate_name} ({len(evidence_list)} evidence(s), Level {best_level.value})")

            logger.info(f"\n✓ Found {len(all_connections)} corporate connection(s)")

            self._update_progress(
                progress_callback,
                step=3,
                progress=80,
                message=f"Found {len(all_connections)} corporate connection(s)",
                status="processing"
            )

            # STEP 4: Find paths to corporates (distance < 3)
            self._update_progress(
                progress_callback,
                step=4,
                progress=85,
                message="Finding paths to corporates...",
                status="processing"
            )

            corporate_paths = {}
            if all_connections:
                try:
                    # Build graph from database
                    from src.database.adapters import scientist_to_scholar_data, scientist_to_patents_data
                    from src.graph.builder import build_graph_data
                    from src.pathfinding.graph_adapter import adapt_graph
                    from src.pathfinding.pathfinder import Pathfinder

                    logger.info("Building graph for pathfinding...")
                    scholar_graph_data = scientist_to_scholar_data(scientist_name=scholar_data.name)
                    patents_graph_data = scientist_to_patents_data(scientist_name=scholar_data.name)

                    graph_dict = build_graph_data(scholar_graph_data, patents_graph_data)
                    nodes_dict, edges_list = adapt_graph(graph_dict)

                    # Create pathfinder with max_path_length=2 (distance < 3)
                    pathfinder = Pathfinder(
                        nodes=nodes_dict,
                        edges=edges_list,
                        max_path_length=2  # Max 2 edges = distance < 3
                    )

                    # Find researcher node ID
                    researcher_node_id = f"person:{slug(scholar_data.name)}"

                    # For each unique corporate, find paths
                    unique_corporates = set(c.corporate for c in all_connections)
                    for i, corporate_name in enumerate(unique_corporates, 1):
                        logger.info(f"Finding paths to {corporate_name}...")

                        # Try to find corporate node ID
                        corporate_node_id = f"corporate:{slug(corporate_name)}"

                        # Find paths (max 3 paths per corporate)
                        paths = pathfinder.find_paths(
                            source_id=researcher_node_id,
                            target_id=corporate_node_id,
                            max_paths=3
                        )

                        if paths:
                            # Format paths for display
                            corporate_paths[corporate_name] = [
                                {
                                    "score": path.score,
                                    "length": len(path.steps),
                                    "steps": [
                                        {
                                            "node_name": step.entity.name,
                                            "node_type": step.entity.type.value,
                                            "relation": step.relation.type.value if step.relation else None
                                        }
                                        for step in path.steps
                                    ]
                                }
                                for path in paths
                            ]
                            logger.info(f"  Found {len(paths)} path(s) to {corporate_name}")

                except Exception as e:
                    logger.error(f"Error finding paths: {e}", exc_info=True)
                    # Continue anyway, paths are optional

            # STEP 5: Generate report
            self._update_progress(
                progress_callback,
                step=4,
                progress=90,
                message="Generating report...",
                status="processing"
            )

            # Generate Excel report
            excel_filename = None
            try:
                # Fetch patents data from database for Excel report
                from src.database.adapters import scientist_to_patents_data
                patents_data = scientist_to_patents_data(scientist_name=scholar_data.name)

                # Create safe filename
                safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", scholar_data.name).strip("_")
                excel_filename = f"researcher_report_{safe_name}.xlsx"

                # Save to webapp static folder
                webapp_static = Path(__file__).parent.parent / "static" / "reports"
                webapp_static.mkdir(parents=True, exist_ok=True)
                excel_path = webapp_static / excel_filename

                # Generate Excel
                exporter = ExcelExporter()
                exporter.write(str(excel_path), scholar_data.name, scholar_data, patents_data)

                logger.info(f"Excel report generated: {excel_filename}")
            except Exception as e:
                logger.error(f"Failed to generate Excel report: {e}", exc_info=True)
                # Continue anyway, Excel is optional

            # Format corporate connections for web display
            corporate_connections_formatted = []
            for connection in all_connections:
                corporate_connections_formatted.append({
                    "corporate_name": connection.corporate,
                    "coauthor_name": connection.coauthor,
                    "evidence_count": len(connection.evidence_list),
                    "best_evidence_level": connection.best_evidence_level.value,
                    "confidence": connection.overall_confidence,
                    "evidence": [
                        {
                            "type": e.evidence_type.value,
                            "level": e.verdict.value,
                            "source_url": e.source_url if hasattr(e, 'source_url') else None,
                            "notes": e.notes if hasattr(e, 'notes') else None
                        }
                        for e in connection.evidence_list
                    ]
                })

            # Calculate recent publications (last 12 months / previous year)
            from datetime import datetime
            current_year = datetime.now().year
            previous_year = current_year - 1

            recent_publications_count = 0
            if scholar_data.top_publications:
                for pub in scholar_data.top_publications:
                    pub_year = pub.year
                    # Count publications from previous year and current year (last 12 months approximation)
                    if pub_year and isinstance(pub_year, (int, str)):
                        try:
                            year_int = int(pub_year)
                            if year_int >= previous_year:
                                recent_publications_count += 1
                        except (ValueError, TypeError):
                            continue

            result = {
                "status": "completed",
                "researcher": {
                    "name": scholar_data.name,
                    "scholar_id": scholar_data.author_id,
                    "openalex_id": main_researcher_openalex_id,
                    "h_index": scholar_data.h_index,
                    "citations": scholar_data.citations_total,
                    "affiliation": scholar_data.affiliation,
                    "recent_publications": recent_publications_count
                },
                "coauthors": disambiguated_coauthors,
                "corporate_connections": corporate_connections_formatted,
                "corporate_paths": corporate_paths,  # Paths to each corporate (distance < 3)
                "excel_report": excel_filename,
                "summary": {
                    "total_coauthors": len(coauthors_to_scan),
                    "disambiguated_coauthors": len(disambiguated_coauthors),
                    "corporate_connections_found": len(all_connections),
                    "unique_corporates": len(set(c.corporate for c in all_connections)),
                    "corporates_with_paths": len(corporate_paths)
                }
            }

            self._update_progress(
                progress_callback,
                step=4,
                progress=100,
                message="Analysis complete!",
                status="completed",
                data=result
            )

            return result

        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            self._update_progress(
                progress_callback,
                step=0,
                progress=0,
                message=f"Error: {str(e)}",
                status="error"
            )
            raise

    def _update_progress(
        self,
        callback: Optional[Callable[[AnalysisProgress], None]],
        step: int,
        progress: int,
        message: str,
        status: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """Helper pour envoyer des updates de progression"""
        if callback:
            progress_obj = AnalysisProgress(
                step=step,
                total_steps=4,
                progress=progress,
                message=message,
                status=status,
                data=data
            )
            callback(progress_obj)


# Fonction helper pour utilisation simple (sans classe)
def analyze_researcher(
    researcher_name: str,
    scholar_id: Optional[str] = None,
    max_coauthors: int = 5,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> Dict[str, Any]:
    """
    Fonction helper pour analyser un chercheur

    Usage:
        result = analyze_researcher("Alice Nedelec")
    """
    analyzer = ResearcherAnalyzer()
    return analyzer.analyze(
        researcher_name=researcher_name,
        scholar_id=scholar_id,
        max_coauthors=max_coauthors,
        progress_callback=progress_callback
    )
