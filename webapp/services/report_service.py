"""
Service de génération de rapports

Formatter et préparer les données d'analyse pour affichage dans la page de rapport.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import os
import re
from src.logger import logger


def format_report_data(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formater les résultats d'analyse pour affichage dans le template

    Args:
        analysis_result: Résultats bruts de l'analyse

    Returns:
        Dict formaté pour le template report.html
    """
    # Researcher info
    researcher_data = analysis_result.get('researcher', {})

    h_index = researcher_data.get('h_index')
    affiliation = researcher_data.get('affiliation')
    first_pub_year = researcher_data.get('first_publication_year')

    # Call OpenAI to contextualise the H-index (field + percentile + scale)
    h_index_ai_assessment = None
    if h_index:
        try:
            from services.openai_service import get_h_index_assessment
            pub_titles = _get_top_pub_titles_from_graph(researcher_data.get('name', ''))
            h_index_ai_assessment = get_h_index_assessment(
                name=researcher_data.get('name', ''),
                affiliation=affiliation,
                h_index=h_index,
                first_pub_year=first_pub_year,
                pub_titles=pub_titles,
            )
        except Exception as _e:
            logger.warning(f"H-index AI assessment failed: {_e}")

    # Get patents data for display
    researcher_name = researcher_data.get('name', '')
    patents_list = _get_patents_from_graph(researcher_name) if researcher_name else []

    # Specialty tags — read from DB first, generate+store if absent
    specialty_tags = []
    openalex_id = researcher_data.get('openalex_id', '')
    _scientist_db_id = None

    if researcher_name:
        try:
            from src.database.database import SessionLocal
            from src.database.models import Scientist
            db = SessionLocal()
            try:
                s = db.query(Scientist).filter(Scientist.name.ilike(researcher_name)).first()
                if s:
                    _scientist_db_id = s.id
                    # Use stored tags if available
                    if s.specialty_tags:
                        specialty_tags = [t.strip() for t in s.specialty_tags.split(',') if t.strip()]
                    # Resolve openalex_id if not already known
                    if not openalex_id:
                        if s.openalex_id:
                            openalex_id = s.openalex_id
                        elif s.scholar_url and "openalex.org" in s.scholar_url:
                            openalex_id = s.scholar_url
                        elif s.scholar_id and "openalex.org" in s.scholar_id:
                            openalex_id = s.scholar_id
            finally:
                db.close()
        except Exception:
            pass

    # If no cached tags, generate via OpenAlex + GPT and persist
    if not specialty_tags and openalex_id:
        try:
            from services.coauthor_service import _get_openalex_data
            from src.database.database import SessionLocal
            from src.database.models import Scientist
            oa_data = _get_openalex_data(openalex_id, researcher_name)
            if oa_data:
                raw_tags = oa_data.get('specialty_tags', '')
                if raw_tags:
                    specialty_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
                    # Persist to DB so next load skips GPT
                    if _scientist_db_id:
                        try:
                            db2 = SessionLocal()
                            try:
                                s2 = db2.query(Scientist).filter(Scientist.id == _scientist_db_id).first()
                                if s2:
                                    s2.specialty_tags = raw_tags
                                    db2.commit()
                                    logger.info(f"Stored specialty_tags for {researcher_name}: {raw_tags}")
                            finally:
                                db2.close()
                        except Exception as _e:
                            logger.warning(f"Could not persist specialty_tags: {_e}")
        except Exception as _e:
            logger.warning(f"Could not generate specialty tags for {researcher_name}: {_e}")

    researcher = {
        'name': researcher_name or 'Unknown Researcher',
        'affiliation': affiliation,
        'h_index': h_index,
        'h_index_percentile': None,
        'h_index_ai_assessment': h_index_ai_assessment,
        'patents_count': researcher_data.get('patents_count', 0),
        'patents': patents_list,
        'recent_publications': researcher_data.get('recent_publications', 0),
        'scholar_id': researcher_data.get('scholar_id'),
        'openalex_id': openalex_id,
        'citations': researcher_data.get('citations', 0),
        'specialty_tags': specialty_tags,
    }

    # Co-authors
    coauthors_data = analysis_result.get('coauthors', [])
    coauthors = [
        {
            'name': ca.get('name', ca.get('original_name', 'Unknown')),
            'scholar_id': ca.get('scholar_id'),
            'affiliation': ca.get('affiliation'),
            'collaborations_count': ca.get('collaborations_count', 0),
            'corporate_links': ca.get('corporate_links', [])
        }
        for ca in coauthors_data
    ]

    # Corporate connections → Potential buyers
    corporate_connections = analysis_result.get('corporate_connections', [])
    potential_buyers = _format_potential_buyers(corporate_connections)

    # Graph URL (chercher un graphe existant ou utiliser celui fourni)
    graph_url = analysis_result.get('graph_url')
    if not graph_url:
        # Chercher un graphe existant pour ce chercheur
        graph_url = find_graph_for_researcher(researcher_data.get('name', ''))

    # Summary
    summary = analysis_result.get('summary', {})

    # Excel report URL
    excel_report = analysis_result.get('excel_report')
    excel_url = f"/static/reports/{excel_report}" if excel_report else None

    return {
        'researcher': researcher,
        'coauthors': coauthors,
        'potential_buyers': potential_buyers,
        'graph_url': graph_url,
        'excel_url': excel_url,
        'summary': summary
    }


