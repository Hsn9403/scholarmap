#!/usr/bin/env python3
"""
Google Patents data retrieval and processing.

This module provides:
- PatentsClient: Main class for patent searches and data enrichment
- Entity utilities: is_corporate, same_person, same_org
- Extractors: Functions to extract data from API responses
- Parsers: Functions to parse HTML pages

Example:
    >>> from src.patents import PatentsClient
    >>> client = PatentsClient()
    >>> data = client.fetch_patents_data("Marie Curie")
"""
from .client import PatentsClient, fetch_patents_data
from .entity import is_corporate, same_person, same_org
from .extractors import (
    extract_citing_patents,
    extract_inventors,
    extract_top_claims,
    extract_cited_by_count,
    extract_assignees,
)

__all__ = [
    # Main client
    "PatentsClient",
    "fetch_patents_data",
    # Entity classification
    "is_corporate",
    "same_person",
    "same_org",
    # Extractors
    "extract_citing_patents",
    "extract_inventors",
    "extract_top_claims",
    "extract_cited_by_count",
    "extract_assignees",
]
