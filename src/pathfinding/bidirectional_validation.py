"""
Bidirectional co-author validation using Google Scholar profiles.

Problem: "A Ferrero" could match multiple people with the same name.
Solution: Check if the candidate lists the seed scientist in THEIR co-authors list.

This is the SIMPLEST and MOST RELIABLE method:
- If Andre Imbert lists "Michel Bergmann" as co-author
- AND Michel Bergmann lists "Andre Imbert" as co-author
- → They are definitely co-authors!

Google Scholar has already done the disambiguation work for us.
"""
from typing import Optional
from src.models import CoAuthor
from src.scholar.client import ScholarClient
from src.logger import logger


def validate_coauthor_bidirectional(
    seed_scientist_name: str,
    seed_scientist_id: Optional[str],
    coauthor_candidate: CoAuthor,
    scholar_client: Optional[ScholarClient] = None
) -> bool:
    """
    Validate co-author by checking if they list the seed scientist in THEIR profile.

    This is a bidirectional check:
    1. Seed lists candidate as co-author (already known)
    2. Candidate lists seed as co-author (this function checks)

    Args:
        seed_scientist_name: Name of the main scientist
        seed_scientist_id: Scholar ID of the main scientist (optional but recommended)
        coauthor_candidate: The co-author to validate (must have scholar_id)
        scholar_client: ScholarClient instance (optional, will create if not provided)

    Returns:
        True if validated (bidirectional match), False otherwise
    """
    # If candidate has no Scholar ID, we can't check their profile
    if not coauthor_candidate.scholar_id:
        logger.debug(
            f"Cannot validate {coauthor_candidate.name} bidirectionally: "
            f"no Scholar ID available"
        )
        return True  # Benefit of the doubt (will rely on other validations)

    # Create client if not provided
    if not scholar_client:
        scholar_client = ScholarClient()

    try:
        # Fetch the co-author's profile
        logger.info(f"Checking {coauthor_candidate.name}'s profile for bidirectional validation...")
        coauthor_profile = scholar_client.fetch_author_data(
            coauthor_candidate.scholar_id,
            num_articles=1  # We only need co-authors list, not articles
        )

        # Get the co-author's co-authors list
        their_coauthors = coauthor_profile.coauthors

        # Normalize seed scientist name for matching
        seed_normalized = scholar_client._normalize_name(seed_scientist_name)

        # Check if seed scientist is in their co-authors list
        for their_coauthor in their_coauthors:
            their_coauthor_normalized = scholar_client._normalize_name(their_coauthor.name)

            # Strategy 1: Check by Scholar ID (most reliable)
            if seed_scientist_id and their_coauthor.scholar_id:
                if their_coauthor.scholar_id == seed_scientist_id:
                    logger.info(
                        f"✓ BIDIRECTIONAL MATCH (by ID): {coauthor_candidate.name} lists "
                        f"{seed_scientist_name} as co-author"
                    )
                    return True

            # Strategy 2: Check by name (if no ID match)
            if scholar_client._is_same_person(seed_normalized, their_coauthor_normalized):
                logger.info(
                    f"✓ BIDIRECTIONAL MATCH (by name): {coauthor_candidate.name} lists "
                    f"'{their_coauthor.name}' as co-author (matches '{seed_scientist_name}')"
                )
                return True

        # Not found in their co-authors list
        logger.warning(
            f"✗ BIDIRECTIONAL MISMATCH: {coauthor_candidate.name} does NOT list "
            f"{seed_scientist_name} as co-author. This is likely a different person "
            f"with the same name!"
        )
        logger.debug(
            f"  Their co-authors ({len(their_coauthors)}): "
            f"{[c.name for c in their_coauthors[:10]]}"
        )
        return False

    except Exception as e:
        logger.warning(
            f"Failed to validate {coauthor_candidate.name} bidirectionally: {e}"
        )
        # On error, give benefit of the doubt (will rely on other validations)
        return True


def should_use_bidirectional_validation(coauthor: CoAuthor) -> bool:
    """
    Determine if bidirectional validation should be used for a co-author.

    Use bidirectional validation when:
    - Co-author has a Scholar ID (can fetch their profile)
    - Co-author has a common name that could have homonymes

    Args:
        coauthor: The co-author to check

    Returns:
        True if bidirectional validation is recommended
    """
    # Always use if Scholar ID is available
    if coauthor.scholar_id:
        return True

    # If no Scholar ID, skip bidirectional validation
    return False
