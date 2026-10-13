#!/usr/bin/env python3
"""
Merge duplicate scientists with and without Scholar IDs.

Finds scientists that appear twice: once with Scholar ID (from searches)
and once without Scholar ID (from publications). Merges them intelligently.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist,
    PublicationAuthor,
    PatentInventor,
    ScientistInstitution,
)
from src.logger import logger


def normalize_name_for_matching(name: str) -> str:
    """Normalize name for matching."""
    import unicodedata
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    return name.lower().strip().replace('.', '').replace(',', '').replace('-', ' ')


def names_match(name1: str, name2: str) -> bool:
    """Check if two names match (handles initials vs full names)."""
    n1 = normalize_name_for_matching(name1)
    n2 = normalize_name_for_matching(name2)

    # Exact match
    if n1 == n2:
        return True

    parts1 = n1.split()
    parts2 = n2.split()

    # Must have at least a last name
    if not parts1 or not parts2:
        return False

    # Compare last names
    if parts1[-1] != parts2[-1]:
        return False

    # If one has initials and other has full name, check if they match
    # e.g., "B Calvignac" vs "Brice Calvignac"
    if len(parts1) == len(parts2):
        for p1, p2 in zip(parts1[:-1], parts2[:-1]):
            # Check if one is initial of the other
            if len(p1) == 1 and p2.startswith(p1):
                continue
            if len(p2) == 1 and p1.startswith(p2):
                continue
            if p1 != p2:
                return False
        return True

    return False


def merge_scientists(db, keep_id: int, remove_id: int):
    """Merge two scientist records, keeping the one with Scholar ID."""
    from sqlalchemy import text

    keep = db.query(Scientist).get(keep_id)
    remove = db.query(Scientist).get(remove_id)

    logger.info(f"Merging: '{remove.name}' (ID: {remove.id}, pubs) → '{keep.name}' (ID: {keep.id}, Scholar: {keep.scholar_id})")

    # Move publications using raw SQL
    db.execute(text("""
        UPDATE publications_author
        SET author_id = :keep_id
        WHERE author_id = :remove_id
        AND publication_id NOT IN (
            SELECT publication_id FROM publications_author WHERE author_id = :keep_id
        )
    """), {"keep_id": keep_id, "remove_id": remove_id})

    # Delete remaining duplicates
    db.execute(text("""
        DELETE FROM publications_author WHERE author_id = :remove_id
    """), {"remove_id": remove_id})

    # Move patents
    db.execute(text("""
        UPDATE patents_inventor
        SET scientist_id = :keep_id
        WHERE scientist_id = :remove_id
        AND patent_id NOT IN (
            SELECT patent_id FROM patents_inventor WHERE scientist_id = :keep_id
        )
    """), {"keep_id": keep_id, "remove_id": remove_id})

    db.execute(text("""
        DELETE FROM patents_inventor WHERE scientist_id = :remove_id
    """), {"remove_id": remove_id})

    # Move institutions
    db.execute(text("""
        UPDATE scientist_institution
        SET scientist_id = :keep_id
        WHERE scientist_id = :remove_id
        AND institution_id NOT IN (
            SELECT institution_id FROM scientist_institution WHERE scientist_id = :keep_id
        )
    """), {"keep_id": keep_id, "remove_id": remove_id})

    db.execute(text("""
        DELETE FROM scientist_institution WHERE scientist_id = :remove_id
    """), {"remove_id": remove_id})

    # Move API calls (set to keep_id if remove_id)
    db.execute(text("""
        UPDATE api_calls
        SET scientist_id = :keep_id
        WHERE scientist_id = :remove_id
    """), {"keep_id": keep_id, "remove_id": remove_id})

    # Update affiliation if target doesn't have one
    if remove.affiliation and not keep.affiliation:
        keep.affiliation = remove.affiliation

    # Delete the duplicate
    db.execute(text("""
        DELETE FROM scientists WHERE id = :remove_id
    """), {"remove_id": remove_id})

    db.commit()


def merge_duplicates(db) -> dict:
    """Find and merge duplicate scientists."""
    stats = {
        "duplicates_found": 0,
        "scientists_merged": 0,
        "publications_moved": 0,
    }

    # Get all scientists
    scientists = db.query(Scientist).all()

    # Group by last name for efficiency
    from collections import defaultdict
    by_lastname = defaultdict(list)

    for s in scientists:
        parts = normalize_name_for_matching(s.name).split()
        if parts:
            lastname = parts[-1]
            by_lastname[lastname].append(s)

    # Find duplicates in each group
    for lastname, group in by_lastname.items():
        if len(group) < 2:
            continue

        # Store IDs and names to avoid deleted object errors
        with_scholar = [(s.id, s.name, s.scholar_id) for s in group if s.scholar_id]
        without_scholar = [(s.id, s.name, len(s.publications)) for s in group if not s.scholar_id and len(s.publications) > 0]

        for with_id, with_name, with_scholar_id in with_scholar:
            for without_id, without_name, pubs_count in without_scholar:
                # Check if still exists (may have been merged already)
                if not db.query(Scientist).filter_by(id=without_id).first():
                    continue

                # Check if names match
                if names_match(with_name, without_name):
                    stats["duplicates_found"] += 1
                    stats["publications_moved"] += pubs_count

                    # Merge: keep the one with Scholar ID
                    merge_scientists(db, keep_id=with_id, remove_id=without_id)
                    stats["scientists_merged"] += 1

    return stats


def main():
    """Main entry point."""
    db = SessionLocal()

    try:
        logger.info("Starting duplicate scientist merge...")
        stats = merge_duplicates(db)

        logger.info("\n📊 Merge Statistics:")
        logger.info(f"   Duplicates found: {stats['duplicates_found']}")
        logger.info(f"   Scientists merged: {stats['scientists_merged']}")
        logger.info(f"   Publications moved: {stats['publications_moved']}")

        logger.info("\n✅ Duplicate merge completed")

    except Exception as e:
        logger.error(f"Failed to merge duplicates: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
