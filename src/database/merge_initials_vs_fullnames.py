#!/usr/bin/env python3
"""
Merge scientists with initials vs full names.

Detects cases like:
- "P Sharan" vs "Priyanka Sharan"
- "C Dancette" vs "Corentin Dancette"

Always keeps the one with the most data (Scholar ID, h-index, etc.)
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
    """Normalize name for comparison (lowercase, no extra spaces)."""
    return " ".join(name.lower().split())


def extract_initials_and_lastname(name: str) -> tuple:
    """
    Extract initials and last name from a name.

    Returns:
        (initials_set, lastname)

    Examples:
        "P Sharan" -> ({'p'}, 'sharan')
        "Priyanka Sharan" -> ({'p'}, 'sharan')
        "C Dancette" -> ({'c'}, 'dancette')
    """
    parts = normalize_name(name).split()
    if len(parts) < 2:
        return (set(), "")

    lastname = parts[-1]

    # Extract initials from first names
    initials = set()
    for part in parts[:-1]:  # All parts except last name
        if len(part) == 1:
            # Already an initial
            initials.add(part)
        else:
            # Full name - take first letter
            initials.add(part[0])

    return (initials, lastname)


def is_initial_variant(name1: str, name2: str) -> bool:
    """
    Check if two names are variants (initial vs full name).

    Rules:
    - Same last name (exact match)
    - One has initial(s), other has full first name(s)
    - Initials must match

    Examples:
        "P Sharan" and "Priyanka Sharan" -> True
        "C Dancette" and "Corentin Dancette" -> True
        "P Sharan" and "Prashant Sharan" -> True (both start with P)
        "P Sharan" and "K Sharan" -> False (different initials)
    """
    initials1, lastname1 = extract_initials_and_lastname(name1)
    initials2, lastname2 = extract_initials_and_lastname(name2)

    # Must have same last name
    if lastname1 != lastname2:
        return False

    # Check if initials match
    if initials1 & initials2:  # At least one initial in common
        return True

    return False


def score_scientist(scientist: Scientist) -> int:
    """
    Score a scientist to determine which one has more data.

    Higher score = more complete data = this is the one to keep.
    """
    score = 0

    # Priority 1: Has Scholar ID (most important - unique identifier)
    if scientist.scholar_id:
        score += 100000

    # Priority 2: Has h-index
    if scientist.h_index is not None:
        score += 10000
        score += scientist.h_index  # Bonus for higher h-index

    # Priority 3: Has Scholar URL
    if scientist.scholar_url:
        score += 1000

    # Priority 4: Has affiliation
    if scientist.affiliation:
        score += 500

    # Priority 5: Longer name (more complete)
    score += len(scientist.name) * 10

    # Priority 6: First name is not just an initial
    parts = scientist.name.split()
    if parts and len(parts[0]) > 1:
        score += 100

    return score


def merge_scientist_duplicates(db):
    """Merge scientists with initials vs full names."""
    logger.info("=" * 80)
    logger.info("🔍 Detecting initial vs full name duplicates")
    logger.info("=" * 80)

    # Get all scientists
    all_scientists = db.query(Scientist).all()
    logger.info(f"Total scientists: {len(all_scientists)}")

    # Group by last name for faster comparison
    by_lastname = defaultdict(list)
    for s in all_scientists:
        _, lastname = extract_initials_and_lastname(s.name)
        if lastname:
            by_lastname[lastname].append(s)

    # Find duplicates
    merged_count = 0

    for lastname, scientists in by_lastname.items():
        if len(scientists) < 2:
            continue

        # Find clusters of variants
        processed = set()

        for i, s1 in enumerate(scientists):
            if s1.id in processed:
                continue

            cluster = [s1]
            processed.add(s1.id)

            # Find all variants of s1
            for s2 in scientists[i+1:]:
                if s2.id in processed:
                    continue

                if is_initial_variant(s1.name, s2.name):
                    cluster.append(s2)
                    processed.add(s2.id)

            if len(cluster) <= 1:
                continue

            # Found duplicates - choose best one to keep
            cluster.sort(key=score_scientist, reverse=True)
            best = cluster[0]
            to_merge = cluster[1:]

            logger.info(f"\n📦 Found {len(cluster)} variants:")
            for s in cluster:
                marker = "✅ KEEP" if s.id == best.id else "❌ MERGE"
                logger.info(
                    f"  {marker} | ID={s.id:4d} | {s.name:30s} | "
                    f"Scholar={s.scholar_id or 'N/A':15s} | h={s.h_index or 'N/A'}"
                )

            # Merge each duplicate into best
            for scientist in to_merge:
                logger.info(f"\n  Merging ID {scientist.id} ({scientist.name}) into ID {best.id} ({best.name})")

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

                # Refresh session
                db.expire_all()

                # Move publication links
                pub_links = db.query(PublicationAuthor).filter_by(author_id=scientist.id).all()
                moved_pubs = 0
                for link in pub_links:
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

                # Move patent links
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

                # Move institution links
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

                # Move API calls
                api_calls = db.query(APICall).filter_by(scientist_id=scientist.id).all()
                if api_calls:
                    for api_call in api_calls:
                        api_call.scientist_id = best.id
                    logger.info(f"    → Moved {len(api_calls)} API call links")
                    db.flush()

                # Delete the duplicate
                db.delete(scientist)
                merged_count += 1

            # Commit after each cluster
            db.commit()
            logger.info(f"  ✅ Merged {len(to_merge)} duplicates into {best.name}")

    logger.info(f"\n✅ Successfully merged {merged_count} scientists")
    logger.info(f"Total scientists after merge: {db.query(Scientist).count()}")


def main():
    """Run the merge."""
    db = SessionLocal()

    try:
        merge_scientist_duplicates(db)

        logger.info("\n" + "=" * 80)
        logger.info("✅ MERGE COMPLETE!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Merge failed: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
