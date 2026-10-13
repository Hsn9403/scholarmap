"""
Validation of co-author identity to avoid ambiguity.

Problem: "E Lombardi" could match Elizabeth, Edward, or Edoardo.
Solution: Validate that the found scientist actually co-authored with the seed scientist.
"""
from typing import Optional, List
from src.models import ScholarData, CoAuthor
from src.logger import logger


def validate_coauthor_identity(
    seed_scientist: ScholarData,
    coauthor_candidate: CoAuthor,
    candidate_scholar_data: Optional[ScholarData]
) -> bool:
    """
    Validate that the candidate scholar is the correct co-author.

    Checks if they have publications in common with the seed scientist.

    Args:
        seed_scientist: The main scientist's data
        coauthor_candidate: The co-author from seed's publication list
        candidate_scholar_data: Scholar data retrieved for the candidate

    Returns:
        True if validated (shared publications found), False otherwise
    """
    if not candidate_scholar_data:
        logger.warning(f"Cannot validate {coauthor_candidate.name}: no Scholar data")
        return False

    # Get expected shared publication titles from coauthor_candidate
    expected_titles = set()
    if coauthor_candidate.example_titles:
        for title in coauthor_candidate.example_titles:
            expected_titles.add(_normalize_title(title))

    # Also collect titles from seed scientist's publications where coauthor appears
    for pub in seed_scientist.top_publications:
        if pub.authors and any(
            _names_match(coauthor_candidate.name, author)
            for author in pub.authors
        ):
            expected_titles.add(_normalize_title(pub.title))

    if not expected_titles:
        logger.warning(
            f"Cannot validate {coauthor_candidate.name}: "
            f"no example titles available"
        )
        return True  # Benefit of the doubt

    # Check if candidate has ANY of these publications
    candidate_titles = {
        _normalize_title(pub.title)
        for pub in candidate_scholar_data.top_publications
    }

    matches = expected_titles & candidate_titles
    match_ratio = len(matches) / len(expected_titles) if expected_titles else 0

    if matches:
        logger.info(
            f"✓ Validated {coauthor_candidate.name} → {candidate_scholar_data.name}: "
            f"{len(matches)}/{len(expected_titles)} shared publications"
        )
        return True
    else:
        logger.warning(
            f"✗ FAILED validation for {coauthor_candidate.name} → {candidate_scholar_data.name}: "
            f"NO shared publications found! This is likely the WRONG person."
        )
        logger.warning(
            f"  Expected titles: {list(expected_titles)[:3]}"
        )
        logger.warning(
            f"  Candidate titles: {list(candidate_titles)[:3]}"
        )
        return False


def _normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    import re
    # Lowercase, remove punctuation, collapse whitespace
    title = title.lower()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def _names_match(name1: str, name2: str) -> bool:
    """
    Check if two names likely refer to the same person.

    Handles:
    - "E Lombardi" matches "Edoardo Lombardi" ✓
    - "E Lombardi" does NOT match "Elizabeth Lombardi" ✗
    """
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Exact match
    if n1 == n2:
        return True

    # Split into parts
    parts1 = n1.split()
    parts2 = n2.split()

    if not parts1 or not parts2:
        return False

    # Last name must match
    if parts1[-1] != parts2[-1]:
        return False

    # Check first name/initial
    first1 = parts1[0]
    first2 = parts2[0]

    # If one is initial, check if it matches first letter
    if len(first1) == 1 or len(first2) == 1:
        return first1[0] == first2[0]

    # Otherwise, full match required
    return first1 == first2
