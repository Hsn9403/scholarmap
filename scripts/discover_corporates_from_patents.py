#!/usr/bin/env python3
"""
Discover corporate connections from patents.

This script:
1. Searches patents for a researcher
2. Extracts all assignees (current owners + citing companies)
3. Filters to keep only corporate entities
4. Adds them to the database
5. Regenerates the graph
"""
import re
from pathlib import Path
from typing import Set

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.patents.client import PatentsClient
from src.database.database import SessionLocal
from src.database.models import Scientist, Corporate
from src.database.add_coauthor_industry_connections import ScientistCorporate
from src.helpers import slug
from src.logger import logger


# Keywords to identify corporate entities
CORPORATE_INDICATORS = [
    r'\binc\b', r'\bincorporated\b', r'\bcorp\b', r'\bcorporation\b',
    r'\bltd\b', r'\blimited\b', r'\bgmbh\b', r'\bag\b', r'\bs\.a\b',
    r'\bllc\b', r'\bco\b', r'\bcompany\b', r'\bgroup\b',
    r'\bpharma\b', r'\btherapeutics\b', r'\bbiotech\b',
    r'\btechnologies\b', r'\bsystems\b', r'\bsolutions\b'
]

# Keywords to exclude (individuals, universities, government)
EXCLUDE_PATTERNS = [
    r'\buniversity\b', r'\buniversité\b', r'\bcollege\b',
    r'\binstitute\b', r'\bhospital\b', r'\bclinic\b',
    r'\bmedical center\b', r'\bschool\b', r'\bacademy\b',
    r'\bnational\b', r'\bgovernment\b', r'\bministry\b',
    r'\bdepartment of\b', r'\bpublic health\b',
    # Exclude individual names (simple heuristic: < 3 words, no corporate suffix)
]


def is_corporate(name: str) -> bool:
    """
    Determine if a name is a corporate entity.

    Args:
        name: Assignee name.

    Returns:
        True if corporate, False otherwise.
    """
    if not name or len(name.strip()) < 3:
        return False

    name_lower = name.lower()

    # Exclude academic/government
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, name_lower):
            return False

    # Check for corporate indicators
    for pattern in CORPORATE_INDICATORS:
        if re.search(pattern, name_lower):
            return True

    # Additional heuristics
    # If name has 4+ words and contains capitalized words, likely corporate
    words = name.split()
    if len(words) >= 3:
        capitalized = sum(1 for w in words if w and w[0].isupper())
        if capitalized >= 2:
            return True

    return False


def discover_corporates_from_patents(researcher_name: str, max_patents: int = 20) -> Set[str]:
    """
    Discover corporate connections from researcher's patents.

    Args:
        researcher_name: Name of the researcher.
        max_patents: Maximum patents to analyze.

    Returns:
        Set of corporate names found.
    """
    logger.info("="*80)
    logger.info(f"DISCOVERING CORPORATES FROM PATENTS: {researcher_name}")
    logger.info("="*80)

    patents_client = PatentsClient()
    corporates = set()

    try:
        # Fetch patents data
        logger.info(f"\n1. Searching patents for: {researcher_name}")
        patents_data = patents_client.fetch_patents_data(
            inventor_name=researcher_name,
            max_patents=max_patents
        )

        logger.info(f"✓ Found {patents_data.patents_total} total patents")
        logger.info(f"✓ Analyzing {len(patents_data.top_patents)} patents\n")

        # Extract all assignees
        logger.info("2. Extracting assignees from patents...")

        for i, patent in enumerate(patents_data.top_patents, 1):
            logger.info(f"\n[{i}/{len(patents_data.top_patents)}] {patent.title[:60]}...")

            # Current assignee (owner) - PERTINENT: relation directe
            if patent.current_assignee:
                assignee = patent.current_assignee.strip()
                if is_corporate(assignee):
                    corporates.add(assignee)
                    logger.info(f"  ✓ Owner: {assignee}")
                else:
                    logger.debug(f"  ✗ Owner (not corporate): {assignee}")

            # Citing assignees (companies that cited this patent) - PERTINENT: intérêt pour le travail
            for citing_assignee in (patent.citing_assignees or []):
                if citing_assignee and citing_assignee != "no corporate has cited this patent":
                    assignee = citing_assignee.strip()
                    if is_corporate(assignee):
                        corporates.add(assignee)
                        logger.info(f"  ✓ Cited by: {assignee}")

            # IMPORTANT: On N'inclut PAS les "cited assignees" car citer un brevet
            # n'indique PAS une relation de proximité, juste une référence bibliographique

        logger.info(f"\n✓ Found {len(corporates)} unique corporate entities")

    except Exception as e:
        logger.error(f"Error extracting corporates from patents: {e}")

    return corporates


