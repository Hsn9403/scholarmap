#!/usr/bin/env python3
"""
Name matching utilities for Google Scholar profile disambiguation.

This module provides functions to compare and score researcher names
against Google Scholar profile data.
"""
from __future__ import annotations

import re
from typing import Optional

from src.helpers import strip_accents_basic
from src.models import ScholarData


def normalize_text(s: str) -> str:
    """
    Normalize text for comparison.

    Converts to lowercase, removes accents, and strips whitespace.

    Args:
        s: Input string to normalize.

    Returns:
        Normalized string.

    Example:
        >>> normalize_text("José García")
        'jose garcia'
    """
    return strip_accents_basic((s or "").lower().strip())


def name_matches_query(query_name: str, scholar_name: str) -> bool:
    """
    Check if a Google Scholar name matches a query name.

    Matching rules:
    - Both names must have at least 2 parts (first + last)
    - Last name must match exactly (case/accent insensitive)
    - First name must match OR share the same first initial

    Args:
        query_name: The name being searched for.
        scholar_name: The name from Google Scholar profile.

    Returns:
        True if names match according to the rules, False otherwise.

    Examples:
        >>> name_matches_query("John Smith", "John Smith")
        True
        >>> name_matches_query("John Smith", "J. Smith")
        True
        >>> name_matches_query("John Smith", "Jane Smith")
        False
        >>> name_matches_query("John Smith", "John Doe")
        False
    """
    q = normalize_text(query_name)
    s = normalize_text(scholar_name)

    q_parts = [p for p in re.split(r"\s+", q) if p]
    s_parts = [p for p in re.split(r"\s+", s) if p]

    # Need at least first + last name
    if len(q_parts) < 2 or len(s_parts) < 2:
        return False

    q_first, q_last = q_parts[0], q_parts[-1]
    s_first, s_last = s_parts[0], s_parts[-1]

    # Last name must match
    if q_last != s_last:
        return False

    # First name matches exactly
    if s_first == q_first:
        return True

    # First initial matches
    if s_first and q_first and s_first[0] == q_first[0]:
        return True

    return False


def score_candidate(
    filter_text: str,
    candidate: ScholarData,
    google_snippet: str = ""
) -> int:
    """
    Score a Scholar candidate based on filter text match.

    Scoring:
    - +3 points if filter matches affiliation
    - +2 points if filter matches name
    - +1 point if filter matches Google snippet

    Args:
        filter_text: Text to match against (e.g., affiliation, keywords).
        candidate: ScholarData object to score.
        google_snippet: Original Google search snippet.

    Returns:
        Score as integer (higher = better match, 0 = no match).

    Example:
        >>> from src.models import ScholarData
        >>> data = ScholarData(
        ...     author_id="abc",
        ...     name="John Smith",
        ...     affiliation="MIT",
        ...     citations_total=100,
        ...     h_index=10,
        ...     publications_total=50,
        ...     top_publications=[]
        ... )
        >>> score_candidate("MIT", data)
        3
        >>> score_candidate("Harvard", data)
        0
    """
    ft = normalize_text(filter_text)
    if not ft:
        return 0

    score = 0
    hay_aff = normalize_text(candidate.affiliation)
    hay_name = normalize_text(candidate.name)
    hay_snip = normalize_text(google_snippet)

    if ft in hay_aff:
        score += 3
    if ft in hay_name:
        score += 2
    if ft in hay_snip:
        score += 1

    return score
