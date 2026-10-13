#!/usr/bin/env python3
"""
Revert Elvesys and Inside Therapeutics back to corporates.

These are companies (corporates), not academic institutions.
The 'assignee' role is correct and stored in PatentCorporate.role.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Corporate,
    Institution,
    PatentCorporate,
    ScientistInstitution,
    Patent,
)
from src.database.parse_entities import normalize_name
from src.logger import logger
from sqlalchemy import text


def move_institution_to_corporate(db, institution_name: str):
    """Move an institution back to corporates table."""

    # Find the institution
    institution = db.query(Institution).filter(Institution.name.ilike(f"%{institution_name}%")).first()
    if not institution:
        logger.warning(f"Institution not found: {institution_name}")
        return

    logger.info(f"Found institution: {institution.name} (ID: {institution.id})")

    # Check if corporate already exists
    normalized = normalize_name(institution.name)
    existing_corp = db.query(Corporate).filter_by(normalized_name=normalized).first()

    if existing_corp:
        logger.info(f"Corporate already exists: {existing_corp.name} (ID: {existing_corp.id})")
        corporate = existing_corp
    else:
        # Create new corporate
        corporate = Corporate(
            name=institution.name,
            normalized_name=normalized,
            country=institution.country,
            notes="Company (moved back from institutions)"
        )
        db.add(corporate)
        db.flush()
        logger.info(f"Created corporate: {corporate.name} (ID: {corporate.id})")

    # Recreate patent-corporate links
    # Get all scientists linked to this institution
    scientist_links = db.query(ScientistInstitution).filter_by(
        institution_id=institution.id
    ).all()

    scientist_ids = [link.scientist_id for link in scientist_links]
    logger.info(f"Found {len(scientist_ids)} scientists linked to institution")

    # For each scientist, find their patents and link to corporate
    from src.database.models import PatentInventor
    for scientist_id in scientist_ids:
        # Get patents where this scientist is inventor
        patent_links = db.query(PatentInventor).filter_by(scientist_id=scientist_id).all()

        for patent_link in patent_links:
            # Check if this patent should be linked to this corporate
            # (if it was previously linked when it was an institution)

            # Check if link already exists
            existing_link = (
                db.query(PatentCorporate)
                .filter_by(patent_id=patent_link.patent_id, corporate_id=corporate.id)
                .first()
            )

            if not existing_link:
                # Create link with assignee role
                corp_link = PatentCorporate(
                    patent_id=patent_link.patent_id,
                    corporate_id=corporate.id,
                    role="assignee"
                )
                db.add(corp_link)

                patent = db.query(Patent).get(patent_link.patent_id)
                logger.info(f"  Linked patent {patent.patent_id} to corporate as assignee")

    # Delete scientist-institution links
    db.execute(text("""
        DELETE FROM scientist_institution WHERE institution_id = :inst_id
    """), {"inst_id": institution.id})

    # Delete the institution entry
    logger.info(f"Deleting institution: {institution.name}")
    db.delete(institution)

    db.commit()
    logger.info(f"✅ Successfully moved {institution_name} to corporates")


def main():
    """Main entry point."""
    db = SessionLocal()

    try:
        logger.info("Reverting institutions to corporates...")

        # Move Elvesys back to corporates
        move_institution_to_corporate(db, "Elvesys")

        # Move Inside Therapeutics back to corporates
        move_institution_to_corporate(db, "Inside Therapeutics")

        logger.info("✅ Institutions reverted to corporates successfully")

    except Exception as e:
        logger.error(f"Failed to revert: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
