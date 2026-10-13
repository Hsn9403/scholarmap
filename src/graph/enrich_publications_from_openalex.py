"""
Enrich publication author lists using OpenAlex.

For each publication, searches OpenAlex by title and replaces abbreviated
author names (e.g. "S Patskovsky") with full names from OpenAlex authorships.
Also fills in missing authors from truncated Scholar lists.
"""
import unicodedata
import re
from typing import TYPE_CHECKING

from src.logger import logger

if TYPE_CHECKING:
    from src.models import ScholarData
    from src.pathfinding.openalex_client import OpenAlexClient


def _normalize(text: str) -> str:
    """Lowercase, strip accents, remove non-alphanumeric."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _initial_matches(abbreviated: str, full_name: str) -> bool:
    """
    Check if abbreviated name (e.g. "S Patskovsky") matches full name
    (e.g. "Sergiy Patskovsky").

    Rules:
    - Last names must match exactly (normalized)
    - First part of abbreviated must be a single letter matching the first
      letter of the full first name
    """
    a_parts = abbreviated.strip().split()
    f_parts = full_name.strip().split()

    if len(a_parts) < 2 or len(f_parts) < 2:
        return False

    # Last name comparison (last token)
    a_last = _normalize(a_parts[-1])
    f_last = _normalize(f_parts[-1])
    if a_last != f_last:
        return False

    # First part: check it's a single letter or single letter + dot
    a_first = a_parts[0].replace(".", "").strip()
    if len(a_first) != 1:
        return False

    f_first = _normalize(f_parts[0])
    return f_first.startswith(a_first.lower())


def resolve_author_names_via_openalex(
    scholar_data: "ScholarData",
    openalex_client: "OpenAlexClient",
    max_publications: int = 30,
) -> int:
    """
    Enrich publication author lists using OpenAlex.

    For each publication in scholar_data.top_publications (up to max_publications),
    searches OpenAlex by title and:
    1. Replaces abbreviated names with full names (e.g. "S Patskovsky" → "Sergiy Patskovsky")
    2. Adds missing authors from truncated Scholar lists

    Modifies scholar_data.top_publications in-place.

    Args:
        scholar_data: Scholar data object with top_publications.
        openalex_client: OpenAlex client instance.
        max_publications: Maximum publications to query (each costs 1 cached API call).

    Returns:
        Number of author names resolved/added.
    """
    if not scholar_data or not scholar_data.top_publications:
        return 0

    total_resolved = 0
    pubs = scholar_data.top_publications[:max_publications]

    # Filter only publications that need enrichment (have abbreviated names)
    def _has_abbreviated(pub) -> bool:
        return bool(pub.authors and any(
            len(parts) >= 2 and len(parts[0].replace(".", "").strip()) == 1
            for a in pub.authors
            for parts in [a.strip().split()]
        ))

    pubs_to_enrich = [p for p in pubs if p.title and p.title.strip() and _has_abbreviated(p)]

    if not pubs_to_enrich:
        logger.info("✅ OpenAlex enrichment: no abbreviated names to resolve")
        return 0

    # Fetch all OpenAlex results in parallel (each call is independent)
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    def _fetch(pub):
        return pub, openalex_client.search_work_by_title(pub.title)

    works: dict = {}  # pub → work result
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch, p): p for p in pubs_to_enrich}
        for fut in _as_completed(futures):
            try:
                pub, work = fut.result()
                works[id(pub)] = (pub, work)
            except Exception as e:
                logger.debug(f"OpenAlex fetch error: {e}")

    # Apply results sequentially (writes to pub.authors, no shared state issues)
    for _, (pub, work) in works.items():
        if not work:
            continue

        openalex_authors = [
            authorship.get("author", {}).get("display_name", "").strip()
            for authorship in work.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ]
        if not openalex_authors:
            continue

        # Verify it's the same paper
        oa_title = _normalize(work.get("title", ""))
        pub_title = _normalize(pub.title)
        if pub_title and oa_title:
            overlap = sum(1 for c in pub_title if c in oa_title) / max(len(pub_title), 1)
            if overlap < 0.7:
                logger.debug(f"OpenAlex title mismatch for '{pub.title[:50]}' (overlap={overlap:.2f}), skipping")
                continue

        if pub.authors is None:
            pub.authors = []

        new_authors = list(pub.authors)
        resolved_in_pub = 0
        for i, author in enumerate(new_authors):
            a_parts = author.strip().split()
            if len(a_parts) < 2:
                continue
            a_first = a_parts[0].replace(".", "").strip()
            if len(a_first) != 1:
                continue
            matches = [oa for oa in openalex_authors if _initial_matches(author, oa)]
            if len(matches) == 1:
                logger.info(f"  OpenAlex resolved: '{author}' → '{matches[0]}' (in '{pub.title[:50]}')")
                new_authors[i] = matches[0]
                resolved_in_pub += 1
            elif len(matches) > 1:
                logger.debug(f"  Ambiguous OpenAlex match for '{author}': {matches} — skipping")

        pub.authors = new_authors
        total_resolved += resolved_in_pub

    logger.info(
        f"✅ OpenAlex enrichment: resolved/added {total_resolved} author names "
        f"across {len(pubs)} publications"
    )
    return total_resolved
