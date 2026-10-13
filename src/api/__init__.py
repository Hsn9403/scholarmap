#!/usr/bin/env python3
"""
API clients for external services (SerpAPI, Semantic Scholar, ClinicalTrials.gov, Crossref).

This module provides:
- SerpAPIClient: Main class for interacting with SerpAPI
- SemanticScholarClient: Client for Semantic Scholar API (complete author lists)
- ClinicalTrialsClient: Client for ClinicalTrials.gov API (industry sponsors)
- CrossrefClient: Client for Crossref API (author name enrichment)
- CassetteManager: Recording/playback of API responses for offline mode
- Backward-compatible functions (get_serpapi_key, serp_search, serp_search_html)

Cassette Modes (set via CASSETTE_MODE env var):
    - "record": Make real API calls AND save responses (default)
    - "offline": Only use cached responses
    - "disabled": No caching

Example:
    >>> from src.api import SerpAPIClient, SemanticScholarClient, ClinicalTrialsClient, CrossrefClient
    >>> client = SerpAPIClient()
    >>> results = client.search_scholar("machine learning")

    >>> # Offline mode
    >>> client = SerpAPIClient(cassette_mode="offline")

    >>> # Semantic Scholar for complete author lists
    >>> s2_client = SemanticScholarClient()
    >>> authors = s2_client.get_paper_authors("Effect of viscosity on microswimmers")

    >>> # ClinicalTrials.gov for industry sponsors
    >>> ct_client = ClinicalTrialsClient()
    >>> sponsors = ct_client.get_industry_sponsors_for_researcher("John Doe")

    >>> # Crossref for author name enrichment
    >>> crossref_client = CrossrefClient(mailto="research@example.com")
    >>> full_name = crossref_client.match_author_by_initial("A. Nedelec", authors)
"""
from .serpapi_client import (
    SerpAPIClient,
    # Backward compatibility
    get_serpapi_key,
    serp_search,
    serp_search_html,
)
from .cassette import CassetteManager, get_cassette_mode
from .semantic_scholar_client import SemanticScholarClient
from .clinicaltrials_client import ClinicalTrialsClient
from .crossref_client import CrossrefClient

__all__ = [
    "SerpAPIClient",
    "SemanticScholarClient",
    "ClinicalTrialsClient",
    "CrossrefClient",
    "CassetteManager",
    "get_cassette_mode",
    "get_serpapi_key",
    "serp_search",
    "serp_search_html",
]