def add_corporates_to_database(
    researcher_name: str,
    corporates: Set[str],
    affiliation_type: str = "patent_assignee"
) -> int:
    """
    Add discovered corporates to the database.

    IMPORTANT: When corporates are discovered from patents, we DON'T create
    direct Scientist → Corporate links because the patent nodes already show
    this connection (Scientist → Patent → Corporate).

    This function now only adds the Corporate entities to the database,
    NOT the links, to avoid redundant edges in the graph.

    Args:
        researcher_name: Name of the researcher.
        corporates: Set of corporate names.
        affiliation_type: Type of affiliation (default: "patent_assignee").

    Returns:
        Number of new corporates added (NOT links).
    """
    if not corporates:
        logger.info("No corporates to add.")
        return 0

    logger.info(f"\n3. Adding corporates to database...")
    logger.info(f"   Note: NOT creating direct links (patents show the connection)")

    db = SessionLocal()
    new_corporates = 0

    try:
        # Add each corporate (but don't create links)
        for corporate_name in corporates:
            # Get or create corporate
            corporate = db.query(Corporate).filter_by(
                normalized_name=slug(corporate_name)
            ).first()

            if not corporate:
                corporate = Corporate(
                    name=corporate_name,
                    normalized_name=slug(corporate_name),
                    notes="Discovered from patent assignee"
                )
                db.add(corporate)
                db.commit()
                logger.info(f"  ✓ Added corporate: {corporate_name}")
                new_corporates += 1
            else:
                logger.debug(f"  → Corporate already exists: {corporate_name}")

        logger.info(f"\n✓ Added {new_corporates} new corporate(s) to database")
        logger.info(f"   Connections will be shown via patent nodes in the graph")

    except Exception as e:
        logger.error(f"Error adding corporates to database: {e}")
        db.rollback()
    finally:
        db.close()

    return new_corporates


def main():
    """Main execution."""
    import sys

    # Get researcher name from command line or use default
    if len(sys.argv) > 1:
        researcher_name = " ".join(sys.argv[1:])
    else:
        researcher_name = "Andre Imbert"
        print("💡 Usage: python discover_corporates_from_patents.py \"Researcher Name\"")
        print(f"   Using default: {researcher_name}\n")

    print(f"\n{'='*80}")
    print(f"PATENT-BASED CORPORATE DISCOVERY")
    print(f"Researcher: {researcher_name}")
    print(f"{'='*80}\n")

    # Step 1: Discover corporates from patents
    corporates = discover_corporates_from_patents(
        researcher_name=researcher_name,
        max_patents=20
    )

    if not corporates:
        print(f"\n⚠️  No corporates found in patents for {researcher_name}")
        print("This could mean:")
        print("  • No patents found for this researcher")
        print("  • Patents are assigned to individuals, not companies")
        print("  • Patents are assigned to universities/research institutes")
        return

    # Step 2: Show results and ask for confirmation
    print(f"\n{'='*80}")
    print(f"DISCOVERED {len(corporates)} CORPORATES FROM PATENTS")
    print(f"{'='*80}\n")

    for i, corporate in enumerate(sorted(corporates), 1):
        print(f"  {i}. {corporate}")

    # Step 3: Add to database
    new_links = add_corporates_to_database(
        researcher_name=researcher_name,
        corporates=corporates
    )

    # Step 4: Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"  • Corporates discovered: {len(corporates)}")
    print(f"  • New database links: {new_links}")
    print(f"\n💡 Next step: Regenerate the graph to see the new connections")
    print(f"  Run: .venv/bin/python regenerate_andre_graph.py")
    print("="*80)


if __name__ == "__main__":
    main()
