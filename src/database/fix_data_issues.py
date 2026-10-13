#!/usr/bin/env python3
"""
Fix data issues:
1. Merge AN Mercier / A Nedelec Mercier with Alice Nedelec
2. Re-parse publications to extract year from publication_info.summary
"""
import json
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist, Publication, PublicationAuthor, PatentInventor,
    ScientistInstitution, APICall
)
from src.logger import logger


def extract_year_from_summary(summary: str) -> int | None:
    """
    Extract year from publication_info.summary string.

    Format: "Authors - Journal, YEAR - Publisher"
    Example: "P Sharan, A Nedelec - Small, 2021 - Wiley Online Library"
    """
    if not summary:
        return None

    # Look for 4-digit year (1900-2099)
    match = re.search(r'\b(19\d{2}|20\d{2})\b', summary)
    if match:
        return int(match.group(1))

    return None


def merge_an_mercier_with_alice():
    """Merge AN Mercier / A Nedelec Mercier with Alice Nedelec."""
    db = SessionLocal()

    try:
        # Find Alice Nedelec (the one to keep)
        alice = db.query(Scientist).filter(
            Scientist.name == "Alice Nedelec"
        ).first()

        if not alice:
            logger.error("Alice Nedelec not found in database!")
            return

        logger.info(f"Keeping Alice Nedelec (ID: {alice.id})")

        # Find duplicates
        duplicates = db.query(Scientist).filter(
            Scientist.name.in_(["AN Mercier", "A Nedelec Mercier"])
        ).all()

        if not duplicates:
            logger.info("No duplicates found for AN Mercier")
            return

        logger.info(f"Found {len(duplicates)} duplicate(s) to merge")

        for dup in duplicates:
            logger.info(f"Merging {dup.name} (ID: {dup.id}) into Alice Nedelec")

            # Move publication links
            pub_links = db.query(PublicationAuthor).filter_by(author_id=dup.id).all()
            for link in pub_links:
                # Check if link already exists
                existing = db.query(PublicationAuthor).filter_by(
                    publication_id=link.publication_id,
                    author_id=alice.id
                ).first()
                if not existing:
                    link.author_id = alice.id
                else:
                    db.delete(link)
            if pub_links:
                logger.info(f"  → Moved {len(pub_links)} publication links")

            # Move patent links
            patent_links = db.query(PatentInventor).filter_by(scientist_id=dup.id).all()
            for link in patent_links:
                existing = db.query(PatentInventor).filter_by(
                    patent_id=link.patent_id,
                    scientist_id=alice.id
                ).first()
                if not existing:
                    link.scientist_id = alice.id
                else:
                    db.delete(link)
            if patent_links:
                logger.info(f"  → Moved {len(patent_links)} patent links")

            # Move institution links
            inst_links = db.query(ScientistInstitution).filter_by(scientist_id=dup.id).all()
            for link in inst_links:
                existing = db.query(ScientistInstitution).filter_by(
                    scientist_id=alice.id,
                    institution_id=link.institution_id
                ).first()
                if not existing:
                    link.scientist_id = alice.id
                else:
                    db.delete(link)
            if inst_links:
                logger.info(f"  → Moved {len(inst_links)} institution links")

            # Move API call links
            api_calls = db.query(APICall).filter_by(scientist_id=dup.id).all()
            for api_call in api_calls:
                api_call.scientist_id = alice.id
            if api_calls:
                logger.info(f"  → Moved {len(api_calls)} API call links")

            # Delete duplicate
            db.delete(dup)
            logger.info(f"  ✓ Deleted {dup.name}")

        db.commit()
        logger.info("✅ Successfully merged AN Mercier duplicates")

    except Exception as e:
        logger.error(f"Failed to merge: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def fix_publication_years():
    """Re-parse publications from cassettes to extract year from publication_info.summary."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"
    db = SessionLocal()

    stats = {
        'cassettes_processed': 0,
        'publications_updated': 0,
        'years_extracted': 0,
    }

    try:
        logger.info("Extracting publication years from cassettes...")

        for cassette_file in cassettes_dir.glob('*.json'):
            try:
                with open(cassette_file, 'r') as f:
                    data = json.load(f)

                # Only process Scholar publication searches
                if data.get('request', {}).get('engine') != 'google_scholar':
                    continue

                stats['cassettes_processed'] += 1

                results = data.get('response', {}).get('organic_results', [])

                for result in results:
                    title = result.get('title')
                    if not title:
                        continue

                    # Find publication in database (case-insensitive)
                    # Try exact match first, then partial match
                    pub = db.query(Publication).filter(
                        Publication.title.ilike(title)
                    ).first()

                    if not pub:
                        # Try partial match (first 50 chars)
                        title_prefix = title[:50]
                        pub = db.query(Publication).filter(
                            Publication.title.ilike(f"{title_prefix}%")
                        ).first()

                    if not pub:
                        continue

                    # If publication already has a year, skip
                    if pub.year:
                        continue

                    # Extract year from publication_info.summary
                    pub_info = result.get('publication_info', {})
                    summary = pub_info.get('summary', '')

                    year = extract_year_from_summary(summary)

                    if year:
                        pub.year = year
                        stats['publications_updated'] += 1
                        stats['years_extracted'] += 1
                        logger.info(f"✓ Updated '{title[:60]}...' with year {year}")

            except Exception as e:
                logger.error(f"Error processing {cassette_file.name}: {e}")
                continue

        db.commit()

        logger.info("\n📊 Statistics:")
        logger.info(f"   Cassettes processed: {stats['cassettes_processed']}")
        logger.info(f"   Publications updated: {stats['publications_updated']}")
        logger.info(f"   Years extracted: {stats['years_extracted']}")
        logger.info("\n✅ Publication year extraction completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    logger.info("Starting data fixes...")

    # 1. Merge AN Mercier with Alice Nedelec
    logger.info("\n1. Merging AN Mercier with Alice Nedelec...")
    merge_an_mercier_with_alice()

    # 2. Fix publication years
    logger.info("\n2. Extracting publication years from cassettes...")
    fix_publication_years()

    logger.info("\n✅ All fixes completed")
