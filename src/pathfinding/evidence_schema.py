"""
Evidence schema for corporate connections.

This module defines the structure for verifiable evidence linking
co-authors to corporate entities.

EVIDENCE LEVELS:
- Level A (irrefutable): Direct proof (patent inventors list, publication affiliation)
- Level B (strong): Repeated affiliations across multiple publications
- Level C (signal): Co-author affiliation (indirect signal)
- Level REJECTED: Failed verification
- Level UNRESOLVED: High ambiguity, needs user input
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Literal
from enum import Enum


class EvidenceLevel(str, Enum):
    """Evidence quality levels."""
    LEVEL_A = "LEVEL_A"  # Irrefutable
    LEVEL_B = "LEVEL_B"  # Strong
    LEVEL_C = "LEVEL_C"  # Signal (indirect)
    REJECTED = "REJECTED"  # Failed verification
    UNRESOLVED = "UNRESOLVED"  # High ambiguity


class EvidenceType(str, Enum):
    """Types of evidence."""
    PATENT_INVENTOR = "patent_inventor"  # Person is inventor on patent
    PUBLICATION_AFFILIATION = "publication_affiliation"  # Person affiliated with corporate in publication
    REPEATED_AFFILIATION = "repeated_affiliation"  # Corporate affiliation repeated across N pubs
    COAUTHOR_AFFILIATION = "coauthor_affiliation"  # Co-author is affiliated (indirect)
    CLINICAL_TRIAL = "clinical_trial"  # Person is PI on clinical trial sponsored by corporate


@dataclass
class Evidence:
    """
    Structured evidence for a corporate connection.

    This is the core data structure for ALL corporate links.
    Every link MUST have evidence at Level A or B to be displayed.
    """
    # Claim
    claim: str  # "Co-author J. Weller affiliated with Orange SA"
    verdict: EvidenceLevel

    # Evidence details
    evidence_type: EvidenceType
    source: str  # "google_patents", "openalex", "ror"
    source_url: Optional[str]  # Direct link to proof

    # Verification details
    field_path: Optional[str]  # "authorships[2].institutions[0]" or "inventors[3]"
    proof_snippet: Optional[str]  # Short excerpt showing the proof

    # Metadata
    confidence: float  # 0.0 to 1.0
    notes: str  # Why accepted/rejected

    # Raw data (for debugging)
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        """Create from dict."""
        return cls(**data)


@dataclass
class CorporateConnection:
    """
    A verified connection: Researcher → Co-author → Corporate.
    """
    researcher: str
    coauthor: str
    coauthor_openalex_id: Optional[str]
    corporate: str
    corporate_ror_id: Optional[str]

    # Multiple pieces of evidence (may have both patent + affiliation)
    evidence_list: List[Evidence]

    # Overall confidence (max of all evidence)
    overall_confidence: float
    best_evidence_level: EvidenceLevel

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "researcher": self.researcher,
            "coauthor": self.coauthor,
            "coauthor_openalex_id": self.coauthor_openalex_id,
            "corporate": self.corporate,
            "corporate_ror_id": self.corporate_ror_id,
            "evidence": [e.to_dict() for e in self.evidence_list],
            "overall_confidence": self.overall_confidence,
            "best_evidence_level": self.best_evidence_level.value
        }

    def is_displayable(self) -> bool:
        """
        Check if this connection should be displayed.

        Only display if at least one evidence is Level A or B.
        """
        return any(
            e.verdict in (EvidenceLevel.LEVEL_A, EvidenceLevel.LEVEL_B)
            for e in self.evidence_list
        )


def create_patent_evidence(
    patent_id: str,
    patent_title: str,
    patent_url: str,
    assignee: str,
    inventors_list: List[str],
    coauthor_name: str,
    inventor_confirmed: bool,
    matching_inventor: Optional[str] = None
) -> Evidence:
    """
    Create evidence for a patent-based corporate connection.

    Args:
        patent_id: Patent ID.
        patent_title: Patent title.
        patent_url: URL to patent page.
        assignee: Corporate assignee.
        inventors_list: List of ALL inventors on the patent.
        coauthor_name: Name being searched.
        inventor_confirmed: Whether the name was confirmed in inventors list.
        matching_inventor: Exact name as it appears in inventors list.

    Returns:
        Evidence object with Level A (if confirmed) or REJECTED.
    """
    if inventor_confirmed and matching_inventor:
        return Evidence(
            claim=f"{coauthor_name} is inventor on patent assigned to {assignee}",
            verdict=EvidenceLevel.LEVEL_A,
            evidence_type=EvidenceType.PATENT_INVENTOR,
            source="google_patents",
            source_url=patent_url,
            field_path=f"inventors[{inventors_list.index(matching_inventor)}]",
            proof_snippet=f"Inventor: {matching_inventor}",
            confidence=0.95,
            notes=f"Name '{coauthor_name}' confirmed as inventor '{matching_inventor}' on patent",
            raw_data={
                "patent_id": patent_id,
                "patent_title": patent_title,
                "assignee": assignee,
                "all_inventors": inventors_list,
                "matching_inventor": matching_inventor
            }
        )
    else:
        return Evidence(
            claim=f"{coauthor_name} is inventor on patent assigned to {assignee}",
            verdict=EvidenceLevel.REJECTED,
            evidence_type=EvidenceType.PATENT_INVENTOR,
            source="google_patents",
            source_url=patent_url,
            field_path=None,
            proof_snippet=None,
            confidence=0.0,
            notes=f"Name '{coauthor_name}' NOT found in inventors list: {', '.join(inventors_list[:5])}...",
            raw_data={
                "patent_id": patent_id,
                "patent_title": patent_title,
                "assignee": assignee,
                "all_inventors": inventors_list
            }
        )


def create_publication_affiliation_evidence(
    work_id: str,
    work_title: str,
    work_url: str,
    author_name: str,
    institution_name: str,
    institution_ror_id: Optional[str],
    authorship_index: int,
    institution_index: int
) -> Evidence:
    """
    Create evidence for a publication affiliation.

    Args:
        work_id: OpenAlex work ID.
        work_title: Publication title.
        work_url: URL to work page.
        author_name: Author name.
        institution_name: Corporate institution name.
        institution_ror_id: ROR ID if available.
        authorship_index: Index in authorships array.
        institution_index: Index in institutions array.

    Returns:
        Evidence object with Level A.
    """
    return Evidence(
        claim=f"{author_name} affiliated with {institution_name} in publication",
        verdict=EvidenceLevel.LEVEL_A,
        evidence_type=EvidenceType.PUBLICATION_AFFILIATION,
        source="openalex",
        source_url=work_url,
        field_path=f"authorships[{authorship_index}].institutions[{institution_index}]",
        proof_snippet=f"Institution: {institution_name}" + (f" (ROR: {institution_ror_id})" if institution_ror_id else ""),
        confidence=0.95,
        notes=f"Affiliation explicitly listed in OpenAlex publication metadata",
        raw_data={
            "work_id": work_id,
            "work_title": work_title,
            "author_name": author_name,
            "institution_name": institution_name,
            "institution_ror_id": institution_ror_id
        }
    )