def _calculate_h_index_percentile(h_index: Optional[int]) -> Optional[int]:
    """
    Calculer le percentile approximatif du H-index

    Basé sur des statistiques générales :
    - H-index >= 100 : Top 1%
    - H-index >= 50 : Top 5%
    - H-index >= 30 : Top 10%
    - H-index >= 20 : Top 20%
    - H-index >= 10 : Top 30%
    - H-index >= 5 : Top 40%
    - H-index >= 3 : Top 50%
    - H-index >= 1 : Top 60%
    """
    if not h_index:
        return None

    if h_index >= 100:
        return 1
    elif h_index >= 50:
        return 5
    elif h_index >= 30:
        return 10
    elif h_index >= 20:
        return 20
    elif h_index >= 10:
        return 30
    elif h_index >= 5:
        return 40
    elif h_index >= 3:
        return 50
    elif h_index >= 1:
        return 60
    else:
        return None


def _format_potential_buyers(corporate_connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Formatter les connexions corporates en "acheteurs potentiels"

    Args:
        corporate_connections: Liste des connexions trouvées

    Returns:
        Liste formatée pour affichage
    """
    buyers = []

    # Grouper par corporate
    corporate_groups = {}
    for conn in corporate_connections:
        corporate_name = conn.get('corporate_name', conn.get('company', 'Unknown Company'))

        if corporate_name not in corporate_groups:
            corporate_groups[corporate_name] = {
                'company_name': corporate_name,
                'connections': [],
                'total_evidence': 0
            }

        corporate_groups[corporate_name]['connections'].append(conn)
        corporate_groups[corporate_name]['total_evidence'] += len(conn.get('evidence', []))

    # Formatter pour l'affichage
    for corporate_name, group_data in corporate_groups.items():
        connections = group_data['connections']
        total_evidence = group_data['total_evidence']

        # Description
        description = _generate_buyer_description(connections, total_evidence)

        # Détails
        details = _generate_buyer_details(connections)

        # Next steps
        next_steps = [
            "Contact X in order to speak to Y",
            "Go to this event",
            "..."
        ]

        buyers.append({
            'company_name': corporate_name,
            'description': description,
            'details': details,
            'next_steps': next_steps,
            'connections_count': len(connections),
            'evidence_count': total_evidence
        })

    # Trier par nombre d'évidences (plus pertinent en premier)
    buyers.sort(key=lambda x: x['evidence_count'], reverse=True)

    return buyers


def _generate_buyer_description(connections: List[Dict[str, Any]], total_evidence: int) -> str:
    """Générer une description pour un acheteur potentiel"""
    num_connections = len(connections)

    if num_connections == 1:
        conn = connections[0]
        coauthor_name = conn.get('coauthor_name', 'a co-author')
        return f"The founder is connected to 1 company through {total_evidence} patent citation(s) related to {coauthor_name}."
    else:
        return f"The founder is connected through {num_connections} co-authors with {total_evidence} piece(s) of evidence (patents, affiliations)."


def _generate_buyer_details(connections: List[Dict[str, Any]]) -> List[str]:
    """Générer les détails pour un acheteur potentiel"""
    details = []

    # Collecter les domaines/technologies
    technologies = set()
    for conn in connections:
        evidence_list = conn.get('evidence', [])
        for ev in evidence_list:
            if 'technology' in ev or 'field' in ev:
                technologies.add(ev.get('technology', ev.get('field', '')))

    if technologies:
        tech_str = ', '.join(list(technologies)[:3])
        details.append(f"Technical focus: {tech_str}")

    return details


# Helper pour créer des données mockées (pour tests)
def find_graph_for_researcher(researcher_name: str) -> Optional[str]:
    """
    Chercher un graphe existant pour un chercheur.

    Priorité 1 : DB (persistant, survit aux redémarrages Clever Cloud).
    Priorité 2 : fichier HTML sur le filesystem (fallback local/dev).

    Args:
        researcher_name: Nom du chercheur

    Returns:
        URL du graphe (relative) ou None
    """
    if not researcher_name:
        return None

    from src.helpers import slug
    normalized_name = slug(researcher_name)

    # Priorité 1 : DB
    try:
        from src.database.database import SessionLocal
        from src.database.models import Scientist

        db = SessionLocal()
        try:
            has_graph = db.query(Scientist.id).filter(
                Scientist.normalized_name == normalized_name,
                Scientist.graph_html.isnot(None),
            ).first()
            if has_graph:
                return f"/graphs/db/{normalized_name}"
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"DB graph lookup failed (falling back to filesystem): {e}")

    # Priorité 2 : filesystem (dev local ou anciens graphes non encore en DB)
    project_root = Path(__file__).parent.parent.parent

    patterns = [
        f"{normalized_name}_network*.html",
        f"{normalized_name}*.html",
        f"*{normalized_name}*.html"
    ]

    for pattern in patterns:
        matching_files = list(project_root.glob(pattern))
        if matching_files:
            def sort_key(filepath):
                name = filepath.name.lower()
                if 'enriched' in name:
                    return 0
                elif 'network' in name and 'enriched' not in name:
                    return 1
                else:
                    return 2

            matching_files.sort(key=sort_key)
            return f"/graphs/{matching_files[0].name}"

    return None


def _count_patents_from_graph(researcher_name: str) -> int:
    """
    Compte les brevets depuis le graphe HTML (source de vérité pour le nombre affiché).
    """
    import json
    project_root = Path(__file__).parent.parent.parent
    from src.helpers import slug
    normalized = slug(researcher_name)

    patterns = [
        f"{normalized}_network*.html",
        f"{normalized}*.html",
        f"*{normalized}*.html",
    ]
    graph_path = None
    for pattern in patterns:
        matches = list(project_root.glob(pattern))
        if matches:
            matches.sort(key=lambda p: (0 if 'enriched' in p.name.lower() else 1 if 'network' in p.name.lower() else 2))
            graph_path = matches[0]
            break

    if not graph_path or not graph_path.exists():
        return -1  # -1 = pas de graphe, fallback sur Excel

    try:
        with open(graph_path, encoding='utf-8') as f:
            html = f.read()
        match = re.search(r'const graphData = ({.*?});', html, re.DOTALL)
        if not match:
            return -1
        data = json.loads(match.group(1))
        return len(data.get('patents', []))
    except Exception:
        return -1


def _get_patents_from_graph(researcher_name: str) -> list:
    """
    Extract patents with names and URLs from the graph HTML.
    Returns list of dicts with 'label' and 'url' keys.
    """
    import json
    project_root = Path(__file__).parent.parent.parent
    from src.helpers import slug
    normalized = slug(researcher_name)

    patterns = [
        f"{normalized}_network*.html",
        f"{normalized}*.html",
        f"*{normalized}*.html",
    ]
    graph_path = None
    for pattern in patterns:
        matches = list(project_root.glob(pattern))
        if matches:
            matches.sort(key=lambda p: (0 if 'enriched' in p.name.lower() else 1 if 'network' in p.name.lower() else 2))
            graph_path = matches[0]
            break

    if not graph_path or not graph_path.exists():
        return []

    try:
        with open(graph_path, encoding='utf-8') as f:
            html = f.read()

        # Extract graphData with patents list
        match = re.search(r'const graphData = ({.*?});', html, re.DOTALL)
        if not match:
            return []

        data = json.loads(match.group(1))
        patents_list = data.get('patents', [])

        if not patents_list:
            return []

        # Build map of patent node IDs to their full titles and URLs
        patents_data = {}

        for patent in patents_list:
            patent_id = patent.get('id', '')
            if patent_id:
                # Extract patents_url from the node in the HTML
                url_pattern = rf'"{re.escape(patent_id)}"[^}}]*?"patents_url"\s*:\s*"([^"]*)"'
                url_match = re.search(url_pattern, html)
                url = url_match.group(1) if url_match else ''

                patents_data[patent_id] = {
                    'url': url,
                    'title': patent.get('title', '')  # Get title from graphData which now includes it
                }

        # Build result list
        result = []
        for patent in patents_list:
            patent_id = patent.get('id', '')
            label = patent.get('label', '')
            title = patent.get('title', '')  # Title directly from graphData

            # Get URL from extracted data
            patent_info = patents_data.get(patent_id, {})
            url = patent_info.get('url', '')

            # Use full title if available, otherwise fallback to label
            display_label = title if title else label

            if display_label:
                result.append({
                    'label': display_label,
                    'url': url,
                    'id': patent_id
                })

        return result
    except Exception as e:
        logger.warning(f"Could not extract patents from graph: {e}")
        return []


def _get_top_pub_titles_from_graph(researcher_name: str, n: int = 5) -> list:
    """Get top-n most-cited publication titles from graph_html stored in DB."""
    import json
    try:
        from src.database.database import SessionLocal
        from src.database.models import Scientist
        from src.helpers import slug
        db = SessionLocal()
        try:
            html = db.query(Scientist.graph_html).filter(
                Scientist.normalized_name == slug(researcher_name)
            ).scalar()
            if not html:
                return []
            match = re.search(r'const graphData = ({.*?});', html, re.DOTALL)
            if not match:
                return []
            pubs = json.loads(match.group(1)).get('publications', [])
            pubs_sorted = sorted(pubs, key=lambda p: p.get('cited_by', 0) or 0, reverse=True)
            return [p.get('title') or p.get('label') for p in pubs_sorted[:n]
                    if p.get('title') or p.get('label')]
        finally:
            db.close()
    except Exception:
        return []


def _count_recent_publications_from_graph(researcher_name: str) -> int:
    """
    Compte les publications de l'année précédente depuis le graphe HTML.

    Le graphe contient un JSON embarqué avec {publications: [{year: '2025', ...}, ...]}
    """
    import json
    from datetime import datetime
    prev_year = str(datetime.now().year - 1)
    current_year = str(datetime.now().year)

    project_root = Path(__file__).parent.parent.parent
    from src.helpers import slug
    normalized = slug(researcher_name)

    patterns = [
        f"{normalized}_network*.html",
        f"{normalized}*.html",
        f"*{normalized}*.html",
    ]
    graph_path = None
    for pattern in patterns:
        matches = list(project_root.glob(pattern))
        if matches:
            graph_path = matches[0]
            break

    if not graph_path or not graph_path.exists():
        return 0

    try:
        with open(graph_path, encoding='utf-8') as f:
            html = f.read()
        match = re.search(r'const graphData = ({.*?});', html, re.DOTALL)
        if not match:
            return 0
        data = json.loads(match.group(1))
        publications = data.get('publications', [])
        return sum(
            1 for p in publications
            if str(p.get('year', '')) in (prev_year, current_year)
        )
    except Exception:
        return 0


def load_from_excel(researcher_name: str) -> Optional[Dict[str, Any]]:
    """
    Charger les données réelles depuis le rapport Excel généré par la pipeline.

    Utilisé comme fallback quand la DB n'a pas la donnée (ex: rollback dû au bug year).

    Args:
        researcher_name: Nom du chercheur

    Returns:
        Dict avec les données réelles ou None si fichier pas trouvé
    """
    from src.helpers import slug
    try:
        import openpyxl
    except ImportError:
        return None

    slugified = slug(researcher_name)
    excel_path = Path(__file__).parent.parent / "static" / "reports" / f"{slugified}_report.xlsx"

    if not excel_path.exists():
        return None

    try:
        wb = openpyxl.load_workbook(str(excel_path), read_only=True, data_only=True)
        ws = wb['Dashboard']

        # Read all non-empty rows into a flat list for parsing
        rows = [
            row for row in ws.iter_rows(values_only=True)
            if any(v is not None for v in row)
        ]

        # Parse key-value pairs from the Scholar Summary block
        # Structure: (None, key, value, ...) starting at row index 3
        kv = {}
        for row in rows:
            if row[1] and row[2] is not None:
                kv[str(row[1]).strip()] = row[2]
            # Patents section is at col 5-6 (index 5=key, 6=value)
            if len(row) > 6 and row[5] and row[6] is not None:
                kv[str(row[5]).strip()] = row[6]

        name = kv.get('Researcher', researcher_name)
        scholar_id = kv.get('author_id')
        affiliation = kv.get('Affiliation')
        citations = kv.get('Citations', 0)
        h_index = kv.get('H-index')
        publications_total = kv.get('Publications', 0)
        patents_total_excel = int(kv.get('Patents total', 0) or 0)

        # Compter les brevets depuis le graphe (source de vérité = même nombre que le filtre)
        patents_from_graph = _count_patents_from_graph(researcher_name)
        patents_total = patents_from_graph if patents_from_graph >= 0 else patents_total_excel

        graph_url = find_graph_for_researcher(researcher_name)

        # Count recent publications from the graph HTML (which has year per publication)
        recent_publications = _count_recent_publications_from_graph(researcher_name)

        logger.info(
            f"Loaded from Excel: {name} | h_index={h_index} | "
            f"affiliation={affiliation} | patents={patents_total} | "
            f"recent_pubs={recent_publications}"
        )

        return {
            'researcher': {
                'name': name,
                'affiliation': affiliation,
                'h_index': h_index,
                'scholar_id': scholar_id,
                'patents_count': patents_total,
                'recent_publications': recent_publications,
                'citations': citations,
                'total_publications': publications_total,
            },
            'coauthors': [],
            'corporate_connections': [],
            'summary': {
                'total_coauthors': 0,
                'disambiguated_coauthors': 0,
                'corporate_connections_found': 0,
            },
            'graph_url': graph_url,
            'excel_report': f"{slugified}_report.xlsx",
        }

    except Exception as e:
        logger.warning(f"Could not load Excel for {researcher_name}: {e}")
        return None


def load_from_pregenerated_json(researcher_name: str) -> Optional[Dict[str, Any]]:
    """
    Charger les données depuis un fichier JSON pré-généré

    Utilisé pour la démo sur Render sans base de données.

    Args:
        researcher_name: Nom du chercheur

    Returns:
        Dict avec les données ou None si fichier pas trouvé
    """
    import json
    from src.helpers import slug

    # Normaliser le nom
    safe_name = researcher_name.lower().replace(' ', '_')
    json_filename = f"{safe_name}_data.json"
    json_path = Path(__file__).parent.parent / "static" / json_filename

    if not json_path.exists():
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        # Convertir vers le format attendu
        scientist = data.get('scientist', {})
        corporates = data.get('corporates', [])
        publications = data.get('publications', [])

        # Compter les publications récentes (seulement 2025 - année précédente)
        recent_pubs = len([p for p in publications if p.get('year') == 2025])

        # Chercher le graphe HTML pour ce chercheur
        graph_url = find_graph_for_researcher(researcher_name)

        # Compter les brevets depuis le graphe (pas tous les brevets de la DB)
        # Utiliser la même logique que find_graph_for_researcher pour trouver le bon fichier
        patents_count = 0
        try:
            import json
            normalized_name = slug(researcher_name)
            project_root = Path(__file__).parent.parent.parent

            # Patterns de fichiers à chercher (même ordre que find_graph_for_researcher)
            patterns = [
                f"{normalized_name}_network*.html",
                f"{normalized_name}*.html",
                f"*{normalized_name}*.html"
            ]

            graph_path = None
            for pattern in patterns:
                matching_files = list(project_root.glob(pattern))
                if matching_files:
                    # Trier pour privilégier enriched > network > autres
                    def sort_key(filepath):
                        name = filepath.name.lower()
                        if 'enriched' in name:
                            return 0
                        elif 'network' in name and 'enriched' not in name:
                            return 1
                        else:
                            return 2
                    matching_files.sort(key=sort_key)
                    graph_path = matching_files[0]
                    break

            if graph_path and graph_path.exists():
                with open(graph_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    # Extraire graphData.patents.length depuis le JavaScript
                    match = re.search(r'const graphData = ({.*?});', html_content, re.DOTALL)
                    if match:
                        graph_data_str = match.group(1)
                        graph_data = json.loads(graph_data_str)
                        patents_count = len(graph_data.get('patents', []))
                        logger.info(f"Found {patents_count} patents in graph {graph_path.name}")
        except Exception as e:
            logger.warning(f"Could not count patents from graph: {e}")

        # Chercher le fichier Excel généré
        # Format: {slug(researcher_name)}_report.xlsx
        excel_filename = None
        slugified_name = slug(researcher_name)
        excel_path = Path(__file__).parent.parent / "static" / "reports" / f"{slugified_name}_report.xlsx"
        if excel_path.exists():
            excel_filename = f"{slugified_name}_report.xlsx"
            logger.info(f"Found Excel report: {excel_filename}")

        return {
            'researcher': {
                'name': scientist.get('name', researcher_name),
                'affiliation': None,
                'h_index': scientist.get('h_index'),
                'patents_count': patents_count,
                'recent_publications': recent_pubs,
                'scholar_id': scientist.get('scholar_id'),
                'citations': 0
            },
            'coauthors': [],
            'corporate_connections': [
                {
                    'corporate_name': corp['name'],
                    'coauthor_name': corp.get('via_coauthor', 'Direct'),
                    'evidence': [{'type': corp.get('affiliation_type', 'connection')}],
                    'technology': 'Various'
                }
                for corp in corporates
            ],
            'summary': {
                'total_coauthors': 0,
                'disambiguated_coauthors': 0,
                'corporate_connections_found': len(corporates)
            },
            'graph_url': graph_url,
            'excel_report': excel_filename
        }
    except Exception as e:
        print(f"Error loading JSON for {researcher_name}: {e}")
        return None


def create_mock_report_data(researcher_name: str) -> Dict[str, Any]:
    """
    Créer des données mockées pour tester le rapport

    Args:
        researcher_name: Nom du chercheur

    Returns:
        Dict avec données mockées
    """
    from src.helpers import slug

    # Check if Excel report exists for this researcher
    # Format: {slug(researcher_name)}_report.xlsx (same as build_ultra_complete_graph.py)
    slugified_name = slug(researcher_name)
    excel_filename = f"{slugified_name}_report.xlsx"
    excel_path = Path(__file__).parent.parent / "static" / "reports" / excel_filename

    # Generate pseudo-random but consistent data based on researcher name
    import hashlib
    name_hash = int(hashlib.md5(researcher_name.encode()).hexdigest(), 16)

    # Generate varied metrics based on name hash
    h_index = 20 + (name_hash % 40)  # Between 20 and 60
    patents_count = name_hash % 8  # Between 0 and 7
    recent_publications = 2 + (name_hash % 8)  # Between 2 and 9 co-authored publications on previous year
    citations = 500 + (name_hash % 2000)  # Between 500 and 2500

    # Different affiliations
    affiliations = [
        'MIT and Stanford University',
        'Elvesys and TU Dresden',
        'Harvard Medical School',
        'University of Cambridge',
        'INSERM and Sorbonne University',
        'ETH Zurich',
        'Johns Hopkins University'
    ]
    affiliation = affiliations[name_hash % len(affiliations)]

    return {
        'researcher': {
            'name': researcher_name,
            'affiliation': affiliation,
            'h_index': h_index,
            'patents_count': patents_count,
            'recent_publications': recent_publications,
            'scholar_id': 'abc123def456',
            'citations': citations
        },
        'coauthors': [
            {
                'name': 'John Doe',
                'scholar_id': 'scholar123',
                'affiliation': 'MIT',
                'collaborations_count': 12,
                'corporate_links': ['Siemens', 'Google Research']
            },
            {
                'name': 'Jane Smith',
                'scholar_id': 'scholar456',
                'affiliation': 'Stanford University',
                'collaborations_count': 8,
                'corporate_links': ['Apple', 'Microsoft']
            },
            {
                'name': 'Bob Johnson',
                'affiliation': 'Harvard Medical School',
                'collaborations_count': 5,
                'corporate_links': []
            }
        ],
        'corporate_connections': [
            {
                'corporate_name': 'Siemens',
                'coauthor_name': 'John Doe',
                'evidence': [
                    {'type': 'patent', 'count': 3},
                    {'type': 'affiliation', 'count': 1}
                ],
                'technology': 'Nanophysics and Microfluidics'
            }
        ],
        'summary': {
            'total_coauthors': 5,
            'disambiguated_coauthors': 3,
            'corporate_connections_found': 1
        },
        'graph_url': None,  # Sera ajouté par la suite
        'excel_report': excel_filename if excel_path.exists() else None
    }
