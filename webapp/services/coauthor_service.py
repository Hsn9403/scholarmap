"""
Service for retrieving coauthor profile data from graph + DB + OpenAlex.
"""
import json
import re
import os
from pathlib import Path
from typing import Dict, Any, Optional

from src.logger import logger
from src.helpers import slug, strip_accents_basic
from src.pathfinding.openalex_client import OpenAlexClient


def _merge_api_patents(coauthor_name: str, db_patents: list, specialty_tags: str = "") -> list:
    """Fetch all patents for a coauthor using the full fetch_patents_data logic
    (same rules as the seed researcher: middle-initial, GPT validation by specialty)
    and merge with patents already stored in DB from the pipeline.

    Returns the merged, deduplicated list.
    """
    try:
        from src.patents.client import PatentsClient

        client = PatentsClient()
        patents_data = client.fetch_patents_data(
            coauthor_name,
            max_patents=10,
            researcher_specialty=specialty_tags,
        )

        api_patents = []
        if patents_data and patents_data.top_patents:
            for p in patents_data.top_patents:
                link = p.link or ""
                if not link and p.patent_id:
                    link = f"https://patents.google.com/patent/{p.patent_id}/en"
                api_patents.append({
                    "patent_id": p.patent_id or "",
                    "title": p.title or "",
                    "publication_date": str(p.publication_date) if p.publication_date else None,
                    "link": link,
                    "assignee": p.current_assignee or "",
                })

        # Deduplicate with existing DB patents
        seen_ids = {p.get("patent_id", "") for p in db_patents if p.get("patent_id")}
        seen_titles = {(p.get("title") or "").lower()[:60] for p in db_patents if p.get("title")}

        merged = list(db_patents)
        for p in api_patents:
            pid = p.get("patent_id", "")
            title = (p.get("title") or "").lower()[:60]
            if pid and pid in seen_ids:
                continue
            if title and title in seen_titles:
                continue
            merged.append(p)
            if pid:
                seen_ids.add(pid)
            if title:
                seen_titles.add(title)

        logger.info(f"[coauthor patents] {coauthor_name}: {len(db_patents)} DB + {len(merged) - len(db_patents)} API = {len(merged)} total")
        return merged

    except Exception as e:
        logger.warning(f"[coauthor patents] fetch_patents_data failed for {coauthor_name}: {e}")
        return db_patents  # Fallback: DB only


