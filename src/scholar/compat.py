#!/usr/bin/env python3
"""
Backward compatibility functions for legacy code.

These functions provide the original API signatures for code that
hasn't migrated to the new class-based ScholarClient interface.

Note:
    These functions are deprecated. New code should use ScholarClient directly.

Example (deprecated):
    >>> data = fetch_scholar_author_data("xJaxiEEAAAAJ", api_key)

Example (recommended):
    >>> from src.scholar import ScholarClient
    >>> client = ScholarClient(api_key=api_key)
    >>> data = client.fetch_author_data("xJaxiEEAAAAJ")
"""
from __future__ import annotations

from typing import List, Optional

from src.models import ScholarCandidate, ScholarData


def find_scholar_candidates_via_google(
    name: str,
    api_key: str,
    hl: str = "fr",
    num: int = 10
) -> List[ScholarCandidate]:
    """
    Find Google Scholar candidates via Google search.

    .. deprecated::
        Use :meth:`ScholarClient.find_candidates` instead.

    Args:
        name: Researcher name to search for.
        api_key: SerpAPI key.
        hl: Language code (default: "fr").
        num: Maximum number of results (default: 10).

    Returns:
        List of ScholarCandidate objects.

    Example:
        >>> candidates = find_scholar_candidates_via_google("John Smith", api_key)
    """
    # Import here to avoid circular imports
    from .client import ScholarClient

    client = ScholarClient(api_key=api_key, hl=hl)
    return client.find_candidates(name, num=num)


def fetch_scholar_author_data(
    author_id: str,
    api_key: str,
    hl: str = "fr"
) -> ScholarData:
    """
    Fetch Google Scholar author data.

    .. deprecated::
        Use :meth:`ScholarClient.fetch_author_data` instead.

    Args:
        author_id: Google Scholar author ID.
        api_key: SerpAPI key.
        hl: Language code (default: "fr").

    Returns:
        ScholarData object with author information.

    Example:
        >>> data = fetch_scholar_author_data("xJaxiEEAAAAJ", api_key)
        >>> print(f"H-index: {data.h_index}")
    """
    from .client import ScholarClient

    client = ScholarClient(api_key=api_key, hl=hl)
    return client.fetch_author_data(author_id)


def resolve_author_id_with_disambiguation(
    researcher_name: str,
    api_key: str,
    hl: str = "fr",
    max_candidates: int = 8
) -> Optional[str]:
    """
    Resolve researcher name to author ID with disambiguation.

    .. deprecated::
        Use :meth:`ScholarClient.resolve_author_id` instead.

    Args:
        researcher_name: Name of the researcher to search.
        api_key: SerpAPI key.
        hl: Language code (default: "fr").
        max_candidates: Maximum candidates to consider (default: 8).

    Returns:
        The resolved author_id, None if not found, or "__QUIT__" if cancelled.

    Example:
        >>> author_id = resolve_author_id_with_disambiguation("John Smith", api_key)
    """
    from .client import ScholarClient

    client = ScholarClient(api_key=api_key, hl=hl)
    return client.resolve_author_id(researcher_name, max_candidates=max_candidates)
