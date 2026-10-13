#!/usr/bin/env python3
"""
Merge duplicate publications (same title, different case).
"""
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Publication, PublicationAuthor
from src.logger import logger


def normalize_title(title: str) -> str:
    """Normalize title for matching (lowercase, no extra spaces)."""
    return " ".join(title.lower().strip().split())


def merge_duplicate_publications():
    """Merge duplicate publications with same title."""
    db = SessionLocal()

    stats = {
        'duplicates_found': 0,
        'publications_merged': 0,
    }

    try:
        # Get all publications
        all_pubs = db.query(Publication).all()

        # Group by normalized title
        title_groups = defaultdict(list)
        for pub in all_pubs:
            norm_title = normalize_title(pub.title)
            title_groups[norm_title].append(pub)

        # Find and merge duplicates
        for norm_title, pubs in title_groups.items():
            if len(pubs) <= 1:
                continue

            logger.info(f"\nFound {len(pubs)} duplicates:")
            for p in pubs:
                logger.info(f"  ID {p.id}: {p.title[:60]}... (year:{p.year}, cited:{p.cited_by})")

            stats['duplicates_found'] += len(pubs) - 1

            # Choose best one to keep (prefer one with most complete data)
            best = max(pubs, key=lambda p: (
                bool(p.year),  # Has year
                bool(p.cited_by),  # Has cited_by
                bool(p.source),  # Has source
                bool(p.abstract),  # Has abstract
                -p.id  # Tie-breaker: prefer older (lower ID)
            ))

            logger.info(f"  → Keeping ID {best.id} (year:{best.year}, cited:{best.cited_by})")

            # Merge all others into best
            for pub in pubs:
                if pub.id == best.id:
                    continue

                logger.info(f"  → Merging ID {pub.id} into ID {best.id}")

                # Copy missing data
                if pub.year and not best.year:
                    best.year = pub.year
                if pub.cited_by and not best.cited_by:
                    best.cited_by = pub.cited_by
                if pub.source and not best.source:
                    best.source = pub.source
                if pub.abstract and not best.abstract:
                    best.abstract = pub.abstract
                if pub.link and not best.link:
                    best.link = pub.link

                # Move author links
                author_links = db.query(PublicationAuthor).filter_by(
                    publication_id=pub.id
                ).all()

                for link in author_links:
                    # Check if link already exists
                    existing = db.query(PublicationAuthor).filter_by(
                        publication_id=best.id,
                        author_id=link.author_id
                    ).first()

                    if not existing:
                        link.publication_id = best.id
                    else:
                        db.delete(link)

                # Delete duplicate
                db.delete(pub)
                stats['publications_merged'] += 1

                # Commit after each merge to avoid stale data errors
                try:
                    db.commit()
                except Exception as e:
                    logger.warning(f"  ! Could not merge publication {pub.id}: {e}")
                    db.rollback()
                    continue

            logger.info(f"  ✓ Merged {len(pubs) - 1} duplicates")

        logger.info("\n📊 Statistics:")
        logger.info(f"   Duplicate publications found: {stats['duplicates_found']}")
        logger.info(f"   Publications merged: {stats['publications_merged']}")
        logger.info("\n✅ Publication merge completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    merge_duplicate_publications()
