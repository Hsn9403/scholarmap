#!/usr/bin/env python3
"""
Enrich person nodes with full names from database.

This module enriches graph person nodes by replacing abbreviated names
(e.g., "J. Simmchen") with full names from the database (e.g., "Juliane Simmchen").
"""
from typing import Dict, Any
from sqlalchemy.orm import Session, defer
from src.database.models import Scientist
from src.helpers import slug
from src.logger import logger


def enrich_persons_from_db(
    graph: Dict[str, Any],
    db: Session,
    allow_api_fallback: bool = False,
    max_api_enrichments: int = 10,
) -> Dict[str, Any]:
    """
    Enrich person nodes with data from database (and optionally Scholar API).

    For abbreviated names: resolves to full name from DB.
    For full names without enrichment: adds h_index/scholar_url from DB.
    API fallback (disabled by default): for nodes with scholar_id but no h_index,
    fetches h_index from Scholar API — limited to top N collaborators.

    Args:
        graph: Graph dict with nodes and edges
        db: Database session
        allow_api_fallback: If True, fetch h_index via API when missing from DB.
                           WARNING: costs ~1 API call per person enriched this way.
        max_api_enrichments: Max nodes to enrich via API (ranked by collaborations).

    Returns:
        Enriched graph with updated person names and attributes
    """
    logger.info("Enriching person nodes with full names from database...")

    # Charger uniquement les colonnes nécessaires — évite de charger les objets ORM complets
    # (graph_html peut faire 1-5 MB par row, et l'identity map SQLAlchemy garde tout en RAM)
    rows = db.query(
        Scientist.name,
        Scientist.scholar_id,
        Scientist.h_index,
        Scientist.affiliation,
        Scientist.scholar_url,
    ).filter(
        Scientist.name.isnot(None)
    ).all()

    # Wrap rows in lightweight objects for compatibility with existing code
    class _ScientistRow:
        __slots__ = ('name', 'scholar_id', 'h_index', 'affiliation', 'scholar_url')
        def __init__(self, row):
            self.name = row.name
            self.scholar_id = row.scholar_id
            self.h_index = row.h_index
            self.affiliation = row.affiliation
            self.scholar_url = row.scholar_url

    scientists = [_ScientistRow(r) for r in rows]
    del rows

    # Create lookup dictionaries
    by_normalized_name = {}
    by_scholar_id = {}

    def _enrichment_score(s) -> int:
        score = 0
        if s.h_index is not None:
            score += 100 + s.h_index
        if s.scholar_id:
            score += 50
        if s.scholar_url:
            score += 20
        if s.affiliation:
            score += 5
        return score

    for scientist in scientists:
        # Check if name is abbreviated (single letter first name)
        parts = scientist.name.strip().split()
        if len(parts) >= 2:
            first = parts[0].replace('.', '').strip()
            is_abbreviated = len(first) == 1

            # Only add to lookup if name is NOT abbreviated (full name)
            if not is_abbreviated:
                normalized = slug(scientist.name)
                # Keep the most enriched entry when duplicates exist
                if normalized not in by_normalized_name or \
                        _enrichment_score(scientist) > _enrichment_score(by_normalized_name[normalized]):
                    by_normalized_name[normalized] = scientist

                if scientist.scholar_id:
                    by_scholar_id[scientist.scholar_id] = scientist

    logger.info(f"Found {len(by_normalized_name)} scientists with full names in DB")

    # Enrich person nodes in graph
    enriched_count = 0

    for node in graph.get("nodes", []):
        if node.get("type") != "person":
            continue

        node_id = node.get("id", "")
        current_label = node.get("label", "")

        parts = current_label.strip().split()
        is_abbreviated = len(parts) >= 2 and len(parts[0].replace('.', '').strip()) == 1

        # For full names: only enrich if missing h_index AND scholar_url (avoid overwriting)
        attrs = node.get("attributes", {})
        links = node.get("links", {})
        already_enriched = attrs.get("h_index") is not None or links.get("scholar_profile")
        if not is_abbreviated and already_enriched:
            continue

        # Try to find matching scientist in DB
        matched_scientist = None

        # Method 1: Match by scholar_id from node attributes
        scholar_id = attrs.get("scholar_id")
        if scholar_id and scholar_id in by_scholar_id:
            matched_scientist = by_scholar_id[scholar_id]

        # Method 2: Try matching by normalized name
        if not matched_scientist and len(parts) >= 2:
            last_name = parts[-1].lower()
            first_part = parts[0].replace('.', '').strip().lower()

            if is_abbreviated:
                # Abbreviated: match by last name + initial, collect all candidates
                candidates = []
                for normalized, scientist in by_normalized_name.items():
                    scientist_parts = scientist.name.strip().split()
                    if len(scientist_parts) >= 2:
                        scientist_last = scientist_parts[-1].lower()
                        scientist_first = scientist_parts[0].replace('.', '').strip().lower()
                        if scientist_last == last_name and scientist_first.startswith(first_part):
                            candidates.append(scientist)

                if len(candidates) == 1:
                    matched_scientist = candidates[0]
                elif len(candidates) > 1:
                    logger.warning(
                        f"⚠ Ambiguous match for '{current_label}': "
                        f"{[c.name for c in candidates]} — keeping abbreviated form"
                    )
            else:
                # Full name: exact match only (normalized slug)
                exact_key = slug(current_label)
                if exact_key in by_normalized_name:
                    matched_scientist = by_normalized_name[exact_key]

        # Update node if match found
        if matched_scientist:
            old_label = node["label"]
            new_label = matched_scientist.name
            new_id = f"person:{slug(matched_scientist.name)}"

            # Update node
            node["label"] = new_label
            node["id"] = new_id

            # Update attributes
            if "attributes" not in node:
                node["attributes"] = {}

            # API fallback: only when explicitly enabled AND scholar_id known but h_index missing
            if allow_api_fallback and matched_scientist.scholar_id and not matched_scientist.h_index:
                collab_count = node.get("attributes", {}).get("collaborations_with_seed", 0)
                node["_api_fallback_collab"] = collab_count  # tag for later sorting

            if matched_scientist.scholar_id:
                node["attributes"]["scholar_id"] = matched_scientist.scholar_id
            if matched_scientist.h_index:
                node["attributes"]["h_index"] = matched_scientist.h_index
            if matched_scientist.affiliation:
                node["attributes"]["affiliation"] = matched_scientist.affiliation

            # Update links (scholar_url goes in links for visualizer)
            if "links" not in node:
                node["links"] = {}

            if matched_scientist.scholar_url:
                node["links"]["scholar_profile"] = matched_scientist.scholar_url

            logger.info(f"✨ Enriched: '{old_label}' → '{new_label}'")
            enriched_count += 1

            # Update edges that reference this node
            old_node_id = node_id
            for edge in graph.get("edges", []):
                if edge.get("source") == old_node_id:
                    edge["source"] = new_id
                if edge.get("target") == old_node_id:
                    edge["target"] = new_id

    logger.info(f"✅ Enriched {enriched_count} person nodes from DB")

    # API fallback: fetch h_index for tagged nodes (scholar_id known, h_index missing)
    # Only runs when allow_api_fallback=True, limited to top max_api_enrichments by collaborations
    if allow_api_fallback:
        api_candidates = [
            n for n in graph.get("nodes", [])
            if "_api_fallback_collab" in n
        ]
        api_candidates.sort(key=lambda n: n.get("_api_fallback_collab", 0), reverse=True)
        api_candidates = api_candidates[:max_api_enrichments]

        if api_candidates:
            try:
                from src.scholar.client import ScholarClient
                scholar_client = ScholarClient()
                api_enriched = 0
                for node in api_candidates:
                    sid = node.get("attributes", {}).get("scholar_id")
                    if not sid:
                        continue
                    try:
                        author_data = scholar_client.fetch_author_data(sid, num_articles=0)
                        if author_data and author_data.h_index:
                            node["attributes"]["h_index"] = author_data.h_index
                            if author_data.affiliation:
                                node["attributes"]["affiliation"] = author_data.affiliation
                            logger.info(
                                f"  ✅ API h_index for '{node['label']}': {author_data.h_index}"
                            )
                            api_enriched += 1
                    except Exception as e:
                        logger.debug(f"  Could not fetch h_index for '{node['label']}': {e}")
                logger.info(f"✅ API fallback enriched {api_enriched} nodes")
            except Exception as e:
                logger.warning(f"Could not initialize ScholarClient for API fallback: {e}")

        # Clean up temporary tags
        for node in graph.get("nodes", []):
            node.pop("_api_fallback_collab", None)

    return graph
