#!/usr/bin/env python3
"""
Enrich author names using Crossref API.

This script uses Crossref API to replace "Initial + Lastname" format with
"Firstname + Lastname" format in the database.

Strategy:
1. Find scientists with initial-only first names (e.g., "A. Nedelec", "P Sharan")
2. For each scientist, look at their publications
3. Query Crossref for each publication to get full author names
4. Match the scientist by last name and initial
5. Update the scientist's name in the database if a match is found

Example:
    $ python src/database/enrich_with_crossref.py
    $ python src/database/enrich_with_crossref.py --dry-run  # Preview only
    $ python src/database/enrich_with_crossref.py --limit 10  # Process only 10 scientists
"""
import sys
import argparse
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Scientist, Publication, PublicationAuthor
from src.api.crossref_client import CrossrefClient
from src.logger import logger


def normalize_for_comparison(name: str) -> str:
    """
    Normalize name for comparison (remove accents, lowercase).

    Args:
        name: Name to normalize.

    Returns:
        Normalized name.
    """
    # Remove accents
    nfd = unicodedata.normalize('NFD', name)
    without_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    # Lowercase and strip
    return without_accents.lower().strip()


def has_initial_only_firstname(name: str) -> bool:
    """
    Check if a name has only an initial for the first name.

    Returns True for:
    - "A. Nedelec"
    - "A Nedelec"
    - "P. Sharan"

    Returns False for:
    - "Alice Nedelec"
    - "Priyanka Sharan"

    Args:
        name: Scientist name to check.

    Returns:
        True if first name is only an initial.
    """
    parts = name.strip().split()
    if len(parts) < 2:
        return False

    first_part = parts[0].replace(".", "").strip()

    # Check if first part is a single letter
    return len(first_part) == 1


def extract_lastname_and_initial(name: str) -> tuple[str, str]:
    """
    Extract last name and first initial from a name.

    Args:
        name: Name to parse (e.g., "A. Nedelec").

    Returns:
        Tuple of (lastname, initial) in lowercase.

    Example:
        >>> extract_lastname_and_initial("A. Nedelec")
        ('nedelec', 'a')
    """
    parts = name.strip().replace(".", "").split()
    if len(parts) < 2:
        return ("", "")

    lastname = parts[-1].lower()
    initial = parts[0][0].lower() if parts[0] else ""

    return (lastname, initial)


def find_full_name_from_publications(
    scientist: Scientist,
    db,
    crossref_client: CrossrefClient,
    max_pubs: int = 5
) -> Optional[str]:
    """
    Find full name for a scientist by querying Crossref for their publications.

    Args:
        scientist: Scientist with initial-only first name.
        db: Database session.
        crossref_client: Crossref API client.
        max_pubs: Maximum number of publications to check (default: 5).

    Returns:
        Full name if found (e.g., "Alice Nedelec"), or None.
    """
    # Get scientist's publications (limit to recent ones)
    publications = (
        db.query(Publication)
        .join(PublicationAuthor)
        .filter(PublicationAuthor.author_id == scientist.id)
        .order_by(Publication.year.desc())
        .limit(max_pubs)
        .all()
    )

    if not publications:
        logger.debug(f"No publications found for {scientist.name}")
        return None

    logger.info(f"Checking {len(publications)} publications for {scientist.name}")

    # Extract lastname and initial from scientist name
    lastname, initial = extract_lastname_and_initial(scientist.name)
    if not lastname or not initial:
        logger.warning(f"Could not extract lastname/initial from {scientist.name}")
        return None

    # Try each publication
    for pub in publications:
        if not pub.title:
            continue

        logger.debug(f"  Querying Crossref for: {pub.title[:50]}...")

        try:
            # Get authors from Crossref
            crossref_authors = crossref_client.get_paper_authors(pub.title)

            if not crossref_authors:
                logger.debug(f"    No authors found on Crossref")
                continue

            logger.debug(f"    Found {len(crossref_authors)} authors on Crossref")

            # Try to match scientist by lastname + initial
            full_name = crossref_client.match_author_by_initial(
                scientist.name,
                crossref_authors
            )

            if full_name:
                # Found a match!
                return full_name

        except Exception as e:
            logger.warning(f"    Error querying Crossref: {e}")
            continue

    logger.debug(f"No match found for {scientist.name} across {len(publications)} publications")
    return None