def get_coauthor_profile(coauthor_name: str, seed_researcher: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Build a complete coauthor profile combining:
    - Graph data (co-publications count, collaborations)
    - DB data (affiliation, patents, connected corporates via patents)
    - OpenAlex data (h-index, true affiliations, enriched info)

    Args:
        coauthor_name: Name of the coauthor to profile
        seed_researcher: Optional seed researcher name to compute co-publication count

    Returns:
        Dict with coauthor profile or None if not found
    """
    try:
        # Step 1: Get graph data (collaborations with seed)
        graph_data = {}
        coauthor_collab_count = 0
        graph_entities = {"corporates": [], "institutions": []}
        patent_titles_from_graph = []
        openalex_id = ""

        if seed_researcher:
            graph_data = _extract_from_graph(coauthor_name, seed_researcher)
            coauthor_collab_count = graph_data.get("collaborations_with_seed", 0)
            graph_entities = graph_data.get("connected_entities", {})
            patent_titles_from_graph = graph_data.get("patent_titles_from_graph", [])
            openalex_id = graph_data.get("openalex_id", "")

        # Step 2: Get DB data (affiliation, patents, corporates from patents)
        db_data = _get_coauthor_db_data(coauthor_name, patent_titles_from_graph)
        patents = db_data.get("patents", [])
        db_corporates = db_data.get("corporates", [])
        db_institutions = db_data.get("institutions", [])

        # Step 2b: Complete patent list via fetch_patents_data (full rule logic)
        # Use specialty_tags from DB if available (stored from a previous pipeline run)
        db_specialty = db_data.get("specialty_tags", "")
        patents = _merge_api_patents(coauthor_name, patents, specialty_tags=db_specialty)

        # Fallback to DB openalex_id if not in graph
        if not openalex_id:
            openalex_id = db_data.get("openalex_id", "")

        # Step 3: Get OpenAlex data (by ID or name search)
        openalex_data = _get_openalex_data(openalex_id, coauthor_name) or {}

        # Step 4: Merge H-index: OpenAlex > DB > graph
        h_index = openalex_data.get("h_index") or db_data.get("h_index") or graph_data.get("h_index")

        # Step 5: Merge affiliations: OpenAlex > DB > graph
        affiliation = openalex_data.get("affiliation") or db_data.get("affiliation") or graph_data.get("affiliation", "")

        # Step 6: Institutions come from graph edges (source of truth)
        # OpenAlex affiliations are not used here — they mix corporates into institutions
        all_institutions = graph_entities.get("institutions", [])

        # Step 7: Corporates come from graph edges only
        # DB patent assignees are excluded — they conflate universities with companies
        all_corporates = graph_entities.get("corporates", [])

        # Step 8: Compile profile
        specialty_tags = openalex_data.get("specialty_tags", "")
        is_seed = bool(seed_researcher and coauthor_name.lower() == seed_researcher.lower())
        publications_count = graph_data.get("publications_count", 0) if is_seed else 0

        profile = {
            "name": coauthor_name,
            "affiliation": affiliation,
            "h_index": h_index,
            "openalex_id": openalex_id,
            "scholar_id": graph_data.get("scholar_id", ""),
            "collaborations_with_seed": coauthor_collab_count,
            "is_seed": is_seed,
            "publications_count": publications_count,
            "patents_count": len(patents),
            "patents": patents,
            "connected_corporates": all_corporates,
            "connected_institutions": all_institutions,
            "specialty_tags": specialty_tags,
        }

        return profile

    except Exception as e:
        logger.warning(f"Could not get coauthor profile for {coauthor_name}: {e}")
        return None


def _generate_specialty_tags(topics: list) -> str:
    """Generate specialty tags from research topics using ChatGPT.

    Args:
        topics: List of research topics (names).

    Returns:
        Comma-separated specialty tags.
    """
    if not topics:
        return ""

    try:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return ""

        client = OpenAI(api_key=api_key)
        model = "gpt-5.4-mini"

        prompt = f"""Based on these research topics, generate 2-3 concise specialty tags for a researcher.
Topics: {', '.join(topics)}

Return only the tags as a comma-separated string, e.g.: "Gene Therapy, RNA Interference"
Keep it short and professional."""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=50,
            temperature=0
        )

        tags = response.choices[0].message.content.strip()
        return tags

    except Exception as e:
        logger.warning(f"Could not generate specialty tags: {e}")
        return ""


def _get_openalex_data(openalex_id: str, coauthor_name: str = "") -> Optional[Dict[str, Any]]:
    """Get coauthor data from OpenAlex API (H-index, affiliations, topics, etc).

    Args:
        openalex_id: OpenAlex author ID. If empty, searches by name.
        coauthor_name: Author name for search if openalex_id not available.
    """
    try:
        client = OpenAlexClient()
        author = None

        # If we have the ID, fetch directly
        if openalex_id:
            author = client.get_author(openalex_id)
        # Otherwise search by name
        elif coauthor_name:
            author = client.search_author(coauthor_name)

        if not author:
            return {}

        # Extract H-index from summary_stats
        h_index = None
        summary_stats = author.get("summary_stats", {})
        if summary_stats:
            h_index = summary_stats.get("h_index")

        # Extract all affiliations (current + past) from OpenAlex
        affiliation = ""
        institutions = []
        seen_institutions = set()

        # Get primary affiliation (first from last_known_institutions)
        last_institutions = author.get("last_known_institutions", [])
        if last_institutions:
            affiliation = last_institutions[0].get("display_name", "")

        # Get ALL institutions from affiliations field (includes both current and past)
        affiliations = author.get("affiliations", [])
        for aff in affiliations:
            inst = aff.get("institution", {})
            label = inst.get("display_name", "")

            if label and label.lower() not in seen_institutions:
                institutions.append({
                    "id": inst.get("id", ""),
                    "label": label,
                    "type": "institution",
                    "source": "openalex_affiliations"
                })
                seen_institutions.add(label.lower())

        # Sort all institutions alphabetically
        institutions.sort(key=lambda x: x.get("label", "").lower())

        # Extract top 3 topics and generate specialty tags
        specialty_tags = ""
        topics_data = author.get("topics", [])
        if topics_data:
            # Get top 3 topics by relevance score
            top_topics = sorted(topics_data, key=lambda x: x.get("score") or 0, reverse=True)[:3]
            topic_names = [t.get("display_name", "") for t in top_topics if t.get("display_name")]

            if topic_names:
                specialty_tags = _generate_specialty_tags(topic_names)

        return {
            "h_index": h_index,
            "affiliation": affiliation,
            "institutions": institutions,
            "specialty_tags": specialty_tags,
        }

    except Exception as e:
        logger.warning(f"Could not fetch OpenAlex data for {openalex_id or coauthor_name}: {e}")
        return {}


def _extract_from_graph(coauthor_name: str, seed_researcher: str) -> Dict[str, Any]:
    """Extract coauthor data from seed researcher's graph HTML by traversing vis.js edges."""
    import json

    project_root = Path(__file__).parent.parent.parent
    normalized = slug(seed_researcher)

    # Find graph file
    patterns = [
        f"{normalized}_network*.html",
        f"{normalized}*.html",
        f"*{normalized}*.html",
    ]

    graph_path = None
    for pattern in patterns:
        matches = list(project_root.glob(pattern))
        if matches:
            matches.sort(key=lambda p: (0 if 'enriched' in p.name.lower() else 1))
            graph_path = matches[0]
            break

    if not graph_path or not graph_path.exists():
        return {}

    try:
        with open(graph_path, encoding='utf-8') as f:
            html = f.read()

        # ── Helper: extract a vis.DataSet JSON array by bracket-matching ──
        def _extract_dataset(marker: str) -> list:
            pos = html.find(marker)
            if pos < 0:
                return []
            bracket_start = html.index('[', pos)
            depth = 0
            for i, ch in enumerate(html[bracket_start:]):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        return json.loads(html[bracket_start: bracket_start + i + 1])
            return []

        vis_nodes = _extract_dataset('nodes = new vis.DataSet(')
        vis_edges = _extract_dataset('edges = new vis.DataSet(')

        if not vis_nodes or not vis_edges:
            return {}

        # ── Find person's node ID by label (case-insensitive) ──
        name_lower = coauthor_name.lower()
        person_node_id = None
        node_by_id: Dict[str, Any] = {}
        collab_count = 0
        h_index = None
        openalex_id = ""
        scholar_id = ""
        affiliation = ""

        for node in vis_nodes:
            node_by_id[node['id']] = node
            if node.get('node_type') == 'person' and node.get('label', '').lower() == name_lower:
                person_node_id = node['id']

        if not person_node_id:
            return {}

        # ── Traverse edges to find connected corporates/institutions/patents ──
        seen_ids: set = set()
        corporates: list = []
        institutions: list = []
        patents: list = []

        for edge in vis_edges:
            other_id = None
            if edge.get('from') == person_node_id:
                other_id = edge.get('to')
            elif edge.get('to') == person_node_id:
                other_id = edge.get('from')

            if not other_id or other_id in seen_ids:
                continue
            seen_ids.add(other_id)

            other = node_by_id.get(other_id)
            if not other:
                continue

            ntype = other.get('node_type')
            label = other.get('label', '')

            if ntype == 'corporate':
                corporates.append({'id': other_id, 'label': label, 'type': 'corporate'})
            elif ntype == 'institution':
                institutions.append({'id': other_id, 'label': label, 'type': 'institution'})
            elif ntype == 'patent':
                patents.append({'id': other_id, 'label': label, 'type': 'patent'})

        # ── Pull attributes (h_index, openalex_id, etc.) and pub count from graphData ──
        publications_count = 0
        gd_match = re.search(r'const graphData = ({.*?});', html, re.DOTALL)
        if gd_match:
            gd = json.loads(gd_match.group(1))
            for p in gd.get('persons', []):
                if p.get('label', '').lower() == name_lower:
                    collab_count = p.get('collaborations', 0)
                    h_index = p.get('h_index')
                    openalex_id = p.get('openalex_id', '')
                    scholar_id = p.get('scholar_id', '')
                    affiliation = p.get('affiliation', '')
                    break
            # For seed researcher (not in persons list): count all publication nodes
            publications_count = len(gd.get('publications', []))

        return {
            "affiliation": affiliation,
            "h_index": h_index,
            "openalex_id": openalex_id,
            "scholar_id": scholar_id,
            "collaborations_with_seed": collab_count,
            "publications_count": publications_count,
            "connected_entities": {
                "corporates": corporates,
                "institutions": institutions,
            },
            "patent_titles_from_graph": [p.get('label', '') for p in patents],
        }

    except Exception as e:
        logger.warning(f"Error extracting graph data: {e}")
        return {}


def _merge_entities(graph_entities: list, db_entities: list) -> list:
    """Merge entities from graph and DB, deduplicating by label."""
    seen = set()
    merged = []

    # Add from graph first
    for entity in graph_entities:
        label = entity.get("label", "").lower()
        if label and label not in seen:
            merged.append(entity)
            seen.add(label)

    # Add from DB (avoid duplicates)
    for entity in db_entities:
        label = entity.get("label", "").lower()
        if label and label not in seen:
            merged.append(entity)
            seen.add(label)

    return merged


def _get_coauthor_db_data(coauthor_name: str, patent_titles_from_graph: list = None) -> Dict[str, Any]:
    """Get coauthor data from DB: affiliation, patents, and connected corporates/institutions.

    Args:
        coauthor_name: Name of the coauthor
        patent_titles_from_graph: List of patent titles extracted from graph connections
    """
    try:
        from src.database.database import SessionLocal
        from src.database.models import Scientist, Patent, Corporate, Institution
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            # Find the scientist — try exact match first, then strip middle initial
            # e.g. "Gregory W. Albers" → fallback "Gregory Albers"
            scientist = db.query(Scientist).filter(
                Scientist.name.ilike(f'%{coauthor_name}%')
            ).first()

            if not scientist:
                parts = coauthor_name.strip().split()
                if len(parts) == 3:
                    first_last = f"{parts[0]} {parts[2]}"
                    scientist = db.query(Scientist).filter(
                        Scientist.name.ilike(f'%{first_last}%')
                    ).first()
                    if scientist:
                        logger.debug(f"[DB lookup] {coauthor_name} → matched as '{scientist.name}' (no middle)")

            if not scientist:
                return {
                    "affiliation": "",
                    "h_index": None,
                    "openalex_id": "",
                    "specialty_tags": "",
                    "patents": [],
                    "corporates": [],
                    "institutions": [],
                }

            affiliation = scientist.affiliation or ""
            h_index = scientist.h_index
            openalex_id = scientist.openalex_id or ""

            # Get patents from two sources:
            # 1. Via junction table (if relationships exist)
            # 2. Via title matching with graph data (fallback for missing relationships)
            patents = scientist.patents if hasattr(scientist, 'patents') else []
            patents_list = list(patents)

            # If we have patent titles from graph, find them in batch (not N+1 queries)
            if patent_titles_from_graph:
                from sqlalchemy import or_

                # Build OR filter for all titles at once
                filters = [Patent.title.ilike(f'%{title[:50]}%') for title in patent_titles_from_graph]
                graph_patents = db.query(Patent).filter(or_(*filters)).all()

                # Add to list (deduplicate by ID)
                seen_patent_ids = {p.id for p in patents_list}
                for patent in graph_patents:
                    if patent.id not in seen_patent_ids:
                        patents_list.append(patent)
                        seen_patent_ids.add(patent.id)

            # Extract connected corporates and institutions from patents
            corporates = []
            institutions = []

            seen_corporates = set()
            seen_institutions = set()

            for patent in patents_list:
                # Add assignee as corporate
                if patent.assignee:
                    assignee_lower = patent.assignee.lower()
                    if assignee_lower not in seen_corporates:
                        corporates.append({
                            "id": f"patent_corp:{patent.assignee}",
                            "label": patent.assignee,
                            "type": "corporate",
                            "source": "patent_assignee"
                        })
                        seen_corporates.add(assignee_lower)

            # Get scientist's direct institution affiliation
            if scientist.affiliation:
                inst_lower = scientist.affiliation.lower()
                if inst_lower not in seen_institutions:
                    institutions.append({
                        "id": f"scientist_inst:{scientist.affiliation}",
                        "label": scientist.affiliation,
                        "type": "institution",
                        "source": "scientist_affiliation"
                    })
                    seen_institutions.add(inst_lower)

            # Format patents
            patent_list = []
            for p in patents_list:
                patent_list.append({
                    "patent_id": p.patent_id,
                    "title": p.title,
                    "publication_date": str(p.publication_date) if p.publication_date else None,
                    "link": p.link,
                    "assignee": p.assignee,
                })

            return {
                "affiliation": affiliation,
                "h_index": h_index,
                "openalex_id": openalex_id,
                "specialty_tags": scientist.specialty_tags or "",
                "patents": patent_list,
                "corporates": corporates,
                "institutions": institutions,
            }

        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not fetch DB data for {coauthor_name}: {e}")
        return {
            "affiliation": "",
            "h_index": None,
            "openalex_id": "",
            "specialty_tags": "",
            "patents": [],
            "corporates": [],
            "institutions": [],
        }


def _get_coauthor_patents(coauthor_name: str) -> list:
    """Get patents where coauthor is listed as inventor from DB."""
    try:
        from src.database.database import SessionLocal
        from src.database.models import Patent, Scientist

        db = SessionLocal()
        try:
            # Query via the relationship: find scientists matching the name, then their patents
            scientist = db.query(Scientist).filter(
                Scientist.name.ilike(f'%{coauthor_name}%')
            ).first()

            if not scientist:
                return []

            # Get all patents where this scientist is an inventor
            patents = scientist.patents if hasattr(scientist, 'patents') else []

            result = []
            for p in patents:
                result.append({
                    "patent_id": p.patent_id,
                    "title": p.title,
                    "publication_date": str(p.publication_date) if p.publication_date else None,
                    "link": p.link,
                    "assignee": p.assignee,
                })

            return result
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not fetch patents for {coauthor_name}: {e}")
        return []
