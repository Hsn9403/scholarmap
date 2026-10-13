#!/usr/bin/env python3
"""
Data extraction utilities for patent API responses.

This module provides functions to extract structured data from
SerpAPI JSON responses (inventors, assignees, citations, claims).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.models import CitingPatent, CitedPatent
from src.helpers import safe_int, norm, dedup_preserve_order


def extract_cited_patents(details: Dict[str, Any]) -> List[CitedPatent]:
    """
    Extract list of patents cited by this patent (backward citations).

    Args:
        details: Patent details dictionary from API.

    Returns:
        List of CitedPatent objects.
    """
    out: List[CitedPatent] = []
    block = (
        details.get("patent_citations") or
        details.get("citations") or
        details.get("references") or
        []
    )

    if not isinstance(block, list):
        # Handle nested structures like {"original": [...]}
        if isinstance(block, dict):
            nested = (
                block.get("original") or
                block.get("family_to_family") or
                block.get("citations") or
                []
            )
            if isinstance(nested, list):
                block = nested
            else:
                return out
        else:
            return out

    for entry in block:
        if not isinstance(entry, dict):
            continue

        pub = (
            entry.get("publication_number") or
            entry.get("publication") or
            entry.get("patent_id") or ""
        ).strip()

        link = (entry.get("link") or "").strip()

        # Check multiple possible field names for assignee
        assignee = (
            entry.get("assignee") or
            entry.get("assignee_original") or
            entry.get("owner") or
            entry.get("applicant")
        )

        pub_date = entry.get("publication_date") or entry.get("published")
        filing_date = entry.get("filing_date") or entry.get("filed")
        priority_date = entry.get("priority_date") or entry.get("priority")

        if pub or link:
            out.append(CitedPatent(
                publication_number=pub,
                link=link,
                assignee=assignee if isinstance(assignee, str) else None,
                publication_date=pub_date if isinstance(pub_date, str) else None,
                filing_date=filing_date if isinstance(filing_date, str) else None,
                priority_date=priority_date if isinstance(priority_date, str) else None,
            ))

    return out


def extract_citing_patents(details: Dict[str, Any]) -> List[CitingPatent]:
    """
    Extract list of patents that cite this patent.

    Args:
        details: Patent details dictionary from API.

    Returns:
        List of CitingPatent objects.
    """
    out: List[CitingPatent] = []
    block = details.get("cited_by") or details.get("forward_citations") or []

    if not isinstance(block, list):
        return out

    for entry in block:
        if not isinstance(entry, dict):
            continue

        pub = (
            entry.get("publication_number") or
            entry.get("publication") or
            entry.get("patent_id") or ""
        ).strip()

        link = (entry.get("link") or "").strip()
        assignee = entry.get("assignee") or entry.get("owner") or entry.get("applicant")

        pub_date = entry.get("publication_date") or entry.get("published")
        filing_date = entry.get("filing_date") or entry.get("filed")
        priority_date = entry.get("priority_date") or entry.get("priority")

        if pub or link:
            out.append(CitingPatent(
                publication_number=pub,
                link=link,
                assignee=assignee if isinstance(assignee, str) else None,
                publication_date=pub_date if isinstance(pub_date, str) else None,
                filing_date=filing_date if isinstance(filing_date, str) else None,
                priority_date=priority_date if isinstance(priority_date, str) else None,
            ))

    return out


def extract_inventors(details: Dict[str, Any]) -> List[str]:
    """
    Extract inventor names from patent details.

    Handles various formats:
    - String: "John Smith, Jane Doe"
    - List of strings: ["John Smith", "Jane Doe"]
    - List of dicts: [{"name": "John Smith"}, ...]

    Args:
        details: Patent details dictionary.

    Returns:
        List of inventor names (deduplicated).
    """
    out: List[str] = []
    inv = details.get("inventors") or details.get("inventor")

    if isinstance(inv, str) and inv.strip():
        out.extend(_split_names(inv))

    elif isinstance(inv, list):
        for item in inv:
            if isinstance(item, str) and item.strip():
                out.append(norm(item))
            elif isinstance(item, dict):
                nm = item.get("name") or item.get("inventor") or item.get("full_name")
                if isinstance(nm, str) and nm.strip():
                    out.append(norm(nm))

    elif isinstance(inv, dict):
        nm = inv.get("name")
        if isinstance(nm, str) and nm.strip():
            out.append(norm(nm))
        elif isinstance(nm, list):
            for x in nm:
                if isinstance(x, str) and x.strip():
                    out.append(norm(x))

    # Deep scan fallback
    if not out:
        out = list(_iter_inventor_names(details))

    return dedup_preserve_order(out)


def extract_top_claims(details: Dict[str, Any], n: int = 3) -> List[str]:
    """
    Extract the first N claims from patent details.

    Args:
        details: Patent details dictionary.
        n: Number of claims to extract (default: 3).

    Returns:
        List of claim strings.
    """
    claims = details.get("claims")
    if not isinstance(claims, list):
        return []

    out = []
    for c in claims[:n]:
        if c is not None:
            s = str(c).strip()
            if s:
                out.append(s)
    return out


def extract_cited_by_count(details: Dict[str, Any]) -> Optional[int]:
    """
    Extract the citation count for a patent.

    Args:
        details: Patent details dictionary.

    Returns:
        Number of citations, or None if not available.
    """
    # Try patent_citations key
    v = details.get("patent_citations")
    if isinstance(v, dict):
        return safe_int(v.get("total") or v.get("value"))
    if isinstance(v, (int, str)):
        return safe_int(v)

    # Try citations key
    v2 = details.get("citations")
    if isinstance(v2, dict):
        return safe_int(v2.get("total") or v2.get("value"))
    if isinstance(v2, (int, str)):
        return safe_int(v2)

    return None


def extract_assignees(details: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Extract cited and citing assignees from patent details.

    Args:
        details: Patent details dictionary.

    Returns:
        Tuple of (cited_assignees, citing_assignees).
    """
    cited_block = (
        details.get("patent_citations") or
        details.get("citations") or
        details.get("references") or
        []
    )
    citing_block = (
        details.get("cited_by") or
        details.get("forward_citations") or
        []
    )

    cited = _collect_assignees_from_block(cited_block)
    citing = _collect_assignees_from_block(citing_block)

    return dedup_preserve_order(cited), dedup_preserve_order(citing)


