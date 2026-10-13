#!/usr/bin/env python3
"""Common helper functions used across the project."""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional


def strip_accents_basic(s: str) -> str:
    """Remove accents from a string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def safe_int(x: Any) -> Optional[int]:
    """Safely convert any value to int, returning None on failure."""
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


# Backward compatibility alias
_safe_int = safe_int


def slug(s: str) -> str:
    """Convert a string to a URL-safe slug."""
    s = strip_accents_basic(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def norm(s: str) -> str:
    """Normalize whitespace in a string."""
    return re.sub(r"\s+", " ", (s or "").strip())


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_yyyy_mm_dd(s: Optional[str]) -> Optional[datetime]:
    """Parse a date string in YYYY-MM-DD format."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not _DATE_RE.match(s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def normalize_for_match(s: str) -> str:
    """
    Normalize to compare names (for person matching).
    - lowercase
    - strip accents
    - collapse spaces
    """
    s2 = strip_accents_basic(s or "").lower()
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


def name_variants(name: str) -> list[str]:
    """
    Generate name variants by stripping middle names/initials.

    For a name with 3+ space-separated parts, also produces a "First Last"
    variant (without any middle words). Names with ≤2 parts are returned as-is.

    Used so that a search for "George R. Saade" that returns no results
    can be retried automatically as "George Saade".

    Args:
        name: Full person name string.

    Returns:
        List of unique name variants — always starts with the original name.
        Has exactly 1 entry for 2-word names, 2 entries for 3+-word names.

    Examples:
        >>> name_variants("George R. Saade")
        ["George R. Saade", "George Saade"]
        >>> name_variants("Andre Imbert")
        ["Andre Imbert"]
        >>> name_variants("John M. K. Smith")
        ["John M. K. Smith", "John Smith"]
    """
    name = (name or "").strip()
    if not name:
        return [name]

    parts = name.split()
    if len(parts) <= 2:
        return [name]

    # Strip all middle parts → "First Last"
    without_middle = f"{parts[0]} {parts[-1]}"
    return [name, without_middle]


def dedup_preserve_order(xs: list) -> list:
    """Remove duplicates from list while preserving order."""
    seen = set()
    out = []
    for x in xs:
        x = (x or "").strip() if isinstance(x, str) else x
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out
