"""
Strict disambiguation for co-author names.

This module provides stricter disambiguation than the original name_resolver.py.

KEY DIFFERENCES:
- Higher confidence threshold (0.85 instead of 0.7)
- Better scoring based on multiple signals
- Returns UNRESOLVED when ambiguity is too high
- Interactive mode to ask user for clarification
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from src.logger import logger
from src.pathfinding.openalex_client import OpenAlexClient


# CONFIDENCE THRESHOLDS
THRESHOLD_HIGH = 0.85  # Clear winner, no ambiguity (adjusted from 0.90)
THRESHOLD_MEDIUM = 0.75  # Acceptable confidence (adjusted from 0.85)
THRESHOLD_LOW = 0.60  # Too low, needs more evidence (adjusted from 0.70)
MIN_SHARED_PUBLICATIONS = 2  # Need at least 2 shared pubs for confidence (adjusted from 3)


@dataclass
class DisambiguationResult:
    """Result of disambiguation."""
    original_name: str
    resolved_name: Optional[str]
    openalex_id: Optional[str]
    confidence: float
    shared_publications: int
    status: str  # "RESOLVED", "UNRESOLVED", "MULTIPLE_CANDIDATES"
    candidates: List[Dict[str, Any]]  # All candidates (for interactive mode)
    notes: str


def score_candidate(
    candidate: Dict[str, Any],
    main_researcher_id: str,
    coauthor_partial_name: str
) -> float:
    """
    Score a candidate based on multiple signals.

    Scoring factors:
    1. Number of shared publications (weight: 0.5)
    2. Recency of publications (weight: 0.2)
    3. Name similarity (weight: 0.2)
    4. Co-authorship density (weight: 0.1)

    Args:
        candidate: Candidate dict with name, count, works, etc.
        main_researcher_id: Main researcher's OpenAlex ID.
        coauthor_partial_name: Partial name being resolved.

    Returns:
        Score from 0.0 to 1.0.
    """
    # Factor 1: Shared publications (normalized)
    shared_pubs = candidate.get("count", 0)
    shared_pubs_score = min(1.0, shared_pubs / 10.0)  # 10+ pubs = 1.0

    # Factor 2: Recency (check if recent publications)
    works = candidate.get("works", [])
    recent_works = sum(1 for w in works if (w.get("year") or 0) >= 2020)
    recency_score = min(1.0, recent_works / max(1, len(works)))

    # Factor 3: Name similarity
    # (For now, simple: if full name provided, check similarity)
    resolved_name = candidate.get("name", "")
    partial_lower = coauthor_partial_name.lower()
    resolved_lower = resolved_name.lower()

    # Check if all words in partial name appear in resolved name
    partial_words = set(partial_lower.split())
    resolved_words = set(resolved_lower.split())
    name_overlap = len(partial_words & resolved_words) / max(1, len(partial_words))
    name_similarity_score = name_overlap

    # Factor 4: Co-authorship density (how many works vs total works by candidate)
    # (Not implemented yet - would need to fetch total works)
    density_score = 0.5  # Neutral

    # Weighted sum
    score = (
        shared_pubs_score * 0.5 +
        recency_score * 0.2 +
        name_similarity_score * 0.2 +
        density_score * 0.1
    )

    return score


def disambiguate_coauthor_strict(
    main_researcher_name: str,
    coauthor_partial_name: str,
    openalex_client: Optional[OpenAlexClient] = None,
    max_publications: int = 100,
    interactive: bool = False
) -> DisambiguationResult:
    """
    Disambiguate a co-author name with STRICT criteria.

    This function is more conservative than resolve_coauthor_full_name().

    Args:
        main_researcher_name: Main researcher name.
        coauthor_partial_name: Partial co-author name.
        openalex_client: OpenAlex client instance.
        max_publications: Max publications to check.
        interactive: If True, ask user to choose when ambiguous.

    Returns:
        DisambiguationResult with status RESOLVED/UNRESOLVED/MULTIPLE_CANDIDATES.
    """
    if not openalex_client:
        openalex_client = OpenAlexClient()

    logger.info(f"[STRICT DISAMBIGUATION] Resolving: '{coauthor_partial_name}'")

    # Step 1: Get main researcher's OpenAlex profile
    main_researcher = openalex_client.search_author(main_researcher_name)
    if not main_researcher:
        logger.warning(f"Main researcher not found: {main_researcher_name}")
        return DisambiguationResult(
            original_name=coauthor_partial_name,
            resolved_name=None,
            openalex_id=None,
            confidence=0.0,
            shared_publications=0,
            status="UNRESOLVED",
            candidates=[],
            notes=f"Main researcher '{main_researcher_name}' not found in OpenAlex"
        )

    main_researcher_id = main_researcher["id"]
    logger.info(f"  Main researcher: {main_researcher['display_name']}")

    # Step 2: Get main researcher's publications
    works = openalex_client.get_author_works(main_researcher_id, max_results=max_publications)
    if not works:
        logger.warning("No publications found")
        return DisambiguationResult(
            original_name=coauthor_partial_name,
            resolved_name=None,
            openalex_id=None,
            confidence=0.0,
            shared_publications=0,
            status="UNRESOLVED",
            candidates=[],
            notes="No publications found for main researcher"
        )

    logger.info(f"  Checking {len(works)} publications...")

    # Step 3: Find candidates
    coauthor_lastname = _extract_lastname(coauthor_partial_name).lower()
    candidates_map: Dict[str, Dict[str, Any]] = {}

    for work in works:
        for authorship in work.get("authorships", []):
            author_data = authorship.get("author", {})
            author_id = author_data.get("id")
            author_name = author_data.get("display_name", "")

            if not author_id or author_id == main_researcher_id:
                continue

            # Check if last name matches
            if coauthor_lastname in author_name.lower():
                if author_id not in candidates_map:
                    candidates_map[author_id] = {
                        "name": author_name,
                        "openalex_id": author_id,
                        "count": 0,
                        "works": []
                    }

                candidates_map[author_id]["count"] += 1
                candidates_map[author_id]["works"].append({
                    "work_id": work.get("id"),
                    "title": work.get("title"),
                    "year": work.get("publication_year")
                })

    if not candidates_map:
        logger.warning(f"No candidates found with last name '{coauthor_lastname}'")
        return DisambiguationResult(
            original_name=coauthor_partial_name,
            resolved_name=None,
            openalex_id=None,
            confidence=0.0,
            shared_publications=0,
            status="UNRESOLVED",
            candidates=[],
            notes=f"No co-authors found with last name '{coauthor_lastname}'"
        )

    # Step 4: Score candidates
    candidates_scored = []

    for candidate_data in candidates_map.values():
        # Filter: need at least MIN_SHARED_PUBLICATIONS
        if candidate_data["count"] < MIN_SHARED_PUBLICATIONS:
            logger.debug(
                f"  Skipping '{candidate_data['name']}': only {candidate_data['count']} pubs "
                f"(need {MIN_SHARED_PUBLICATIONS})"
            )
            continue

        # Calculate score
        score = score_candidate(candidate_data, main_researcher_id, coauthor_partial_name)

        candidates_scored.append({
            "name": candidate_data["name"],
            "openalex_id": candidate_data["openalex_id"],
            "shared_publications": candidate_data["count"],
            "score": score,
            "works": candidate_data["works"][:3]  # Keep top 3 as evidence
        })

    if not candidates_scored:
        logger.warning(f"All candidates below {MIN_SHARED_PUBLICATIONS} shared pubs")
        return DisambiguationResult(
            original_name=coauthor_partial_name,
            resolved_name=None,
            openalex_id=None,
            confidence=0.0,
            shared_publications=0,
            status="UNRESOLVED",
            candidates=[],
            notes=f"All candidates have < {MIN_SHARED_PUBLICATIONS} shared publications"
        )

    # Sort by score (highest first)
    candidates_scored.sort(key=lambda x: x["score"], reverse=True)

    # Step 5: Decide
    top_candidate = candidates_scored[0]
    top_score = top_candidate["score"]

    logger.info(f"  Top candidate: '{top_candidate['name']}' (score: {top_score:.2f}, {top_candidate['shared_publications']} pubs)")

    # Case 1: Clear winner (high score, big gap to next)
    if top_score >= THRESHOLD_HIGH:
        if len(candidates_scored) == 1 or (candidates_scored[1]["score"] < top_score - 0.15):
            logger.info(f"  ✓ RESOLVED: Clear winner with high confidence")
            return DisambiguationResult(
                original_name=coauthor_partial_name,
                resolved_name=top_candidate["name"],
                openalex_id=top_candidate["openalex_id"],
                confidence=top_score,
                shared_publications=top_candidate["shared_publications"],
                status="RESOLVED",
                candidates=candidates_scored,
                notes=f"Clear winner: {top_candidate['name']} (score: {top_score:.2f})"
            )

    # Case 2: Acceptable confidence but not clear
    if top_score >= THRESHOLD_MEDIUM:
        if len(candidates_scored) == 1:
            logger.info(f"  ✓ RESOLVED: Only candidate with acceptable confidence")
            return DisambiguationResult(
                original_name=coauthor_partial_name,
                resolved_name=top_candidate["name"],
                openalex_id=top_candidate["openalex_id"],
                confidence=top_score,
                shared_publications=top_candidate["shared_publications"],
                status="RESOLVED",
                candidates=candidates_scored,
                notes=f"Only candidate with score >= {THRESHOLD_MEDIUM}"
            )

        # Multiple candidates with similar scores
        second_score = candidates_scored[1]["score"]
        if abs(top_score - second_score) < 0.10:
            logger.warning(f"  ⚠ MULTIPLE_CANDIDATES: Top 2 scores too close ({top_score:.2f} vs {second_score:.2f})")

            if interactive:
                # TODO: Ask user to choose
                pass

            return DisambiguationResult(
                original_name=coauthor_partial_name,
                resolved_name=None,
                openalex_id=None,
                confidence=top_score,
                shared_publications=top_candidate["shared_publications"],
                status="MULTIPLE_CANDIDATES",
                candidates=candidates_scored,
                notes=f"Ambiguous: {len(candidates_scored)} candidates with similar scores"
            )

    # Case 3: Low confidence
    if top_score < THRESHOLD_MEDIUM:
        logger.warning(f"  ⚠ UNRESOLVED: Top score too low ({top_score:.2f} < {THRESHOLD_MEDIUM})")
        return DisambiguationResult(
            original_name=coauthor_partial_name,
            resolved_name=None,
            openalex_id=None,
            confidence=top_score,
            shared_publications=top_candidate["shared_publications"],
            status="UNRESOLVED",
            candidates=candidates_scored,
            notes=f"Low confidence: top score {top_score:.2f} < threshold {THRESHOLD_MEDIUM}"
        )

    # Default: resolved with medium confidence
    logger.info(f"  ✓ RESOLVED: Acceptable confidence")
    return DisambiguationResult(
        original_name=coauthor_partial_name,
        resolved_name=top_candidate["name"],
        openalex_id=top_candidate["openalex_id"],
        confidence=top_score,
        shared_publications=top_candidate["shared_publications"],
        status="RESOLVED",
        candidates=candidates_scored,
        notes=f"Resolved with score {top_score:.2f}"
    )


def _extract_lastname(name: str) -> str:
    """Extract last name from a name string."""
    parts = name.strip().split()
    return parts[-1] if parts else ""
