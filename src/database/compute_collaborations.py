#!/usr/bin/env python3
"""
Compute and store collaborations between scientists.

Analyzes publications_author and patents_inventor to pre-calculate:
- Number of co-authored publications
- Number of co-invented patents
- Temporal information (first/last collaboration year)
"""
import sys
from pathlib import Path
from collections import defaultdict
from itertools import combinations

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist, Publication, Patent, PublicationAuthor, PatentInventor, Collaboration
)
from src.logger import logger


def compute_publication_collaborations(db):
    """Compute collaborations based on co-authored publications."""
    logger.info("📚 Computing publication collaborations...")

    # Get all publications with their authors
    publications = db.query(Publication).all()

    # Track collaborations: (sci1_id, sci2_id) -> {years: set, count: int}
    collaborations = defaultdict(lambda: {"years": set(), "count": 0})

    for pub in publications:
        authors = db.query(PublicationAuthor).filter_by(publication_id=pub.id).all()
        author_ids = [pa.author_id for pa in authors]

        # Create collaboration for each pair of authors
        for id1, id2 in combinations(sorted(author_ids), 2):
            # Always use smaller ID first to avoid duplicates
            key = (min(id1, id2), max(id1, id2))
            collaborations[key]["count"] += 1
            if pub.year:
                collaborations[key]["years"].add(pub.year)

    # Insert into database
    added = 0
    for (sci1_id, sci2_id), data in collaborations.items():
        years = sorted(data["years"]) if data["years"] else []

        # Check if collaboration already exists
        existing = db.query(Collaboration).filter_by(
            scientist1_id=sci1_id,
            scientist2_id=sci2_id,
            collaboration_type='publication'
        ).first()

        if existing:
            # Update existing
            existing.weight = data["count"]
            existing.first_collaboration_year = years[0] if years else None
            existing.last_collaboration_year = years[-1] if years else None
        else:
            # Create new
            collab = Collaboration(
                scientist1_id=sci1_id,
                scientist2_id=sci2_id,
                collaboration_type='publication',
                weight=data["count"],
                first_collaboration_year=years[0] if years else None,
                last_collaboration_year=years[-1] if years else None
            )
            db.add(collab)
            added += 1

    db.commit()
    logger.info(f"✅ Added {added} publication collaborations")
    logger.info(f"   Total pairs: {len(collaborations)}")


def compute_patent_collaborations(db):
    """Compute collaborations based on co-invented patents."""
    logger.info("🔬 Computing patent collaborations...")

    # Get all patents with their inventors
    patents = db.query(Patent).all()

    # Track collaborations
    collaborations = defaultdict(lambda: {"years": set(), "count": 0})

    for patent in patents:
        inventors = db.query(PatentInventor).filter_by(patent_id=patent.id).all()
        inventor_ids = [pi.scientist_id for pi in inventors]

        # Create collaboration for each pair of inventors
        for id1, id2 in combinations(sorted(inventor_ids), 2):
            key = (min(id1, id2), max(id1, id2))
            collaborations[key]["count"] += 1
            # Extract year from publication_date if available
            if patent.publication_date:
                try:
                    # Try to extract year (assuming format like "Jun 10, 2022")
                    year_str = patent.publication_date.split()[-1]
                    year = int(year_str)
                    collaborations[key]["years"].add(year)
                except (ValueError, IndexError):
                    pass

    # Insert into database
    added = 0
    for (sci1_id, sci2_id), data in collaborations.items():
        years = sorted(data["years"]) if data["years"] else []

        # Check if collaboration already exists
        existing = db.query(Collaboration).filter_by(
            scientist1_id=sci1_id,
            scientist2_id=sci2_id,
            collaboration_type='patent'
        ).first()

        if existing:
            # Update existing
            existing.weight = data["count"]
            existing.first_collaboration_year = years[0] if years else None
            existing.last_collaboration_year = years[-1] if years else None
        else:
            # Create new
            collab = Collaboration(
                scientist1_id=sci1_id,
                scientist2_id=sci2_id,
                collaboration_type='patent',
                weight=data["count"],
                first_collaboration_year=years[0] if years else None,
                last_collaboration_year=years[-1] if years else None
            )
            db.add(collab)
            added += 1

    db.commit()
    logger.info(f"✅ Added {added} patent collaborations")
    logger.info(f"   Total pairs: {len(collaborations)}")


def show_statistics(db):
    """Show collaboration statistics."""
    logger.info("\n" + "=" * 80)
    logger.info("📊 COLLABORATION STATISTICS")
    logger.info("=" * 80)

    # Total collaborations
    total = db.query(Collaboration).count()
    logger.info(f"Total collaborations: {total}")

    # By type
    pub_count = db.query(Collaboration).filter_by(collaboration_type='publication').count()
    patent_count = db.query(Collaboration).filter_by(collaboration_type='patent').count()

    logger.info(f"  - Publications: {pub_count}")
    logger.info(f"  - Patents:      {patent_count}")

    # Top collaborations
    logger.info("\n🔝 Top 10 collaborations (by weight):")

    top_collabs = db.query(Collaboration).order_by(
        Collaboration.weight.desc()
    ).limit(10).all()

    for i, collab in enumerate(top_collabs, 1):
        sci1 = db.query(Scientist).get(collab.scientist1_id)
        sci2 = db.query(Scientist).get(collab.scientist2_id)

        years = ""
        if collab.first_collaboration_year and collab.last_collaboration_year:
            if collab.first_collaboration_year == collab.last_collaboration_year:
                years = f"({collab.first_collaboration_year})"
            else:
                years = f"({collab.first_collaboration_year}-{collab.last_collaboration_year})"

        logger.info(
            f"  {i:2d}. {sci1.name:25s} ↔ {sci2.name:25s} "
            f"| {collab.weight:2d} {collab.collaboration_type:11s} {years}"
        )


def main():
    """Compute all collaborations."""
    logger.info("=" * 80)
    logger.info("🤝 COMPUTING COLLABORATIONS")
    logger.info("=" * 80)

    db = SessionLocal()

    try:
        # Compute publication collaborations
        compute_publication_collaborations(db)

        # Compute patent collaborations
        compute_patent_collaborations(db)

        # Show statistics
        show_statistics(db)

        logger.info("\n" + "=" * 80)
        logger.info("✅ COLLABORATION COMPUTATION COMPLETE!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Failed to compute collaborations: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
