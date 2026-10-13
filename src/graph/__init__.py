#!/usr/bin/env python3
"""
Network graph building, visualization, and path analysis for KOL networks.

This module provides:
- GraphBuilder: Helper class for building graph structures
- build_graph_data: Main function to create graphs from Scholar/Patent data
- extract_two_hop_subgraph: Filter graph to N-hop neighborhood
- render_graph_html: Generate interactive HTML visualization
- path_finding: Sub-module for discovering and scoring relationship paths

Example:
    >>> from src.graph import build_graph_data, extract_two_hop_subgraph, render_graph_html
    >>> graph = build_graph_data("Marie Curie", scholar_data, patents_data)
    >>> subgraph = extract_two_hop_subgraph(graph, cutoff=2)
    >>> render_graph_html(subgraph, "network.html")

    >>> # Path finding
    >>> from src.graph.path_finding import find_paths, score_and_rank
    >>> paths = find_paths(graph)
    >>> targets = score_and_rank(paths)
"""
from .builder import GraphBuilder, build_graph_data
from .visualizer import extract_two_hop_subgraph, render_graph_html

# Re-export path_finding for convenience
from . import path_finding

__all__ = [
    "GraphBuilder",
    "build_graph_data",
    "extract_two_hop_subgraph",
    "render_graph_html",
    "path_finding",
]
