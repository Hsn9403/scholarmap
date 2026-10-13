#!/usr/bin/env python3
"""
Merge all duplicates in the database (scientists and publications).

Fixed version that handles cascade deletes properly.
"""
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist, Publication, PublicationAuthor, PatentInventor,
    ScientistInstitution, APICall
)
from src.logger import logger


def normalize_text(text: str) -> str:
    """Normalize text for grouping (lowercase, no extra spaces)."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def merge_scientist_duplicates(db):
    """Merge all scientist duplicates."""
    logger.info("=" * 80)
    logger.info("👨‍🔬 MERGING SCIENTIST DUPLICATES")
    logger.info("=" * 80)

    # Get all scientists
    all_scientists = db.query(Scientist).all()
    logger.info(f"Total scientists before merge: {len(all_scientists)}")

    # Group by normalized name
    name_groups = defaultdict(list)
    for scientist in all_scientists:
        norm_name = normalize_text(scientist.name)
        name_groups[norm_name].append(scientist)

    # Find and merge duplicates
    duplicates_count = 0
    merged_count = 0

    for norm_name, scientists in name_groups.items():
        if len(scientists) <= 1:
            continue

        duplicates_count += len(scientists)
        logger.info(f"\nFound {len(scientists)} duplicates for: {scientists[0].name}")

        # Choose best one to keep (prefer one with scholar_id, then most complete data)
        best = max(scientists, key=lambda s: (
            bool(s.scholar_id),  # Has scholar_id
            bool(s.h_index),  # Has h_index
            bool(s.scholar_url),  # Has scholar_url
            bool(s.affiliation),  # Has affiliation
            -s.id  # Prefer lower ID (older entry) - note the negative
        ))

        logger.info(f"  Keeping ID {best.id}: {best.name} (scholar_id: {best.scholar_id})")

        # Merge data from all others into best
        for scientist in scientists:
            if scientist.id == best.id:
                continue

            logger.info(f"  Merging ID {scientist.id} into ID {best.id}")

            # Copy missing data from duplicate to best
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

            # Refresh the session to avoid stale data
            db.expire_all()

            # Move publication links (handle duplicates)
            pub_links = db.query(PublicationAuthor).filter_by(author_id=scientist.id).all()
            moved_pubs = 0
            for link in pub_links:
                # Check if link already exists for best scientist
                existing = db.query(PublicationAuthor).filter_by(
                    publication_id=link.publication_id,
                    author_id=best.id
                ).first()

                if not existing:
                    link.author_id = best.id
                    moved_pubs += 1
                else:
                    db.delete(link)

            if moved_pubs > 0:
                logger.info(f"    → Moved {moved_pubs} publication links")
            db.flush()

            # Move patent links (handle duplicates)
            patent_links = db.query(PatentInventor).filter_by(scientist_id=scientist.id).all()
            moved_patents = 0
            for link in patent_links:
                existing = db.query(PatentInventor).filter_by(
                    patent_id=link.patent_id,
                    scientist_id=best.id
                ).first()

                if not existing:
                    link.scientist_id = best.id
                    moved_patents += 1
                else:
                    db.delete(link)

            if moved_patents > 0:
                logger.info(f"    → Moved {moved_patents} patent links")
            db.flush()

            # Move institution links (handle duplicates)
            inst_links = db.query(ScientistInstitution).filter_by(scientist_id=scientist.id).all()
            moved_insts = 0
            for link in inst_links:
                existing = db.query(ScientistInstitution).filter_by(
                    scientist_id=best.id,
                    institution_id=link.institution_id
                ).first()

                if not existing:
                    link.scientist_id = best.id
                    moved_insts += 1
                else:
                    db.delete(link)

            if moved_insts > 0:
                logger.info(f"    → Moved {moved_insts} institution links")
            db.flush()

            # Move API call links
            api_calls = db.query(APICall).filter_by(scientist_id=scientist.id).all()
            if api_calls:
                for api_call in api_calls:
                    api_call.scientist_id = best.id
                logger.info(f"    → Moved {len(api_calls)} API call links")
                db.flush()

            # Delete the duplicate
            db.delete(scientist)
            merged_count += 1

        # Commit after each group
        db.commit()
        logger.info(f"  ✓ Merged {len(scientists) - 1} duplicates")

    logger.info(f"\n✅ Successfully merged {merged_count} scientist duplicates")
    logger.info(f"Total scientists after merge: {db.query(Scientist).count()}")


def merge_publication_duplicates(db):
    """Merge all publication duplicates."""
    logger.info("\n" + "=" * 80)
    logger.info("📚 MERGING PUBLICATION DUPLICATES")
    logger.info("=" * 80)

    # Get all publications
    all_publications = db.query(Publication).all()
    logger.info(f"Total publications before merge: {len(all_publications)}")

    # Group by normalized title
    title_groups = defaultdict(list)
    for pub in all_publications:
        if pub.title:
            norm_title = normalize_text(pub.title)
            title_groups[norm_title].append(pub)

    # Find and merge duplicates
    duplicates_count = 0
    merged_count = 0

    for norm_title, publications in title_groups.items():
        if len(publications) <= 1:
            continue

        duplicates_count += len(publications)
        title_display = publications[0].title[:60] + "..." if len(publications[0].title) > 60 else publications[0].title
        logger.info(f"\nFound {len(publications)} duplicates for: {title_display}")

        # Choose best one to keep (prefer one with most data)
        best = max(publications, key=lambda p: (
            bool(p.source_id),  # Has source_id
            p.cited_by or 0,  # Higher citations
            bool(p.year),  # Has year
            bool(p.link),  # Has link
            bool(p.abstract),  # Has abstract
            -p.id  # Prefer lower ID (older entry)
        ))

        logger.info(f"  Keeping ID {best.id}: cited_by={best.cited_by}, year={best.year}")

        # Merge data from all others into best
        for pub in publications:
            if pub.id == best.id:
                continue

            logger.info(f"  Merging ID {pub.id} into ID {best.id}")

            # Copy missing/better data
            if pub.cited_by and (not best.cited_by or pub.cited_by > best.cited_by):
                best.cited_by = pub.cited_by
                logger.info(f"    → Updated cited_by: {pub.cited_by}")

            if pub.source_id and not best.source_id:
                best.source_id = pub.source_id
                logger.info(f"    → Copied source_id")

            if pub.link and not best.link:
                best.link = pub.link
                logger.info(f"    → Copied link")

            if pub.abstract and not best.abstract:
                best.abstract = pub.abstract
                logger.info(f"    → Copied abstract")

            if pub.year and not best.year:
                best.year = pub.year
                logger.info(f"    → Copied year")

            # Refresh the session
            db.expire_all()

            # Move author links (handle duplicates)
            author_links = db.query(PublicationAuthor).filter_by(publication_id=pub.id).all()
            moved_authors = 0
            for link in author_links:
                existing = db.query(PublicationAuthor).filter_by(
                    publication_id=best.id,
                    author_id=link.author_id
                ).first()

                if not existing:
                    link.publication_id = best.id
                    moved_authors += 1
                else:
                    db.delete(link)

            if moved_authors > 0:
                logger.info(f"    → Moved {moved_authors} author links")
            db.flush()

            # Delete the duplicate
            db.delete(pub)
            merged_count += 1

        # Commit after each group
        db.commit()
        logger.info(f"  ✓ Merged {len(publications) - 1} duplicates")

    logger.info(f"\n✅ Successfully merged {merged_count} publication duplicates")
    logger.info(f"Total publications after merge: {db.query(Publication).count()}")


def main():
    """Run all deduplication."""
    db = SessionLocal()

    try:
        logger.info("🚀 STARTING DEDUPLICATION PROCESS")
        logger.info("=" * 80)

        # Merge scientists first
        merge_scientist_duplicates(db)

        # Then merge publications
        merge_publication_duplicates(db)

        logger.info("\n" + "=" * 80)
        logger.info("✅ DEDUPLICATION COMPLETE!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Failed to merge duplicates: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
