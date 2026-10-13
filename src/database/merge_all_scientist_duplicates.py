#!/usr/bin/env python3
"""
Merge all scientist duplicates by combining their data.

For each group of scientists with the same name:
- Keep the one with the most complete data (scholar_id preferred)
- Merge h_index, scholar_url, affiliation from all duplicates
- Move all publication/patent/institution links to the kept one
- Delete duplicates
"""
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist, PublicationAuthor, PatentInventor, ScientistInstitution, APICall
)
from src.logger import logger


def normalize_name(name: str) -> str:
    """Normalize name for grouping (lowercase, no extra spaces)."""
    return " ".join(name.lower().split())


def merge_scientist_duplicates():
    """Merge all scientist duplicates."""
    db = SessionLocal()

    try:
        # Get all scientists
        all_scientists = db.query(Scientist).all()

        # Group by normalized name
        name_groups = defaultdict(list)
        for scientist in all_scientists:
            norm_name = normalize_name(scientist.name)
            name_groups[norm_name].append(scientist)

        # Find duplicates
        duplicates_count = 0
        merged_count = 0

        for norm_name, scientists in name_groups.items():
            if len(scientists) <= 1:
                continue

            duplicates_count += len(scientists) - 1
            logger.info(f"Found {len(scientists)} duplicates for: {scientists[0].name}")

            # Choose best one to keep (prefer one with scholar_id, then most complete data)
            best = max(scientists, key=lambda s: (
                bool(s.scholar_id),  # Has scholar_id
                bool(s.h_index),  # Has h_index
                bool(s.scholar_url),  # Has scholar_url
                bool(s.affiliation),  # Has affiliation
                s.id  # Tie-breaker: lower ID (older entry)
            ))

            logger.info(f"  Keeping ID {best.id} (scholar_id: {best.scholar_id}, h_index: {best.h_index})")

            # Merge data from all others into best
            for scientist in scientists:
                if scientist.id == best.id:
                    continue

                logger.info(f"  Merging ID {scientist.id} into ID {best.id}")

                # Copy missing data
                if scientist.h_index and not best.h_index:
                    best.h_index = scientist.h_index
                    logger.info(f"    → Copied h_index: {scientist.h_index}")

                if scientist.scholar_id and not best.scholar_id:
                    best.scholar_id = scientist.scholar_id
                    logger.info(f"    → Copied scholar_id: {scientist.scholar_id}")

                if scientist.scholar_url and not best.scholar_url:
                    best.scholar_url = scientist.scholar_url
                    logger.info(f"    → Copied scholar_url")

                if scientist.affiliation and not best.affiliation:
                    best.affiliation = scientist.affiliation
                    logger.info(f"    → Copied affiliation")

                # Move publication links
                pub_links = db.query(PublicationAuthor).filter_by(author_id=scientist.id).all()
                for link in pub_links:
                    existing = db.query(PublicationAuthor).filter_by(
                        publication_id=link.publication_id,
                        author_id=best.id
                    ).first()
                    if not existing:
                        link.author_id = best.id
                    else:
                        db.delete(link)
                if pub_links:
                    logger.info(f"    → Moved {len(pub_links)} publication links")

                # Move patent links
                patent_links = db.query(PatentInventor).filter_by(scientist_id=scientist.id).all()
                for link in patent_links:
                    existing = db.query(PatentInventor).filter_by(
                        patent_id=link.patent_id,
                        scientist_id=best.id
                    ).first()
                    if not existing:
                        link.scientist_id = best.id
                    else:
                        db.delete(link)
                if patent_links:
                    logger.info(f"    → Moved {len(patent_links)} patent links")

                # Move institution links
                inst_links = db.query(ScientistInstitution).filter_by(scientist_id=scientist.id).all()
                for link in inst_links:
                    existing = db.query(ScientistInstitution).filter_by(
                        scientist_id=best.id,
                        institution_id=link.institution_id
                    ).first()
                    if not existing:
                        link.scientist_id = best.id
                    else:
                        db.delete(link)
                if inst_links:
                    logger.info(f"    → Moved {len(inst_links)} institution links")

                # Move API call links
                api_calls = db.query(APICall).filter_by(scientist_id=scientist.id).all()
                for api_call in api_calls:
                    api_call.scientist_id = best.id
                if api_calls:
                    logger.info(f"    → Moved {len(api_calls)} API call links")

                # Delete the duplicate
                db.delete(scientist)
                merged_count += 1

            # Commit after each group
            db.commit()
            logger.info(f"  ✓ Merged {len(scientists) - 1} duplicates")

        logger.info(f"\n✅ Successfully merged {merged_count} duplicates")
        logger.info(f"Total duplicate groups processed: {duplicates_count}")

    except Exception as e:
        logger.error(f"Failed to merge duplicates: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    merge_scientist_duplicates()
