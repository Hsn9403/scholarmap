#!/usr/bin/env python3
"""
Google Scholar data retrieval and processing.

This module provides:
- ScholarClient: Main class for Google Scholar interactions
- ScholarResolver: Disambiguation handler
- Matching utilities for name comparison
- Backward-compatible functions for legacy code

Example:
    >>> from src.scholar import ScholarClient
    >>> client = ScholarClient()
    >>> data = client.fetch_author_data("xJaxiEEAAAAJ")
    >>> print(f"H-index: {data.h_index}")
"""
from .client import ScholarClient
from .resolver import ScholarResolver
from .matching import name_matches_query, score_candidate, normalize_text

# Backward compatibility
from .compat import (
    find_scholar_candidates_via_google,
    fetch_scholar_author_data,
    resolve_author_id_with_disambiguation,
)

__all__ = [
    # Main classes
    "ScholarClient",
    "ScholarResolver",
    # Matching utilities
    "name_matches_query",
    "score_candidate",
    "normalize_text",
    # Backward compatibility
    "find_scholar_candidates_via_google",
    "fetch_scholar_author_data",
    "resolve_author_id_with_disambiguation",
]
