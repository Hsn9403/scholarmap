#!/usr/bin/env python3
"""
Split multiple assignees (e.g., "Inside Therapeutics, Elvesys") into separate corporates.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Corporate, Patent, PatentCorporate
from src.logger import logger


def normalize_name(name: str) -> str:
    """Normalize corporate name for matching."""
    return " ".join(name.lower().strip().split())


def split_multiple_assignees():
    """Split assignees containing commas into separate corporate entities."""
    db = SessionLocal()

    stats = {
        'corporates_split': 0,
        'new_corporates_created': 0,
        'links_updated': 0,
    }

    try:
        # Find all corporates with comma in name
        all_corporates = db.query(Corporate).all()

        for corporate in all_corporates:
            if ',' not in corporate.name:
                continue

            logger.info(f"Splitting: {corporate.name}")
            stats['corporates_split'] += 1

            # Split by comma
            parts = [part.strip() for part in corporate.name.split(',') if part.strip()]

            # Find all patents linked to this corporate
            patent_links = db.query(PatentCorporate).filter_by(
                corporate_id=corporate.id
            ).all()

            logger.info(f"  Found {len(parts)} parts: {parts}")
            logger.info(f"  Linked to {len(patent_links)} patents")

            # For each part, find or create separate corporate
            new_corporates = []
            for part in parts:
                normalized = normalize_name(part)

                # Find or create corporate for this part
                existing = db.query(Corporate).filter_by(
                    normalized_name=normalized
                ).first()

                if existing:
                    logger.info(f"    Found existing corporate: {existing.name}")
                    new_corporates.append(existing)
                else:
                    new_corporate = Corporate(
                        name=part,
                        normalized_name=normalized,
                    )
                    db.add(new_corporate)
                    db.flush()
                    new_corporates.append(new_corporate)
                    stats['new_corporates_created'] += 1
                    logger.info(f"    Created new corporate: {part}")

            # Link patents to new separate corporates
            for link in patent_links:
                for new_corp in new_corporates:
                    # Check if link already exists
                    existing_link = db.query(PatentCorporate).filter_by(
                        patent_id=link.patent_id,
                        corporate_id=new_corp.id,
                        role=link.role
                    ).first()

                    if not existing_link:
                        new_link = PatentCorporate(
                            patent_id=link.patent_id,
                            corporate_id=new_corp.id,
                            role=link.role
                        )
                        db.add(new_link)
                        stats['links_updated'] += 1
                        logger.info(f"    Linked patent to {new_corp.name}")

                # Delete old link
                db.delete(link)

            # Delete old corporate with comma
            db.delete(corporate)
            logger.info(f"  ✓ Deleted composite corporate: {corporate.name}")

        db.commit()

        logger.info("\n📊 Statistics:")
        logger.info(f"   Corporates split: {stats['corporates_split']}")
        logger.info(f"   New corporates created: {stats['new_corporates_created']}")
        logger.info(f"   Patent links updated: {stats['links_updated']}")
        logger.info("\n✅ Assignee splitting completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    split_multiple_assignees()
