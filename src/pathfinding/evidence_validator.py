"""
Evidence validator for corporate connections.

This module provides functions to VERIFY evidence before accepting it.

CRITICAL: No guessing allowed. If we can't verify, we REJECT.
"""
import re
from typing import List, Optional, Tuple
from src.logger import logger


def normalize_name_for_matching(name: str) -> str:
    """
    Normalize name for matching.

    Handles:
    - Lowercasing
    - Removing accents
    - Removing punctuation
    - Removing extra whitespace

    Args:
        name: Raw name.

    Returns:
        Normalized name.
    """
    import unicodedata

    # Lowercase
    name = name.lower()

    # Remove accents (é → e)
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )

    # Remove punctuation except spaces and hyphens
    name = re.sub(r'[^\w\s-]', '', name)

    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def names_match_flexible(name1: str, name2: str, allow_initials: bool = True) -> Tuple[bool, float]:
    """
    Check if two names match with flexible rules.

    Rules:
    - Exact match: 1.0 confidence
    - Initial match: 0.8 confidence (e.g., "J Weller" = "John Weller")
      BUT: Only if the first letter matches (case-insensitive)
    - Partial match: 0.7 confidence (e.g., "J. Weller" = "J Weller")

    IMPORTANT: "A Bottaro" will match BOTH "Andrea Bottaro" and "André Bottaro"
    because both start with 'A'. This is intentionally permissive but with
    REDUCED confidence (0.8) to flag potential ambiguity.

    Args:
        name1: First name (normalized).
        name2: Second name (normalized).
        allow_initials: Whether to allow initial matching.

    Returns:
        (match, confidence) tuple.
    """
    name1 = normalize_name_for_matching(name1)
    name2 = normalize_name_for_matching(name2)

    # Exact match
    if name1 == name2:
        return (True, 1.0)

    if not allow_initials:
        return (False, 0.0)

    # Split into parts
    parts1 = name1.split()
    parts2 = name2.split()

    if len(parts1) != len(parts2):
        return (False, 0.0)

    # Check each part
    all_match = True
    has_initial = False
    has_ambiguous_initial = False

    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            continue

        # One is initial, other is full
        if len(p1) == 1 and p2.startswith(p1):
            has_initial = True
            # Check if this could be ambiguous (first name with single letter)
            # e.g., "A" could be Andrea, André, Antonio, etc.
            if parts1.index(p1) == 0:  # First name position
                has_ambiguous_initial = True
            continue
        elif len(p2) == 1 and p1.startswith(p2):
            has_initial = True
            # Check if this could be ambiguous
            if parts2.index(p2) == 0:  # First name position
                has_ambiguous_initial = True
            continue

        # No match
        all_match = False
        break

    if all_match:
        if has_ambiguous_initial:
            # Reduced confidence due to ambiguity
            # "A Bottaro" matching "André Bottaro" or "Andrea Bottaro"
            confidence = 0.75  # Lower than before (was 0.9)
        elif has_initial:
            confidence = 0.85
        else:
            confidence = 1.0
        return (True, confidence)

    return (False, 0.0)


def find_matching_inventor(
    search_name: str,
    inventors_list: List[str],
    min_confidence: float = 0.85
) -> Optional[Tuple[str, float]]:
    """
    Find matching inventor in a list.

    Args:
        search_name: Name to search for.
        inventors_list: List of inventor names from patent.
        min_confidence: Minimum confidence to accept a match.

    Returns:
        (matching_name, confidence) or None if no match.
    """
    best_match = None
    best_confidence = 0.0

    for inventor in inventors_list:
        match, confidence = names_match_flexible(search_name, inventor, allow_initials=True)

        if match and confidence >= min_confidence:
            if confidence > best_confidence:
                best_match = inventor
                best_confidence = confidence

    if best_match:
        logger.debug(f"Matched '{search_name}' to inventor '{best_match}' (confidence: {best_confidence:.2f})")
        return (best_match, best_confidence)

    logger.debug(f"No match for '{search_name}' in inventors: {', '.join(inventors_list[:5])}...")
    return None


