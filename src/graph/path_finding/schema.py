#!/usr/bin/env python3
"""
Path pattern schema for KOL network analysis.

This module defines the types of paths we search for in the graph,
their evidence levels, and metadata for interpretation.

Evidence Levels:
    - HARD: Direct, verifiable relationships (e.g., patent ownership)
    - MEDIUM: Indirect but strong signals (e.g., cited by company)
    - SOFT: Weak signals requiring interpretation (e.g., cites company's patent)

Hypotheses:
    - H1: Direct connection to organization (assignee, affiliate)
    - H2: Indirect connection via intermediary (co-inventor, citation)
    - H3: Weak/distant connection (mutual citations, shared domain)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EvidenceLevel(Enum):
    """Evidence strength classification."""
    HARD = "hard"      # Direct, verifiable relationship
    MEDIUM = "medium"  # Indirect but meaningful signal
    SOFT = "soft"      # Weak signal, requires interpretation


class Hypothesis(Enum):
    """Hypothesis level for path interpretation."""
    H1 = "H1"  # Direct connection
    H2 = "H2"  # Indirect connection (1 intermediary)
    H3 = "H3"  # Weak/distant connection (2+ intermediaries)


@dataclass
class PathPattern:
    """
    Definition of a path pattern to search for in the graph.

    Attributes:
        pattern_id: Unique identifier for this pattern.
        name: Human-readable name.
        description: Detailed description of what this pattern reveals.
        hypothesis: H1/H2/H3 classification.
        evidence_level: HARD/MEDIUM/SOFT classification.
        edge_sequence: List of (edge_type, direction) tuples.
                       direction: "out" = source→target, "in" = target→source
        node_types: Expected node types at each step (optional constraints).
        weight_factors: How edge weights affect path score.
    """
    pattern_id: str
    name: str
    description: str
    hypothesis: Hypothesis
    evidence_level: EvidenceLevel
    edge_sequence: List[Tuple[str, str]]  # [(edge_type, direction), ...]
    node_types: Optional[List[Optional[str]]] = None
    weight_factors: Dict[str, float] = field(default_factory=dict)

    @property
    def path_length(self) -> int:
        """Number of edges in this pattern."""
        return len(self.edge_sequence)


# =============================================================================
# H1 Patterns - Direct Connections (HARD evidence)
# =============================================================================

H1_DIRECT_ASSIGNEE = PathPattern(
    pattern_id="H1_direct_assignee",
    name="Direct Patent Assignee",
    description="Seed person has a patent assigned to this organization. "
                "This is strong evidence of employment or business relationship.",
    hypothesis=Hypothesis.H1,
    evidence_level=EvidenceLevel.HARD,
    edge_sequence=[
        ("has_patent", "out"),      # Seed → Patent
        ("assigned_to", "out"),     # Patent → Organization
    ],
    node_types=["person", "patent", None],  # End can be corporate/institution
    weight_factors={"has_patent": 1.0, "assigned_to": 1.0},
)

H1_CURRENT_AFFILIATION = PathPattern(
    pattern_id="H1_current_affiliation",
    name="Current Affiliation",
    description="Seed person is affiliated with this organization (from Scholar profile). "
                "Direct employment or academic relationship.",
    hypothesis=Hypothesis.H1,
    evidence_level=EvidenceLevel.HARD,
    edge_sequence=[
        ("affiliated_with", "out"),  # Seed → Organization
    ],
    node_types=["person", None],
    weight_factors={"affiliated_with": 1.0},
)


# =============================================================================
# H2 Patterns - Indirect Connections (MEDIUM evidence)
# =============================================================================

H2_VIA_COINVENTION = PathPattern(
    pattern_id="H2_via_coinvention",
    name="Via Co-Invention",
    description="Seed co-invented with someone whose patent is assigned to this organization. "
                "Suggests professional network overlap.",
    hypothesis=Hypothesis.H2,
    evidence_level=EvidenceLevel.MEDIUM,
    edge_sequence=[
        ("co_invented", "out"),     # Seed → Co-inventor
        ("has_patent", "out"),      # Co-inventor → Patent (inferred, may need adjustment)
        ("assigned_to", "out"),     # Patent → Organization
    ],
    node_types=["person", "person", "patent", None],
    weight_factors={"co_invented": 0.8, "has_patent": 0.5, "assigned_to": 1.0},
)

H2_CITED_BY_COMPANY = PathPattern(
    pattern_id="H2_cited_by_company",
    name="Cited by Company",
    description="This organization has cited the seed's patent. "
                "Shows the organization is aware of and building on seed's work.",
    hypothesis=Hypothesis.H2,
    evidence_level=EvidenceLevel.MEDIUM,
    edge_sequence=[
        ("has_patent", "out"),      # Seed → Patent
        ("cites_patent", "in"),     # Organization → Patent (reverse: org cites patent)
    ],
    node_types=["person", "patent", None],
    weight_factors={"has_patent": 1.0, "cites_patent": 1.5},  # Citing is valuable signal
)

# =============================================================================
# H3 Patterns - Weak/Distant Connections (SOFT evidence)
# =============================================================================

H3_CITES_COMPANY = PathPattern(
    pattern_id="H3_cites_company",
    name="Cites Company Patent",
    description="Seed's patent cites a patent owned by this organization. "
                "Shows awareness but not necessarily a relationship.",
    hypothesis=Hypothesis.H3,
    evidence_level=EvidenceLevel.SOFT,
    edge_sequence=[
        ("has_patent", "out"),      # Seed → Patent
        ("cites", "out"),           # Patent → Organization (cited assignee)
    ],
    node_types=["person", "patent", None],
    weight_factors={"has_patent": 1.0, "cites": 0.5},  # Citing is weaker signal
)

H3_SHARED_COINVENTOR = PathPattern(
    pattern_id="H3_shared_coinventor",
    name="Shared Co-Inventor",
    description="Seed and this organization share a common co-inventor. "
                "Distant network connection through third party.",
    hypothesis=Hypothesis.H3,
    evidence_level=EvidenceLevel.SOFT,
    edge_sequence=[
        ("co_invented", "out"),     # Seed → Co-inventor
        ("co_invented", "in"),      # Someone → Co-inventor (reverse)
        ("has_patent", "out"),      # Someone → Patent
        ("assigned_to", "out"),     # Patent → Organization
    ],
    node_types=["person", "person", "person", "patent", None],
    weight_factors={"co_invented": 0.5, "has_patent": 0.3, "assigned_to": 0.5},
)

H3_MUTUAL_CITATION = PathPattern(
    pattern_id="H3_mutual_citation",
    name="Mutual Citation",
    description="Both seed and this organization cite the same third-party patent. "
                "Suggests working in similar domain.",
    hypothesis=Hypothesis.H3,
    evidence_level=EvidenceLevel.SOFT,
    edge_sequence=[
        ("has_patent", "out"),      # Seed → Patent
        ("cites", "out"),           # Patent → Third party
        ("cites", "in"),            # Organization → Third party (reverse)
    ],
    node_types=["person", "patent", None, None],
    weight_factors={"has_patent": 1.0, "cites": 0.3},
)


# =============================================================================
# Pattern Registry
# =============================================================================

ALL_PATTERNS: List[PathPattern] = [
    # H1 - Direct
    H1_DIRECT_ASSIGNEE,
    H1_CURRENT_AFFILIATION,
    # H2 - Indirect
    H2_CITED_BY_COMPANY,
    H2_VIA_COINVENTION,
    # H3 - Weak
    H3_CITES_COMPANY,
    H3_SHARED_COINVENTOR,
    H3_MUTUAL_CITATION,
]

PATTERNS_BY_ID: Dict[str, PathPattern] = {p.pattern_id: p for p in ALL_PATTERNS}

PATTERNS_BY_HYPOTHESIS: Dict[Hypothesis, List[PathPattern]] = {
    Hypothesis.H1: [p for p in ALL_PATTERNS if p.hypothesis == Hypothesis.H1],
    Hypothesis.H2: [p for p in ALL_PATTERNS if p.hypothesis == Hypothesis.H2],
    Hypothesis.H3: [p for p in ALL_PATTERNS if p.hypothesis == Hypothesis.H3],
}

PATTERNS_BY_EVIDENCE: Dict[EvidenceLevel, List[PathPattern]] = {
    EvidenceLevel.HARD: [p for p in ALL_PATTERNS if p.evidence_level == EvidenceLevel.HARD],
    EvidenceLevel.MEDIUM: [p for p in ALL_PATTERNS if p.evidence_level == EvidenceLevel.MEDIUM],
    EvidenceLevel.SOFT: [p for p in ALL_PATTERNS if p.evidence_level == EvidenceLevel.SOFT],
}


def get_pattern(pattern_id: str) -> Optional[PathPattern]:
    """Get a pattern by its ID."""
    return PATTERNS_BY_ID.get(pattern_id)


def get_patterns_for_hypothesis(hypothesis: Hypothesis) -> List[PathPattern]:
    """Get all patterns for a given hypothesis level."""
    return PATTERNS_BY_HYPOTHESIS.get(hypothesis, [])


def get_patterns_for_evidence(evidence_level: EvidenceLevel) -> List[PathPattern]:
    """Get all patterns for a given evidence level."""
    return PATTERNS_BY_EVIDENCE.get(evidence_level, [])
