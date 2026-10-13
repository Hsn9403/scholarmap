"""
Validation of patent inventors to avoid name mixing.

Problem: "thierry colin" matches a patent with:
  - Thierry Iung (inventor 1)
  - Christine Colin (inventor 2)

Solution: Verify the FULL NAME appears as a single inventor.
"""
from typing import List, Optional
from src.models import PatentsData
from src.logger import logger
import re


def validate_inventor_on_patents(
    inventor_name: str,
    patents_data: Optional[PatentsData]
) -> bool:
    """
    Validate that inventor_name appears as a COMPLETE inventor name on patents.

    Prevents mixing first names and last names from different inventors.

    Args:
        inventor_name: Full name to validate (e.g., "thierry colin")
        patents_data: Patent data for this person

    Returns:
        True if valid inventor, False if name mixing detected
    """
    if not patents_data or not patents_data.top_patents:
        # No patents = can't validate via patents (but not necessarily invalid)
        return True

    inventor_normalized = _normalize_name(inventor_name)
    inventor_parts = inventor_normalized.split()

    if len(inventor_parts) < 2:
        # Single name, hard to validate
        return True

    first_name = inventor_parts[0]
    last_name = inventor_parts[-1]

    # Check each patent for name mixing
    for patent in patents_data.top_patents:
        # ONLY check co-inventors (not the main inventor, since that's the search term)
        if not patent.co_inventors:
            continue

        # Normalize co-inventor names
        coinventors_normalized = [_normalize_name(inv) for inv in patent.co_inventors]

        # Extract first names and last names from co-inventors
        first_names_in_patent = set()
        last_names_in_patent = set()
        full_names_in_patent = set()

        for inv_norm in coinventors_normalized:
            parts = inv_norm.split()
            if len(parts) >= 2:
                first_names_in_patent.add(parts[0])
                last_names_in_patent.add(parts[-1])
                full_names_in_patent.add(inv_norm)

        # Check if OUR inventor's first name appears separately
        # AND last name appears separately
        # BUT full name does NOT appear
        has_first_separately = first_name in first_names_in_patent
        has_last_separately = last_name in last_names_in_patent
        has_full_name = inventor_normalized in full_names_in_patent

        if has_first_separately and has_last_separately and not has_full_name:
            # NAME MIXING DETECTED!
            # The patent has "Thierry [X]" and "[Y] Colin" but NOT "Thierry Colin"

            # Find which inventors have these names
            thierry_inventor = next(
                (inv for inv in patent.co_inventors if _normalize_name(inv).split()[0] == first_name),
                None
            )
            colin_inventor = next(
                (inv for inv in patent.co_inventors if _normalize_name(inv).split()[-1] == last_name),
                None
            )

            logger.warning(
                f"✗ NAME MIXING detected for '{inventor_name}'"
            )
            logger.warning(
                f"  Patent: '{patent.title[:60]}...'"
            )
            logger.warning(
                f"  Found '{thierry_inventor}' (has first name '{first_name}')"
            )
            logger.warning(
                f"  Found '{colin_inventor}' (has last name '{last_name}')"
            )
            logger.warning(
                f"  But '{inventor_name}' (complete name) does NOT appear as a single inventor!"
            )
            logger.warning(
                f"  Current assignee: {patent.current_assignee}"
            )
            return False

    logger.info(
        f"✓ Inventor name '{inventor_name}' validated on {len(patents_data.top_patents)} patent(s)"
    )
    return True


def _normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    # Remove extra whitespace, lowercase
    name = re.sub(r'\s+', ' ', name.strip().lower())
    # Remove common suffixes
    name = re.sub(r'\s+(jr|sr|iii|ii|iv)\.?$', '', name)
    return name


def _names_match(name1: str, name2: str) -> bool:
    """
    Check if two normalized names match.

    Handles:
    - Exact match
    - Initials vs full names
    """
    if name1 == name2:
        return True

    parts1 = name1.split()
    parts2 = name2.split()

    if len(parts1) != len(parts2):
        return False

    # Check each part
    for p1, p2 in zip(parts1, parts2):
        # Exact match
        if p1 == p2:
            continue

        # One is initial, other is full
        if (len(p1) == 1 and p2.startswith(p1)) or \
           (len(p2) == 1 and p1.startswith(p2)):
            continue

        # No match
        return False

    return True