def enrich_scientists_with_crossref(
    db,
    mailto: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None
):
    """
    Enrich scientists with full names from Crossref.

    Args:
        db: Database session.
        mailto: Email for Crossref polite pool (recommended).
        dry_run: If True, only preview changes without updating database.
        limit: Maximum number of scientists to process (None = all).
    """
    logger.info("=" * 80)
    logger.info("🔍 Enriching author names with Crossref API")
    logger.info("=" * 80)

    # Initialize Crossref client
    crossref_client = CrossrefClient(mailto=mailto)
    logger.info(f"Crossref client initialized (mailto={mailto or 'not set'})")

    # Find scientists with initial-only first names
    all_scientists = db.query(Scientist).all()
    logger.info(f"Total scientists in database: {len(all_scientists)}")

    candidates = [
        s for s in all_scientists
        if has_initial_only_firstname(s.name)
    ]

    logger.info(f"Found {len(candidates)} scientists with initial-only first names")

    if limit:
        candidates = candidates[:limit]
        logger.info(f"Processing only {limit} scientists (--limit flag)")

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be saved to database")

    # Process each candidate
    enriched_count = 0
    failed_count = 0

    for i, scientist in enumerate(candidates, 1):
        logger.info(f"\n[{i}/{len(candidates)}] Processing: {scientist.name} (ID={scientist.id})")

        # Try to find full name
        full_name = find_full_name_from_publications(
            scientist,
            db,
            crossref_client,
            max_pubs=5
        )

        if full_name:
            logger.info(f"✨ SUCCESS: '{scientist.name}' → '{full_name}'")

            if not dry_run:
                # Update database
                old_name = scientist.name
                scientist.name = full_name
                db.flush()
                logger.info(f"  ✅ Updated in database: {old_name} → {full_name}")
                enriched_count += 1
            else:
                logger.info(f"  [DRY RUN] Would update: {scientist.name} → {full_name}")
                enriched_count += 1
        else:
            logger.info(f"❌ No match found for {scientist.name}")
            failed_count += 1

        # Commit every 10 scientists to avoid losing progress
        if not dry_run and i % 10 == 0:
            db.commit()
            logger.info(f"  💾 Committed {i} processed scientists")

    # Final commit
    if not dry_run:
        db.commit()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 ENRICHMENT SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total candidates processed: {len(candidates)}")
    logger.info(f"Successfully enriched: {enriched_count}")
    logger.info(f"No match found: {failed_count}")
    logger.info(f"Success rate: {enriched_count / len(candidates) * 100:.1f}%")

    if dry_run:
        logger.info("\n🔍 This was a DRY RUN - no changes were saved to database")
        logger.info("Run without --dry-run to apply changes")


def main():
    """Run the enrichment script."""
    parser = argparse.ArgumentParser(
        description="Enrich author names using Crossref API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enrich all scientists (with polite pool access)
  python src/database/enrich_with_crossref.py --mailto research@example.com

  # Preview changes only (dry run)
  python src/database/enrich_with_crossref.py --dry-run

  # Process only 10 scientists for testing
  python src/database/enrich_with_crossref.py --limit 10 --dry-run
        """
    )

    parser.add_argument(
        "--mailto",
        type=str,
        help="Email for Crossref polite pool (recommended for better rate limits)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating database"
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of scientists to process (for testing)"
    )

    args = parser.parse_args()

    # Open database session
    db = SessionLocal()

    try:
        enrich_scientists_with_crossref(
            db,
            mailto=args.mailto,
            dry_run=args.dry_run,
            limit=args.limit
        )

        logger.info("\n" + "=" * 80)
        logger.info("✅ ENRICHMENT COMPLETE!")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        db.rollback()
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Enrichment failed: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
