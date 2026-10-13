"""
Name resolution for ambiguous co-author names.

Problem: Google Scholar lists "D Lombardi" but there are multiple people with this name.
Solution: Use OpenAlex to find the EXACT person who co-authored with the main researcher.

Strategy:
1. Get main researcher's publications from OpenAlex
2. Find publications where co-author appears (match on last name)
3. Extract co-author's full name + OpenAlex ID from those publications
4. Return resolved name for patent search
"""
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from src.logger import logger
from src.pathfinding.openalex_client import OpenAlexClient


@dataclass
class ResolvedName:
    """Resolved co-author identity."""
    original_name: str  # "D Lombardi"
    resolved_name: str  # "Damiano Lombardi"
    openalex_id: str  # "https://openalex.org/A..."
    confidence: float  # 0.0 to 1.0
    shared_publications: int  # Number of publications found together
    evidence: List[Dict[str, Any]]  # Sample publications as proof


def resolve_coauthor_full_name(
    main_researcher_name: str,
    coauthor_partial_name: str,
    openalex_client: Optional[OpenAlexClient] = None,
    max_publications: int = 50,
    min_shared_publications: int = 2
) -> List[ResolvedName]:
    """
    Resolve a co-author's full name using OpenAlex.

    This solves the problem of ambiguous names like "D Lombardi" by finding
    ALL people with that last name who co-authored with the main researcher.

    IMPORTANT: Returns a LIST because there may be multiple valid candidates
    (e.g., "D Lombardi" could be both "Damiano Lombardi" AND "Edoardo Lombardi").

    Args:
        main_researcher_name: Name of the main researcher (e.g., "Andre Imbert").
        coauthor_partial_name: Incomplete name (e.g., "D Lombardi").
        openalex_client: OpenAlexClient instance.
        max_publications: Max publications to check.
        min_shared_publications: Minimum shared pubs to consider a candidate valid.

    Returns:
        List of ResolvedName (may be empty if no matches found).
    """
    if not openalex_client:
        openalex_client = OpenAlexClient()

    logger.info(f"Resolving name: '{coauthor_partial_name}' (co-author of {main_researcher_name})")

    # Step 1: Get main researcher's OpenAlex profile
    main_researcher = openalex_client.search_author(main_researcher_name)
    if not main_researcher:
        logger.warning(f"Main researcher not found in OpenAlex: {main_researcher_name}")
        return None

    main_researcher_id = main_researcher["id"]
    logger.info(f"  Found main researcher: {main_researcher['display_name']} ({main_researcher_id})")

    # Step 2: Get main researcher's publications
    works = openalex_client.get_author_works(main_researcher_id, max_results=max_publications)
    if not works:
        logger.warning("  No publications found")
        return None

    logger.info(f"  Checking {len(works)} publications...")

    # Extract last name from partial name (e.g., "D Lombardi" → "lombardi")
    coauthor_lastname = _extract_lastname(coauthor_partial_name).lower()
    logger.debug(f"  Looking for co-authors with last name: '{coauthor_lastname}'")

    # Step 3: Find co-author in publications
    coauthor_candidates: Dict[str, Dict[str, Any]] = {}  # {openalex_id: {name, count, works}}

    for work in works:
        authorships = work.get("authorships", [])

        for authorship in authorships:
            author_data = authorship.get("author", {})
            author_id = author_data.get("id")
            author_name = author_data.get("display_name", "")

            # Skip if no ID or if it's the main researcher
            if not author_id or author_id == main_researcher_id:
                continue

            # Check if last name matches
            if coauthor_lastname in author_name.lower():
                # Add or update candidate
                if author_id not in coauthor_candidates:
                    coauthor_candidates[author_id] = {
                        "name": author_name,
                        "openalex_id": author_id,
                        "count": 0,
                        "works": []
                    }

                coauthor_candidates[author_id]["count"] += 1
                coauthor_candidates[author_id]["works"].append({
                    "work_id": work.get("id"),
                    "title": work.get("title"),
                    "year": work.get("publication_year")
                })

    if not coauthor_candidates:
        logger.warning(f"  No co-author found with last name '{coauthor_lastname}'")
        return []

    # Step 4: Select ALL valid candidates (multiple people with same last name)
    valid_candidates = []

    for candidate_data in coauthor_candidates.values():
        # Filter: need at least min_shared_publications for confidence
        if candidate_data["count"] < min_shared_publications:
            logger.debug(
                f"  Skipping '{candidate_data['name']}': only {candidate_data['count']} "
                f"shared publication(s) (need {min_shared_publications})"
            )
            continue

        # Calculate confidence based on number of shared publications
        confidence = min(1.0, 0.5 + (candidate_data["count"] * 0.1))  # 2 pubs = 0.7, 5+ pubs = 1.0

        resolved = ResolvedName(
            original_name=coauthor_partial_name,
            resolved_name=candidate_data["name"],
            openalex_id=candidate_data["openalex_id"],
            confidence=confidence,
            shared_publications=candidate_data["count"],
            evidence=candidate_data["works"][:3]  # Keep top 3 as proof
        )

        valid_candidates.append(resolved)

        logger.info(
            f"  ✓ Candidate: '{coauthor_partial_name}' → '{resolved.resolved_name}' "
            f"(confidence: {confidence:.2f}, {candidate_data['count']} shared pubs)"
        )

        # Show evidence
        for i, work in enumerate(resolved.evidence, 1):
            logger.debug(f"    {i}. {work['title']} ({work['year']})")

    if not valid_candidates:
        logger.warning(f"  No valid candidates found (all below {min_shared_publications} shared pubs)")
        return []

    # Sort by shared publications (most first)
    valid_candidates.sort(key=lambda x: x.shared_publications, reverse=True)

    if len(valid_candidates) > 1:
        logger.info(
            f"  ⚠ MULTIPLE CANDIDATES found for '{coauthor_partial_name}': "
            f"{', '.join(c.resolved_name for c in valid_candidates)}"
        )
        logger.info(f"  → Will process each candidate separately")

    return valid_candidates


