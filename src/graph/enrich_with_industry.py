#!/usr/bin/env python3
"""
Enrich graph with industry connections from database.

This module provides functions to add Corporate nodes and edges
to an existing graph built from Scholar/Patents data.
"""
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from src.database.models import Scientist, Corporate
from src.database.add_coauthor_industry_connections import ScientistCorporate
from src.helpers import slug, strip_accents_basic
from src.logger import logger


_INSTITUTION_PATTERNS = re.compile(
    r"""
    universi        # university / université / universite / universitat / universidad
    | \becole\b     # école (accents stripped → ecole)
    | \bschool\b
    | \bcollege\b
    | \binstitut    # institute / institutes / institution / instituto / institit
    | \bacademi     # academy / académie
    | \bfacult      # faculty / faculté
    | \blaboratoir  # laboratoire
    | \blaboratory\b
    | \bchu\b       # centre hospitalier universitaire
    | \bchru\b
    | \bhospital\b
    | \bclinique\b
    | \bclinic\b
    | foundation.*(?:research|education|medical|health)
    | (?:research|education|medical).*foundation
    | \bcnrs\b
    | \binserm\b
    | \binria\b
    | \banrs\b
    | \bifsttar\b
    | \bnih\b       # National Institutes of Health (US)
    | \bnichd\b     # National Institute of Child Health
    | \bncats?\b    # National Center for Advancing Translational Sciences
    | \bnimh\b      # National Institute of Mental Health
    | \bnhlbi\b     # National Heart, Lung, and Blood Institute
    | \bninds?\b    # National Institute of Neurological Disorders
    | \bnci\b       # National Cancer Institute
    | \bniaid\b     # National Institute of Allergy and Infectious Diseases
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_person_title(name: str) -> bool:
    """
    Return True if the name starts with a personal title (Dr, Pr, Prof, etc.).
    These entries are persons, not corporates.

    Examples:
        >>> _is_person_title("Dr Benoît Trojak")
        True
        >>> _is_person_title("Pr Édouard Hirsch")
        True
        >>> _is_person_title("Renault SAS")
        False
    """
    first_word = (name or "").strip().split()[0].lower().rstrip(".") if (name or "").strip() else ""
    return first_word in {"dr", "pr", "prof", "professor", "docteur", "professeur"}


def _is_institution(name: str) -> bool:
    """
    Return True if the name strongly suggests a public/academic institution
    rather than a commercial corporate.

    Examples:
        >>> _is_institution("Universite de Bordeaux")
        True
        >>> _is_institution("Renault SAS")
        False
        >>> _is_institution("Mayo Foundation for Medical Education and Research")
        True
    """
    normalized = strip_accents_basic(name or "").lower()
    return bool(_INSTITUTION_PATTERNS.search(normalized))


def _is_name_too_short(name: str) -> bool:
    """
    Check if a name is too short/abbreviated to reliably associate with corporates.

    Returns True if the first name is just an initial (e.g., "A Nedelec", "J. Smith").
    This prevents false associations when we only have abbreviated names.

    Args:
        name: The person's name

    Returns:
        True if name is too short/abbreviated (first name is just an initial)

    Examples:
        >>> _is_name_too_short("A Nedelec")
        True
        >>> _is_name_too_short("J. Smith")
        True
        >>> _is_name_too_short("Andre Imbert")
        False
        >>> _is_name_too_short("Alice Nedelec")
        False
    """
    parts = name.strip().split()
    if len(parts) < 2:
        return True

    # Check if first part is just an initial (1-2 chars, potentially with a dot)
    first_part = parts[0].replace(".", "").strip()
    return len(first_part) <= 1


def enrich_graph_with_industry_connections(
    graph: Dict[str, Any],
    db: Session,
    add_coauthor_nodes: bool = False
) -> Dict[str, Any]:
    """
    Enrich an existing graph with industry connections from the database.

    This function:
    1. Looks for ScientistCorporate relationships in the database
    2. For co-authors already in the graph, adds their Corporate affiliations
    3. Adds Corporate nodes (companies)
    4. Adds edges: co-author → corporate

    Args:
        graph: Existing graph dict with keys: meta, nodes, edges.
        db: Database session.
        add_coauthor_nodes: If True, add co-authors not already in graph
                           BUT ONLY if they are connected to someone in the graph
                           (default: False - only enrich existing co-authors).

    Returns:
        Enriched graph dict.

    Example:
        >>> graph = build_graph_data("Andre Imbert", scholar, patents)
        >>> enriched = enrich_graph_with_industry_connections(graph, db)
        >>> # Now graph has Corporate nodes for Meta, OHB, etc.
    """
    logger.info("Enriching graph with industry connections from database...")

    # Get all person nodes in the graph
    person_nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node.get("type") == "person"
    }

    # Build label-slug → [node_id, ...] index to handle disambiguated homonym nodes
    # (e.g. "person:paul_martin" AND "person:paul_martin__a5026234567" both map to slug "paul_martin")
    label_slug_to_ids: dict = {}
    for nid, node in person_nodes.items():
        lslug = slug(node.get("label", ""))
        label_slug_to_ids.setdefault(lslug, []).append(nid)

    logger.info(f"Found {len(person_nodes)} person nodes in graph")

    # Build set of all author names across all publication nodes
    # Used to verify that a DB scientist is actually a co-author of the seed researcher
    pub_author_slugs: set = set()
    for node in graph["nodes"]:
        if node.get("type") == "publication":
            for author_name in (node.get("attributes", {}).get("authors") or []):
                if author_name:
                    pub_author_slugs.add(slug(author_name))

    # Seed node ID (to connect new co-author nodes)
    seed_node_id = graph.get("meta", {}).get("seed_person_id")

    # Query only the columns we need — avoids loading graph_html (MB per scientist) into RAM
    scientist_corporate_links = (
        db.query(
            Scientist.name,
            Scientist.h_index,
            Scientist.affiliation,
            Scientist.scholar_id,
            Scientist.scholar_url,
            Corporate.name.label("corporate_name"),
            Corporate.country,
            Corporate.notes.label("corporate_notes"),
            Corporate.normalized_name,
            ScientistCorporate.affiliation_type,
            ScientistCorporate.notes.label("link_notes"),
            ScientistCorporate.evidence_data,
        )
        .join(ScientistCorporate, Scientist.id == ScientistCorporate.scientist_id)
        .join(Corporate, Corporate.id == ScientistCorporate.corporate_id)
        .all()
    )

    logger.info(f"Found {len(scientist_corporate_links)} scientist-corporate links in DB")

    # Track which corporates we've added
    corporates_added = set()
    edges_added = 0
    nodes_added = 0

    # Dict index for O(1) node lookup instead of O(n) scan per link
    nodes_by_id: dict = {node["id"]: node for node in graph["nodes"]}

    for row in scientist_corporate_links:
        # Skip scientists with abbreviated names (initials only)
        if _is_name_too_short(row.name):
            logger.debug(f"Skipping scientist with abbreviated name: {row.name}")
            continue

        scientist_slug = slug(row.name)
        matched_node_ids = list(label_slug_to_ids.get(scientist_slug, []))

        if not matched_node_ids:
            # Scientist not yet in graph — add only if they appear in seed's publications
            if scientist_slug not in pub_author_slugs or not seed_node_id:
                logger.debug(f"Scientist not in graph or not in publications, skipping: {row.name}")
                continue

            scientist_node_id = f"person:{scientist_slug}"
            new_person_node = {
                "id": scientist_node_id,
                "type": "person",
                "label": row.name,
                "attributes": {
                    "h_index": row.h_index,
                    "affiliation": row.affiliation,
                    "scholar_id": row.scholar_id,
                },
                "links": {
                    "scholar_profile": row.scholar_url or (
                        f"https://scholar.google.com/citations?user={row.scholar_id}"
                        if row.scholar_id else ""
                    )
                }
            }
            graph["nodes"].append(new_person_node)
            nodes_by_id[scientist_node_id] = new_person_node
            person_nodes[scientist_node_id] = new_person_node
            label_slug_to_ids.setdefault(scientist_slug, []).append(scientist_node_id)
            matched_node_ids = [scientist_node_id]
            nodes_added += 1

            graph["edges"].append({
                "source": seed_node_id,
                "target": scientist_node_id,
                "type": "co_author_with",
                "label": "co-author",
                "attributes": {"collaborations_with_seed": 0}
            })
            logger.info(f"Added co-author node (corporate link): {row.name}")

        # Classify corporate node type
        if _is_person_title(row.corporate_name):
            node_type = "person"
        elif _is_institution(row.corporate_name):
            node_type = "institution"
        else:
            node_type = "corporate"
        corporate_node_id = f"{node_type}:{slug(row.corporate_name)}"

        if corporate_node_id not in corporates_added:
            corporate_node = {
                "id": corporate_node_id,
                "type": node_type,
                "label": row.corporate_name,
                "attributes": {
                    "country": row.country or "Unknown",
                    "notes": row.corporate_notes,
                    "normalized_name": row.normalized_name,
                    "connections": []
                }
            }
            graph["nodes"].append(corporate_node)
            nodes_by_id[corporate_node_id] = corporate_node
            corporates_added.add(corporate_node_id)
            nodes_added += 1
            logger.info(f"Added corporate node: {row.corporate_name}")

        # Add connection evidence via O(1) dict lookup
        corp_node = nodes_by_id.get(corporate_node_id)
        if corp_node:
            if "connections" not in corp_node["attributes"]:
                corp_node["attributes"]["connections"] = []
            corp_node["attributes"]["connections"].append({
                "scientist_name": row.name,
                "affiliation_type": row.affiliation_type,
                "notes": row.link_notes,
                "evidence": row.evidence_data.get("evidence", []) if row.evidence_data else []
            })

        # Add edge: scientist → corporate/institution
        for scientist_node_id in matched_node_ids:
            graph["edges"].append({
                "source": scientist_node_id,
                "target": corporate_node_id,
                "type": f"affiliated_with_{node_type}",
                "label": f"{row.affiliation_type}",
                "attributes": {
                    "affiliation_type": row.affiliation_type,
                    "notes": row.link_notes,
                    "evidence_data": row.evidence_data
                }
            })
            edges_added += 1
            logger.debug(f"Added edge: {row.name} ({scientist_node_id}) → {row.corporate_name}")

    # Update metadata
    graph["meta"]["nodes_count"] = len(graph["nodes"])
    graph["meta"]["edges_count"] = len(graph["edges"])
    graph["meta"]["corporates_count"] = len(corporates_added)
    graph["meta"]["industry_enriched"] = True

    logger.info(f"✓ Graph enriched: +{nodes_added} nodes, +{edges_added} edges")
    logger.info(f"  Total corporates: {len(corporates_added)}")

    return graph


def get_industry_connections_for_person(
    person_name: str,
    db: Session
) -> Dict[str, Any]:
    """
    Get industry connections for a specific person from the database.

    Args:
        person_name: Name of the person.
        db: Database session.

    Returns:
        Dict with industry connections:
        {
            "person": "...",
            "connections": [
                {"company": "Meta", "type": "employment", ...},
                ...
            ]
        }
    """
    scientist = db.query(Scientist).filter_by(
        normalized_name=slug(person_name)
    ).first()

    if not scientist:
        return {"person": person_name, "connections": []}

    links = (
        db.query(Corporate, ScientistCorporate)
        .join(ScientistCorporate, Corporate.id == ScientistCorporate.corporate_id)
        .filter(ScientistCorporate.scientist_id == scientist.id)
        .all()
    )

    connections = [
        {
            "company": corporate.name,
            "company_id": corporate.id,
            "country": corporate.country,
            "affiliation_type": link.affiliation_type,
            "notes": link.notes
        }
        for corporate, link in links
    ]

    return {
        "person": scientist.name,
        "person_id": scientist.id,
        "connections": connections
    }