def extract_current_assignee(details: Dict[str, Any]) -> str:
    """
    Extract current assignee from patent details.

    Args:
        details: Patent details dictionary.

    Returns:
        Assignee name or empty string.
    """
    return (
        details.get("assignee") or
        details.get("current_assignee") or
        details.get("owner") or
        ""
    )


def extract_dates(details: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Extract patent dates (publication, filing, priority).

    Args:
        details: Patent details dictionary.

    Returns:
        Dict with keys: publication_date, filing_date, priority_date.
    """
    return {
        "publication_date": details.get("publication_date") or details.get("published"),
        "filing_date": details.get("filing_date") or details.get("filed"),
        "priority_date": details.get("priority_date") or details.get("priority"),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _split_names(s: str) -> List[str]:
    """Split a string of names by common delimiters."""
    pattern = re.compile(
        r"\s*;\s*|\s*,\s*|\s+\band\b\s+|\s+\bet\b\s+",
        flags=re.IGNORECASE
    )
    parts = pattern.split(s or "")
    return [p for p in (norm(p) for p in parts) if p]


def _iter_inventor_names(obj: Any) -> Iterator[str]:
    """Recursively iterate through object finding inventor names."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in ("inventor", "inventors"):
                if isinstance(v, str) and v.strip():
                    yield norm(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.strip():
                            yield norm(item)
                        elif isinstance(item, dict):
                            nm = item.get("name")
                            if isinstance(nm, str) and nm.strip():
                                yield norm(nm)
            yield from _iter_inventor_names(v)

    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_inventor_names(item)


def _collect_assignees_from_block(block: Any) -> List[str]:
    """Collect assignee names from a citations block.

    Handles various API response formats:
    - List of dicts: [{"assignee": "Foo"}, ...]
    - Dict with nested list: {"original": [{"assignee_original": "Foo"}, ...]}
    - Dict with family_to_family: {"family_to_family": [{"assignee_original": "Foo"}, ...]}
    """
    out: List[str] = []

    # Handle nested structures like {"original": [...]} or {"family_to_family": [...]}
    if isinstance(block, dict):
        # Try common nested keys
        nested = (
            block.get("original") or
            block.get("family_to_family") or
            block.get("citations") or
            []
        )
        if isinstance(nested, list):
            block = nested
        else:
            block = [block] if block else []
    elif not isinstance(block, list):
        block = [block] if block else []

    for entry in block:
        if not isinstance(entry, dict):
            continue

        # Check multiple possible field names for assignee
        assignee = (
            entry.get("assignee") or
            entry.get("assignee_original") or  # SerpAPI format
            entry.get("assignees") or
            entry.get("current_assignee") or
            entry.get("owner") or
            entry.get("applicant")
        )

        if isinstance(assignee, str) and assignee.strip():
            out.append(norm(assignee))
        elif isinstance(assignee, list):
            for x in assignee:
                if isinstance(x, str) and x.strip():
                    out.append(norm(x))
                elif isinstance(x, dict):
                    nm = x.get("name")
                    if isinstance(nm, str) and nm.strip():
                        out.append(norm(nm))

    return out
