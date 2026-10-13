#!/usr/bin/env python3
"""
Enrich graph with patents from database.

This module adds patent nodes from the database to the graph.
"""
from typing import Dict, Any
from sqlalchemy.orm import Session
from src.database.models import Scientist, Patent
from src.helpers import slug
from src.graph.builder import _normalize_corp_name
from src.logger import logger


_INSTITUTION_PATTERNS = (
    "universit", "ecole", "school", "college", "institut", "academi",
    "laborat", "hospital", "clinique", "clinic", "chu", "chru",
    "cnrs", "inserm", "inria", "anrs",
)


def _classify_org(name: str) -> str:
    n = name.lower()
    for pat in _INSTITUTION_PATTERNS:
        if pat in n:
            return "institution"
    return "corporate"


def _add_org_node_and_edge(
    graph: Dict[str, Any],
    org_name: str,
    patent_node_id: str,
    edge_type: str,
    link: str = None,
    connection_info: dict = None,
) -> None:
    """Add an organisation node + edge to graph (assignee or citing company)."""
    org_canonical = _normalize_corp_name(org_name)
    org_type = _classify_org(org_canonical)
    org_id = f"{org_type}:{slug(org_canonical)}"

    existing_ids = {n["id"] for n in graph["nodes"]}
    if org_id not in existing_ids:
        graph["nodes"].append({
            "id": org_id,
            "type": org_type,
            "label": org_canonical,
            "attributes": {"org_kind": org_type, "connections": []},
            "links": {"patents_url": link or ""}
        })

    # Append connection provenance to the node (regardless of whether node is new or existing)
    if connection_info:
        for node in graph["nodes"]:
            if node.get("id") == org_id:
                node.setdefault("attributes", {}).setdefault("connections", [])
                node["attributes"]["connections"].append(connection_info)
                break

    # Avoid duplicate edges
    edge_id = f"e:{org_id}__{edge_type}__{patent_node_id}"
    existing_edge_ids = {e.get("id") for e in graph["edges"]}
    if edge_id not in existing_edge_ids:
        graph["edges"].append({
            "id": edge_id,
            "source": org_id,
            "target": patent_node_id,
            "type": edge_type,
            "label": edge_type.replace("_", " "),
            "evidence": [{"kind": "url", "label": "Google Patents", "url": link}] if link else []
        })