def _extract_lastname(name: str) -> str:
    """
    Extract last name from a name string.

    Examples:
        "D Lombardi" → "Lombardi"
        "Andre Imbert" → "Imbert"
        "Maria Vittoria Salvetti" → "Salvetti"

    Args:
        name: Full or partial name.

    Returns:
        Last name.
    """
    parts = name.strip().split()
    if not parts:
        return ""

    # Last part is usually the last name
    return parts[-1]


def batch_resolve_coauthors(
    main_researcher_name: str,
    coauthor_names: List[str],
    openalex_client: Optional[OpenAlexClient] = None
) -> Dict[str, Optional[ResolvedName]]:
    """
    Resolve multiple co-author names in batch.

    This is more efficient than resolving one by one because we fetch
    the main researcher's publications only once.

    Args:
        main_researcher_name: Name of the main researcher.
        coauthor_names: List of co-author names to resolve.
        openalex_client: OpenAlexClient instance.

    Returns:
        Dict mapping original names to ResolvedName (or None if not resolved).
    """
    if not openalex_client:
        openalex_client = OpenAlexClient()

    results: Dict[str, Optional[ResolvedName]] = {}

    # Get main researcher's publications once
    main_researcher = openalex_client.search_author(main_researcher_name)
    if not main_researcher:
        logger.warning(f"Main researcher not found: {main_researcher_name}")
        return {name: None for name in coauthor_names}

    main_researcher_id = main_researcher["id"]
    works = openalex_client.get_author_works(main_researcher_id, max_results=100)

    if not works:
        logger.warning("No publications found")
        return {name: None for name in coauthor_names}

    logger.info(f"Batch resolving {len(coauthor_names)} co-authors...")

    # Build a map of {lastname: [candidates]}
    lastname_to_candidates: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for work in works:
        for authorship in work.get("authorships", []):
            author_data = authorship.get("author", {})
            author_id = author_data.get("id")
            author_name = author_data.get("display_name", "")

            if not author_id or author_id == main_researcher_id:
                continue

            lastname = _extract_lastname(author_name).lower()

            if lastname not in lastname_to_candidates:
                lastname_to_candidates[lastname] = {}

            if author_id not in lastname_to_candidates[lastname]:
                lastname_to_candidates[lastname][author_id] = {
                    "name": author_name,
                    "openalex_id": author_id,
                    "count": 0,
                    "works": []
                }

            lastname_to_candidates[lastname][author_id]["count"] += 1
            lastname_to_candidates[lastname][author_id]["works"].append({
                "work_id": work.get("id"),
                "title": work.get("title"),
                "year": work.get("publication_year")
            })

    # Resolve each co-author
    for coauthor_name in coauthor_names:
        lastname = _extract_lastname(coauthor_name).lower()
        candidates = lastname_to_candidates.get(lastname, {})

        if not candidates:
            logger.debug(f"  No match for '{coauthor_name}'")
            results[coauthor_name] = None
            continue

        # Select best candidate
        best = max(candidates.values(), key=lambda x: x["count"])

        if best["count"] < 2:
            logger.debug(f"  '{coauthor_name}' → '{best['name']}' (low confidence, {best['count']} pubs)")
            results[coauthor_name] = None
            continue

        confidence = min(1.0, 0.5 + (best["count"] * 0.1))

        results[coauthor_name] = ResolvedName(
            original_name=coauthor_name,
            resolved_name=best["name"],
            openalex_id=best["openalex_id"],
            confidence=confidence,
            shared_publications=best["count"],
            evidence=best["works"][:3]
        )

        logger.info(
            f"  ✓ '{coauthor_name}' → '{best['name']}' "
            f"({best['count']} pubs, confidence: {confidence:.2f})"
        )

    return results