def validate_patent_inventor(
    coauthor_name: str,
    patent_inventors: List[str],
    patent_id: str,
    min_confidence: float = 0.85
) -> Tuple[bool, Optional[str], float]:
    """
    Validate that a co-author is actually an inventor on a patent.

    This is CRITICAL: we must verify the name appears in the inventors list.

    Args:
        coauthor_name: Name to validate.
        patent_inventors: List of ALL inventors on the patent.
        patent_id: Patent ID (for logging).
        min_confidence: Minimum confidence to accept.

    Returns:
        (is_valid, matching_inventor_name, confidence) tuple.
    """
    if not patent_inventors:
        logger.warning(f"Patent {patent_id} has NO inventors list - cannot validate")
        return (False, None, 0.0)

    result = find_matching_inventor(coauthor_name, patent_inventors, min_confidence)

    if result:
        matching_name, confidence = result
        logger.info(f"✓ Inventor validated: '{coauthor_name}' → '{matching_name}' on patent {patent_id}")
        return (True, matching_name, confidence)
    else:
        logger.warning(f"✗ Inventor NOT found: '{coauthor_name}' not in patent {patent_id} inventors")
        logger.debug(f"  Inventors on patent: {', '.join(patent_inventors)}")
        return (False, None, 0.0)


def validate_publication_affiliation(
    author_name: str,
    authorship_data: dict,
    work_id: str
) -> Tuple[bool, Optional[dict]]:
    """
    Validate that an author is affiliated with a corporate institution in a publication.

    Args:
        author_name: Name to validate.
        authorship_data: OpenAlex authorship dict.
        work_id: Work ID (for logging).

    Returns:
        (is_valid, institution_data) tuple.
    """
    author_data = authorship_data.get("author", {})
    author_display_name = author_data.get("display_name", "")

    # Check if author name matches
    match, confidence = names_match_flexible(author_name, author_display_name, allow_initials=True)

    if not match:
        logger.debug(f"Author name mismatch: '{author_name}' vs '{author_display_name}'")
        return (False, None)

    # Check institutions
    institutions = authorship_data.get("institutions", [])

    if not institutions:
        logger.debug(f"No institutions for author '{author_display_name}' in work {work_id}")
        return (False, None)

    # Return first institution (usually primary affiliation)
    institution = institutions[0]
    logger.info(f"✓ Affiliation validated: '{author_name}' → '{institution.get('display_name')}' in work {work_id}")

    return (True, institution)


def check_name_ambiguity(
    coauthor_name: str,
    resolved_candidates: List[dict],
    max_candidates: int = 3
) -> Tuple[bool, str]:
    """
    Check if a co-author name is highly ambiguous.

    Args:
        coauthor_name: Name to check.
        resolved_candidates: List of OpenAlex candidates.
        max_candidates: Maximum candidates before marking as ambiguous.

    Returns:
        (is_ambiguous, reason) tuple.
    """
    if not resolved_candidates:
        return (False, "No ambiguity (no candidates found)")

    if len(resolved_candidates) > max_candidates:
        names = ', '.join(c.get("resolved_name", "?") for c in resolved_candidates[:5])
        return (
            True,
            f"High ambiguity: {len(resolved_candidates)} candidates found ({names}...)"
        )

    # Check if top candidates have similar confidence
    if len(resolved_candidates) >= 2:
        confidences = [c.get("confidence", 0.0) for c in resolved_candidates]
        top_conf = confidences[0]
        second_conf = confidences[1]

        if abs(top_conf - second_conf) < 0.1:
            return (
                True,
                f"High ambiguity: Top 2 candidates have similar confidence ({top_conf:.2f} vs {second_conf:.2f})"
            )

    return (False, "No significant ambiguity")
