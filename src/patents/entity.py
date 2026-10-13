#!/usr/bin/env python3
"""
Entity classification and name matching utilities for patent data.

This module provides functions to:
- Determine if an assignee is a corporate entity or a person
- Compare names to check if they refer to the same person/organization
"""
from __future__ import annotations

import re
from typing import Tuple

from src.helpers import strip_accents_basic


# Corporate entity keywords (legal suffixes)
CORP_KEYWORDS = [
    "inc", "corp", "corporation", "gmbh", "ltd", "limited", "llc", "plc",
    "sa", "sas", "sarl", "spa", "ag", "bv", "nv", "oy", "ab", "co", "company",
    "pte", "kg", "kgaa", "kk", "srl", "lp", "holdings", "group"
]

# Organization-related words
ORG_WORDS = [
    "university", "universite", "institut", "institute", "college",
    "center", "centre", "laboratories", "laboratory", "foundation",
    "hospital", "clinic", "school", "academy"
]


def is_corporate(name: str) -> bool:
    """
    Determine if an assignee name is a corporate entity.

    Uses heuristics based on:
    - Legal suffixes (Inc, Ltd, GmbH, etc.)
    - Organization words (University, Institute, etc.)
    - Name structure (acronyms, number of words)

    Args:
        name: Assignee name to classify.

    Returns:
        True if likely a corporate/organization, False if likely a person.

    Example:
        >>> is_corporate("Google Inc")
        True
        >>> is_corporate("John Smith")
        False
        >>> is_corporate("MIT")
        True
    """
    n = re.sub(r"\s+", " ", (name or "").strip())
    if not n:
        return False

    low = n.lower()

    # Check corporate keywords
    for kw in CORP_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return True

    # Check organization words
    for word in ORG_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            return True

    # Two-word names that look like persons (First Last)
    parts = n.split()
    if len(parts) == 2:
        if all(p[0].isupper() and p.isalpha() for p in parts):
            return False

    # Acronyms (all caps, 2+ chars) suggest organization
    if any(p.isupper() and len(p) >= 2 for p in parts):
        return True

    # 3+ tokens more likely organization
    if len(parts) >= 3:
        return True

    return False


def normalize_name(s: str) -> str:
    """
    Normalize a name for comparison.

    Args:
        s: Name to normalize.

    Returns:
        Normalized name (lowercase, no accents, collapsed whitespace).
    """
    s2 = strip_accents_basic(s or "").lower()
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


def split_name_parts(s: str) -> Tuple[str, str]:
    """
    Split a person's name into (first_name, last_name).

    Args:
        s: Full name string.

    Returns:
        Tuple of (first_name, last_name).

    Example:
        >>> split_name_parts("John Smith")
        ('john', 'smith')
    """
    s = normalize_name(s)
    parts = [p for p in s.split() if p]
    if len(parts) < 2:
        return ("", s)
    return (parts[0], parts[-1])


def same_person(a: str, b: str) -> bool:
    """
    Check if two names refer to the same person.

    Rules:
    - Last names must match exactly
    - First names must match OR share the same initial

    Args:
        a: First name to compare.
        b: Second name to compare.

    Returns:
        True if names likely refer to the same person.

    Example:
        >>> same_person("John Smith", "J. Smith")
        True
        >>> same_person("John Smith", "John Doe")
        False
    """
    a_first, a_last = split_name_parts(a)
    b_first, b_last = split_name_parts(b)

    if not a_last or not b_last:
        return False
    if a_last != b_last:
        return False

    if a_first == b_first:
        return True
    if a_first and b_first and a_first[0] == b_first[0]:
        return True

    return False


def normalize_org(s: str) -> str:
    """
    Normalize an organization name for comparison.

    Args:
        s: Organization name.

    Returns:
        Normalized name (no suffixes, no punctuation).
    """
    s = strip_accents_basic(s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    for suffix in CORP_KEYWORDS:
        s = re.sub(rf"\b{suffix}\b", "", s)

    return s.strip()


def same_org(a: str, b: str) -> bool:
    """
    Check if two organization names are the same.

    Args:
        a: First organization name.
        b: Second organization name.

    Returns:
        True if names refer to the same organization.

    Example:
        >>> same_org("Google Inc.", "Google")
        True
    """
    if not a or not b:
        return False
    return normalize_org(a) == normalize_org(b)