def enrich_patents_from_db(graph: Dict[str, Any], db: Session, researcher_name: str) -> Dict[str, Any]:
    """
    Enrich graph with patents from database.

    Adds patent nodes for the researcher if they exist in the DB.

    Args:
        graph: Graph dict with nodes and edges
        db: Database session
        researcher_name: Name of the researcher

    Returns:
        Enriched graph with patent nodes
    """
    logger.info("Enriching graph with patents from database...")

    # Find the researcher in DB
    # Try by normalized_name first
    scientist = db.query(Scientist).filter(
        Scientist.normalized_name == slug(researcher_name)
    ).first()

    # Fallback: search by exact name if normalized_name didn't work
    if not scientist:
        scientist = db.query(Scientist).filter(
            Scientist.name == researcher_name
        ).first()

    # Fallback: search by case-insensitive name
    if not scientist:
        scientist = db.query(Scientist).filter(
            Scientist.name.ilike(researcher_name)
        ).first()

    if not scientist:
        logger.warning(f"Researcher '{researcher_name}' not found in DB")
        return graph

    # Get patents for this scientist
    patents = db.query(Patent).join(Patent.inventors).filter(
        Scientist.id == scientist.id
    ).all()

    if not patents:
        logger.info(f"No patents found in DB for {researcher_name}")
        return graph

    logger.info(f"Found {len(patents)} patents in DB for {researcher_name}")

    seed_person_id = graph.get("meta", {}).get("seed_person_id", "")

    # Add patent nodes and edges
    patents_added = 0

    for patent in patents:
        patent_id = f"patent:{slug(patent.title[:50])}"  # Use first 50 chars of title

        patent_already_exists = any(node.get("id") == patent_id for node in graph.get("nodes", []))

        if not patent_already_exists:
            # Get co-inventors (all inventors except the researcher)
            co_inventors = [inv.name for inv in patent.inventors if inv.name != researcher_name]

            # Parse claims from claims_excerpt
            claims_top3 = []
            if patent.claims_excerpt:
                import re
                claims = re.split(r'\d+\.\s+', patent.claims_excerpt)
                claims = [c.strip() for c in claims if c.strip()]
                claims_top3 = claims[:3]

            # Add patent node
            patent_node = {
                "id": patent_id,
                "type": "patent",
                "label": patent.patent_id or patent.title[:60] + "...",
                "attributes": {
                    "patent_id": patent.patent_id,
                    "title": patent.title,
                    "publication_date": str(patent.publication_date) if patent.publication_date else None,
                    "filing_date": str(patent.filing_date) if patent.filing_date else None,
                    "priority_date": str(patent.priority_date) if patent.priority_date else None,
                    "assignee": patent.assignee,
                    "current_assignee": patent.assignee,
                    "co_inventors": co_inventors,
                    "claims_top3": claims_top3,
                    "cited_by": patent.cited_by_count,
                    "link": patent.link
                },
                "links": {
                    "patents_url": patent.link
                }
            }

            graph["nodes"].append(patent_node)

            # Add edge: seed → patent (has_patent)
            graph["edges"].append({
                "source": seed_person_id,
                "target": patent_id,
                "type": "has_patent",
                "label": "invented"
            })

        # Add co-inventor nodes and edges (mirrors builder.py logic)
        # Always runs even if patent node was already in graph
        existing_node_ids = {n["id"] for n in graph["nodes"]}
        existing_edge_ids = {e.get("id") for e in graph["edges"]}
        for inv in patent.inventors:
            if inv.name == researcher_name:
                continue
            co_id = f"person:{slug(inv.name)}"

            if co_id not in existing_node_ids:
                graph["nodes"].append({
                    "id": co_id,
                    "type": "person",
                    "label": inv.name,
                    "role": ["co_inventor"],
                    "attributes": {
                        "affiliation": inv.affiliation or "",
                        "scholar_id": inv.scholar_id or "",
                    },
                    "links": {}
                })
                existing_node_ids.add(co_id)

            # seed → co-inventor (aggregated co-invention link)
            edge_seed_co = f"e:{seed_person_id}__co_invented__{co_id}"
            if edge_seed_co not in existing_edge_ids:
                graph["edges"].append({
                    "id": edge_seed_co,
                    "source": seed_person_id,
                    "target": co_id,
                    "type": "co_invented",
                    "attributes": {"via": ["patents"]},
                    "evidence": [{"kind": "patent", "patent_id": patent.patent_id, "title": patent.title, "url": patent.link or ""}]
                })
                existing_edge_ids.add(edge_seed_co)

            # co-inventor → patent (link to specific patent)
            edge_co_pat = f"e:{co_id}__co_invented_on__{patent_id}"
            if edge_co_pat not in existing_edge_ids:
                graph["edges"].append({
                    "id": edge_co_pat,
                    "source": co_id,
                    "target": patent_id,
                    "type": "co_invented_on",
                    "attributes": {"patent_id": patent.patent_id or ""},
                    "evidence": [{"kind": "patent", "patent_id": patent.patent_id, "title": patent.title, "url": patent.link or ""}]
                })
                existing_edge_ids.add(edge_co_pat)

        # Add assignee node (current owner of the patent)
        if patent.assignee:
            _add_org_node_and_edge(
                graph, patent.assignee, patent_id, "assigned_to", patent.link,
                connection_info={
                    "scientist_name": researcher_name,
                    "affiliation_type": "patent_assignee",
                    "notes": f"Assignee du brevet : {patent.title[:100]}",
                    "evidence": [{"kind": "patent", "patent_id": patent.patent_id, "title": patent.title, "url": patent.link or ""}],
                }
            )
            # Direct edge: seed → corporate/institution (distance 1)
            # Without this, BFS from seed can't reach assignee corporates
            # because the existing edge is corporate→patent (reverse direction).
            org_canonical = _normalize_corp_name(patent.assignee)
            org_type = _classify_org(org_canonical)
            org_id = f"{org_type}:{slug(org_canonical)}"
            direct_edge_id = f"e:{seed_person_id}__inventor_for__{org_id}"
            existing_edge_ids_check = {e.get("id") for e in graph["edges"]}
            if direct_edge_id not in existing_edge_ids_check:
                graph["edges"].append({
                    "id": direct_edge_id,
                    "source": seed_person_id,
                    "target": org_id,
                    "type": "inventor_for",
                    "label": "inventeur pour",
                    "attributes": {
                        "affiliation_type": "patent_assignee",
                        "notes": f"Inventeur du brevet : {patent.title[:100]}",
                    },
                    "evidence": [{"kind": "patent", "patent_id": patent.patent_id, "title": patent.title, "url": patent.link or ""}]
                })

        # Add citing companies from citing_patents_json
        citing_patents = patent.citing_patents_json or []
        for citing in citing_patents:
            if not isinstance(citing, dict):
                continue
            assignee = (citing.get("assignee") or "").strip()
            if not assignee:
                continue
            # Skip self-citations (same assignee as the patent itself)
            if patent.assignee and assignee.lower() == patent.assignee.lower():
                continue
            _add_org_node_and_edge(
                graph, assignee, patent_id, "cites_patent", citing.get("link"),
                connection_info={
                    "scientist_name": researcher_name,
                    "affiliation_type": "patent_citation",
                    "notes": f"A cité le brevet : {patent.title[:100]}",
                    "evidence": [{"kind": "patent", "patent_id": citing.get("patent_id"), "title": patent.title, "url": citing.get("link") or ""}],
                }
            )
            logger.debug(f"    ↳ Citing company: {assignee}")

        if not patent_already_exists:
            patents_added += 1
        logger.info(f"  ✅ Processed patent: {patent.title[:50]}...")

    logger.info(f"✅ Added {patents_added} patents from DB to graph")

    return graph
