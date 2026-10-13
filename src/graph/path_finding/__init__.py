#!/usr/bin/env python3
"""
Path-finding module for KOL network analysis.

This module provides tools for discovering, scoring, and explaining
relationship paths in the KOL network graph.

Main Components:
    - Schema: Path patterns (H1/H2/H3) and evidence levels (HARD/MEDIUM/SOFT)
    - PathFinder: Discovers paths matching defined patterns
    - PathScorer: Scores and ranks paths by relationship strength
    - PathExplainer: Generates human-readable explanations

Example Usage:
    >>> from src.graph.builder import build_graph_data
    >>> from src.graph.path_finding import (
    ...     find_paths, score_and_rank, generate_report
    ... )
    >>>
    >>> # Build graph from Scholar/Patents data
    >>> graph = build_graph_data("Marie Curie", scholar_data, patents_data)
    >>>
    >>> # Find all relationship paths
    >>> paths = find_paths(graph)
    >>>
    >>> # Score and rank by target
    >>> targets = score_and_rank(paths)
    >>>
    >>> # Generate report
    >>> report = generate_report(targets, "Marie Curie")
"""
from .schema import (
    # Enums
    EvidenceLevel,
    Hypothesis,
    # Pattern class
    PathPattern,
    # Predefined patterns
    H1_DIRECT_ASSIGNEE,
    H1_CURRENT_AFFILIATION,
    H2_CITED_BY_COMPANY,
    H2_VIA_COINVENTION,
    H3_CITES_COMPANY,
    H3_SHARED_COINVENTOR,
    H3_MUTUAL_CITATION,
    # Pattern registries
    ALL_PATTERNS,
    PATTERNS_BY_ID,
    PATTERNS_BY_HYPOTHESIS,
    PATTERNS_BY_EVIDENCE,
    # Lookup functions
    get_pattern,
    get_patterns_for_hypothesis,
    get_patterns_for_evidence,
)

from .path_finder import (
    FoundPath,
    GraphIndex,
    PathFinder,
    find_paths,
)

from .scoring import (
    ScoredPath,
    TargetScore,
    PathScorer,
    score_and_rank,
    get_top_connections,
)

from .explain import (
    PathExplanation,
    TargetExplanation,
    PathExplainer,
    explain_paths,
    explain_targets,
    generate_report,
)


__all__ = [
    # Schema - Enums
    "EvidenceLevel",
    "Hypothesis",
    # Schema - Classes
    "PathPattern",
    # Schema - Predefined patterns
    "H1_DIRECT_ASSIGNEE",
    "H1_CURRENT_AFFILIATION",
    "H2_CITED_BY_COMPANY",
    "H2_VIA_COINVENTION",
    "H3_CITES_COMPANY",
    "H3_SHARED_COINVENTOR",
    "H3_MUTUAL_CITATION",
    # Schema - Registries
    "ALL_PATTERNS",
    "PATTERNS_BY_ID",
    "PATTERNS_BY_HYPOTHESIS",
    "PATTERNS_BY_EVIDENCE",
    "get_pattern",
    "get_patterns_for_hypothesis",
    "get_patterns_for_evidence",
    # Path Finder
    "FoundPath",
    "GraphIndex",
    "PathFinder",
    "find_paths",
    # Scoring
    "ScoredPath",
    "TargetScore",
    "PathScorer",
    "score_and_rank",
    "get_top_connections",
    # Explanation
    "PathExplanation",
    "TargetExplanation",
    "PathExplainer",
    "explain_paths",
    "explain_targets",
    "generate_report",
]
