"""
OpenAlex fallback for researchers without a Google Scholar profile.

When Scholar returns no candidates for a researcher, this module fetches
their publications and co-authors from OpenAlex and returns a ScholarData
object in the same format, so the rest of the pipeline works unchanged.

Gaps vs Scholar (set to None/empty):
- h_index: not in OpenAlex author API without extra per-author calls
- abstract: not provided by OpenAlex works API
- scholar_id / scholar_url for co-authors: N/A (no Scholar ID)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from src.models import CoAuthor, ScholarData, ScholarPublication
from src.logger import logger


def build_scholar_data_from_openalex(
    researcher_name: str,
    openalex_client,
    max_publications: int = 50,
    openalex_id: Optional[str] = None,
) -> Optional[ScholarData]:
    """
    Fetch an OpenAlex author and return a ScholarData object.

    Args:
        researcher_name: Full name of the researcher (used for logging / name search).
        openalex_client: An OpenAlexClient instance.
        max_publications: Max publications to retrieve (sorted by citations desc).
        openalex_id: If provided, fetch this specific OpenAlex author directly
                     (bypasses the name search — use when the user has already
                     selected the correct profile from a disambiguation list).

    Returns:
        ScholarData populated from OpenAlex, or None if author not found.
    """
    if openalex_id:
        logger.info(f"[OpenAlex fallback] Fetching by ID: {openalex_id}")
        author = openalex_client.get_author(openalex_id)
    else:
        logger.info(f"[OpenAlex fallback] Searching for: {researcher_name}")
        author = openalex_client.search_author(researcher_name)

    if not author:
        logger.warning(f"[OpenAlex fallback] Author not found in OpenAlex: {researcher_name}")
        return None

    author_id: str = author["id"]  # full URL e.g. "https://openalex.org/A1234567890"
    display_name: str = author.get("display_name", researcher_name)

    logger.info(f"[OpenAlex fallback] Found: {display_name} ({author_id})")

    # --- Publications ---
    works = openalex_client.get_author_works(author_id, max_results=max_publications)
    logger.info(f"[OpenAlex fallback] Retrieved {len(works)} works")

    # --- Affiliation (most frequent institution across all works) ---
    affiliations = openalex_client.extract_affiliations_from_works(works, author_id=author_id)
    affiliation_str = affiliations[0]["display_name"] if affiliations else ""

    # --- Convert works → ScholarPublication + aggregate co-authors ---
    publications: list[ScholarPublication] = []
    # co-author accumulator: openalex_id → {name, count, years, titles}
    coauthor_map: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "count": 0,
        "years": [],
        "titles": [],
        "openalex_id": ""
    })

    for work in works:
        title = (work.get("title") or "").strip() or "(no title)"
        year = str(work["publication_year"]) if work.get("publication_year") else None
        cited_by = work.get("cited_by_count")
        link = work.get("id", "")  # OpenAlex URL for the work

        # Source journal
        primary_loc = work.get("primary_location") or {}
        source_obj = primary_loc.get("source") or {}
        source = source_obj.get("display_name", "") or ""

        # Authors list (display names)
        authorships = work.get("authorships", [])
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]

        publications.append(ScholarPublication(
            title=title,
            link=link,
            cited_by=cited_by,
            authors=authors,
            year=year,
            source=source,
            abstract=None,  # OpenAlex works API does not return abstracts
        ))

        # Accumulate co-authors (skip the seed researcher's own entry)
        short_author_id = author_id.split("/")[-1]
        for authorship in authorships:
            auth = authorship.get("author", {})
            coauth_id = auth.get("id", "")
            if not coauth_id or short_author_id in coauth_id:
                continue  # skip seed

            coauth_name = auth.get("display_name", "").strip()
            if not coauth_name:
                continue

            entry = coauthor_map[coauth_id]
            entry["name"] = coauth_name
            entry["openalex_id"] = coauth_id
            entry["count"] += 1
            if year:
                entry["years"].append(year)
            if len(entry["titles"]) < 3:
                entry["titles"].append(title)

    # --- H-index ---
    # Prefer the authoritative value from OpenAlex summary_stats (returned directly
    # in the author object). Fall back to calculating it from publications only when
    # summary_stats is unavailable (avoids lower-bound estimates from truncated lists).
    openalex_h_index = (author.get("summary_stats") or {}).get("h_index")

    citation_counts = sorted(
        [p.cited_by for p in publications if p.cited_by is not None],
        reverse=True
    )
    calc_h_index = 0
    for rank, citations in enumerate(citation_counts, start=1):
        if citations >= rank:
            calc_h_index = rank
        else:
            break  # sorted desc — no need to continue

    h_index = openalex_h_index if openalex_h_index is not None else calc_h_index

    logger.info(
        f"[OpenAlex fallback] H-index: {h_index} "
        f"(source: {'OpenAlex summary_stats' if openalex_h_index is not None else 'calculated from publications'})"
    )

    # Sort co-authors by shared publication count desc
    coauthors: list[CoAuthor] = []
    for entry in sorted(coauthor_map.values(), key=lambda x: x["count"], reverse=True):
        years_sorted = sorted(set(entry["years"]), reverse=True)
        coauthors.append(CoAuthor(
            name=entry["name"],
            shared_pubs_count=entry["count"],
            last_shared_year=years_sorted[0] if years_sorted else None,
            example_titles=entry["titles"] or None,
            scholar_id=None,       # not available from OpenAlex
            h_index=None,          # would require a separate per-author call
            scholar_url=None,
            openalex_id=entry["openalex_id"] or None,
        ))

    logger.info(
        f"[OpenAlex fallback] Built ScholarData: {len(publications)} pubs, "
        f"{len(coauthors)} co-authors, affiliation={affiliation_str!r}"
    )

    return ScholarData(
        author_id=author_id,          # OpenAlex URL as author_id
        name=display_name,
        affiliation=affiliation_str,
        citations_total=author.get("cited_by_count"),
        h_index=h_index if h_index else None,
        publications_total=author.get("works_count"),
        top_publications=publications,
        coauthors=coauthors,
    )
