"""
Adapter to convert existing graph format to pathfinding format.

Converts the graph dict from src.graph.builder to Node/Edge objects.
"""
from typing import Dict, List, Any
from src.logger import logger

from .models import Node, Edge, NodeType, RelationType, Evidence


def adapt_graph(graph_dict: Dict[str, Any]) -> tuple[Dict[str, Node], List[Edge]]:
    """
    Convert existing graph dict to pathfinding format.

    Args:
        graph_dict: Graph dict from src.graph.builder.build_graph_data().
                   Expected keys: meta, nodes, edges.

    Returns:
        Tuple of (nodes_dict, edges_list).
    """
    logger.info("Converting existing graph to pathfinding format...")

    nodes_dict = {}
    edges_list = []

    # Convert nodes
    for node_data in graph_dict.get("nodes", []):
        node = _convert_node(node_data)
        if node:
            nodes_dict[node.id] = node

    # Convert edges (excluding citation edges)
    for edge_data in graph_dict.get("edges", []):
        edge = _convert_edge(edge_data)
        if edge:  # None for excluded edge types
            edges_list.append(edge)

    logger.info(
        f"Converted graph: {len(nodes_dict)} nodes, {len(edges_list)} edges"
    )

    return nodes_dict, edges_list


def _convert_node(node_data: Dict[str, Any]) -> Node:
    """Convert node dict to Node object."""
    node_id = node_data.get("id")
    node_type_str = node_data.get("type")
    label = node_data.get("label", "Unknown")

    # Map node types
    type_mapping = {
        "person": NodeType.PERSON,
        "publication": NodeType.PUBLICATION,
        "patent": NodeType.PUBLICATION,  # Patents as publications
        "institution": NodeType.ORGANIZATION,
        "corporate": NodeType.ORGANIZATION,
    }

    node_type = type_mapping.get(node_type_str, NodeType.ORGANIZATION)

    # Determine if corporate
    is_corporate = node_type_str == "corporate"

    # Extract metadata
    attributes = node_data.get("attributes", {})
    links = node_data.get("links", {})

    metadata = {
        **attributes,
        **links,
        "original_type": node_type_str,
        "role": node_data.get("role", [])
    }

    return Node(
        id=node_id,
        type=node_type,
        name=label,
        is_corporate=is_corporate,
        metadata=metadata
    )


def _convert_edge(edge_data: Dict[str, Any]) -> Edge:
    """Convert edge dict to Edge object."""
    source = edge_data.get("source")
    target = edge_data.get("target")
    edge_type_str = edge_data.get("type")

    # EXCLUDE citation edges - they don't represent real connections
    # A corporate citing a patent doesn't mean the inventor works for them
    if edge_type_str == "cites_patent":
        return None

    # Map edge types
    type_mapping = {
        "authored_by": RelationType.AUTHORED,
        "co_author_with": RelationType.COAUTHOR,
        "affiliated_with": RelationType.AFFILIATED,
        "has_patent": RelationType.AUTHORED,
        "assigned_to": RelationType.ASSIGNED_PATENT,
        "co_invented": RelationType.COAUTHOR,
        "co_invented_on": RelationType.AUTHORED,
    }

    relation_type = type_mapping.get(edge_type_str, RelationType.EMPLOYED)

    # Calculate score based on edge type and weight
    score = _calculate_edge_score(edge_type_str, edge_data)

    # Build evidence
    evidence = _build_evidence(edge_data)

    return Edge(
        source=source,
        target=target,
        relation_type=relation_type,
        score=score,
        evidence=evidence
    )


def _calculate_edge_score(edge_type: str, edge_data: Dict[str, Any]) -> float:
    """
    Calculate edge score based on type and attributes.

    Scoring policy (only VALID connections):
    - assigned_to (patent assignee): 0.95 - STRONGEST (inventor works for corporate)
    - has_patent: 0.9
    - authored_by: 0.8
    - affiliated_with: 0.7 - Direct affiliation with corporate
    - co_invented_on: 0.7
    - co_invented: 0.6-0.75 (based on weight)
    - co_author_with: 0.5-0.7 (based on weight)

    NOTE: cites_patent is EXCLUDED - citation doesn't imply connection
    """
    weight = edge_data.get("weight", 1)

    if edge_type == "assigned_to":
        # Patent assigned to corporate - strongest link
        return 0.95

    elif edge_type == "has_patent":
        return 0.9

    elif edge_type == "authored_by":
        return 0.8

    elif edge_type == "affiliated_with":
        # Direct affiliation with corporate
        return 0.7

    elif edge_type == "co_invented_on":
        return 0.7

    elif edge_type == "co_invented":
        # Co-invention - scales with number of joint patents
        base = 0.6
        bonus = min(weight * 0.05, 0.15)
        return base + bonus

    elif edge_type == "co_author_with":
        # Co-authorship - scales with number of collaborations
        base = 0.5
        bonus = min(weight * 0.05, 0.2)  # Max +0.2
        return base + bonus

    else:
        return 0.5  # Default


def _build_evidence(edge_data: Dict[str, Any]) -> Evidence:
    """Build Evidence object from edge data."""
    attributes = edge_data.get("attributes", {})
    evidence_list = edge_data.get("evidence", [])

    # Get URL from evidence list
    url = None
    if evidence_list:
        first_evidence = evidence_list[0]
        url = first_evidence.get("url")

    # Get year
    year = attributes.get("year")

    # Get title/label
    title = attributes.get("from", edge_data.get("type"))

    return Evidence(
        source="database",
        year=year,
        title=title,
        url=url,
        confidence=1.0
    )
