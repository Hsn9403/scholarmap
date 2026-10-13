#!/usr/bin/env python3
"""
Data models for the Scholarmap project.

This module defines dataclasses for representing:
- Google Scholar data (candidates, publications, author data)
- Patent data (patent items, citing patents)

All models are immutable dataclasses designed for:
- Type-safe data transfer between components
- JSON serialization
- Clear documentation of data structures

Example:
    >>> from src.models import ScholarData, PatentItem
    >>> scholar = ScholarData(
    ...     author_id="abc123",
    ...     name="John Doe",
    ...     affiliation="MIT",
    ...     citations_total=500,
    ...     h_index=15,
    ...     publications_total=42,
    ...     top_publications=[]
    ... )
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CitingPatent:
    """
    A patent that cites another patent.

    Attributes:
        publication_number: Patent publication number (e.g., "US10123456B2").
        link: URL to the patent page.
        assignee: Company or entity holding the patent.
        publication_date: Date the patent was published.
        filing_date: Date the patent application was filed.
        priority_date: Earliest priority date claimed.
    """
    publication_number: str
    link: str
    assignee: Optional[str] = None
    publication_date: Optional[str] = None
    filing_date: Optional[str] = None
    priority_date: Optional[str] = None


@dataclass
class CitedPatent:
    """
    A patent that is cited by another patent (backward citation).

    Attributes:
        publication_number: Patent publication number (e.g., "US10123456B2").
        link: URL to the patent page.
        assignee: Company or entity holding the patent (may be person name initially).
        publication_date: Date the patent was published.
        filing_date: Date the patent application was filed.
        priority_date: Earliest priority date claimed.
    """
    publication_number: str
    link: str
    assignee: Optional[str] = None
    publication_date: Optional[str] = None
    filing_date: Optional[str] = None
    priority_date: Optional[str] = None


@dataclass
class ScholarCandidate:
    """
    A Google Scholar profile candidate from search results.

    Attributes:
        author_id: Google Scholar author ID (e.g., "xJaxiEEAAAAJ").
        title: Title from search result (usually author name + affiliation).
        link: URL to the Scholar profile page.
        snippet: Search result snippet text.
    """
    author_id: str
    title: str
    link: str
    snippet: str


@dataclass
class ScholarPublication:
    """
    A publication from a Google Scholar profile.

    Attributes:
        title: Publication title.
        link: URL to the publication page.
        cited_by: Number of citations (None if unknown).
        authors: List of author names (including the profile owner).
        year: Publication year.
        source: Journal/publication source (e.g., "Small 17 (26), 2007403, 2021").
        abstract: Publication abstract/summary.
    """
    title: str
    link: str
    cited_by: Optional[int]
    authors: Optional[List[str]] = None
    year: Optional[str] = None
    source: Optional[str] = None
    abstract: Optional[str] = None


@dataclass
class CoAuthor:
    """
    A co-author aggregated from Google Scholar publications.

    Represents a person who has co-authored publications with the profile owner.
    Used to build CO_AUTHOR_WITH edges in the graph.

    Attributes:
        name: Co-author name (may be abbreviated, e.g., "J Simmchen").
        shared_pubs_count: Number of shared publications.
        last_shared_year: Most recent year of collaboration.
        example_titles: Sample publication titles (up to 3).
        scholar_id: Google Scholar ID if available (for profile link).
        h_index: H-index if available from database.
        scholar_url: Full Scholar profile URL if available.
    """
    name: str
    shared_pubs_count: int
    last_shared_year: Optional[str] = None
    example_titles: Optional[List[str]] = None
    scholar_id: Optional[str] = None
    h_index: Optional[int] = None
    scholar_url: Optional[str] = None
    openalex_id: Optional[str] = None  # OpenAlex author ID for disambiguation


@dataclass
class ScholarData:
    """
    Complete Google Scholar author profile data.

    Attributes:
        author_id: Google Scholar author ID.
        name: Author's display name.
        affiliation: Author's affiliation (university, company).
        citations_total: Total citation count.
        h_index: H-index value.
        publications_total: Total number of publications.
        top_publications: List of top publications.
        coauthors: Aggregated list of co-authors with collaboration stats.
    """
    author_id: str
    name: str
    affiliation: str
    citations_total: Optional[int]
    h_index: Optional[int]
    publications_total: Optional[Any]
    top_publications: List[ScholarPublication]
    coauthors: Optional[List[CoAuthor]] = None


@dataclass
class PatentItem:
    """
    A patent with its metadata and network signals.

    Attributes:
        title: Patent title.
        link: URL to the patent page.
        patent_id: Patent publication number.
        publication_date: Date the patent was published.
        filing_date: Date the application was filed.
        priority_date: Earliest priority date.
        current_assignee: Current patent holder.
        claims_top3: Top 3 claims from the patent.
        cited_by: Number of patents citing this one.
        cited_assignees: Assignees of patents this one cites.
        citing_assignees: Assignees of patents citing this one.
        citing_patents: Detailed list of citing patents.
        co_inventors: Other inventors on this patent.
    """
    title: str
    link: str
    patent_id: Optional[str] = None

    # patent metadata
    publication_date: Optional[str] = None
    filing_date: Optional[str] = None
    priority_date: Optional[str] = None
    current_assignee: Optional[str] = None

    # content / signals
    claims_top3: Optional[List[str]] = None
    cited_by: Optional[int] = None

    # network signals
    cited_assignees: Optional[List[str]] = None      # assignees in "Patent Citations" (legacy)
    citing_assignees: Optional[List[str]] = None     # assignees in "Cited By" (legacy)
    cited_patents: Optional[List[Dict[str, Any]]] = None  # detailed cited patents (backward citations)
    citing_patents: Optional[List[Dict[str, Any]]] = None  # detailed citing patents (forward citations)
    co_inventors: Optional[List[str]] = None         # other inventors (excludes main searched inventor)
    inventors: Optional[List[str]] = None            # ALL inventors (complete list from patent)


@dataclass
class PatentsData:
    """
    Collection of patents for a researcher.

    Attributes:
        patents_total: Total number of patents found.
        top_patents: List of top patent items with details.
    """
    patents_total: Optional[Any]
    top_patents: List[PatentItem]
