#!/usr/bin/env python3
"""
Fix categorization of research startups/institutions.

Moves Elvesys and Inside Therapeutics from corporates to institutions.
These are research-focused startups, not traditional corporate patent holders.
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
    Scientist,
)
from src.database.parse_entities import normalize_name
from src.logger import logger


def move_corporate_to_institution(db, corporate_name: str):
    """Move a corporate entity to institutions table."""

    # Find the corporate
    corporate = db.query(Corporate).filter(Corporate.name.ilike(f"%{corporate_name}%")).first()
    if not corporate:
        logger.warning(f"Corporate not found: {corporate_name}")
        return

    logger.info(f"Found corporate: {corporate.name} (ID: {corporate.id})")

    # Check if institution already exists
    normalized = normalize_name(corporate.name)
    existing_inst = db.query(Institution).filter_by(normalized_name=normalized).first()

    if existing_inst:
        logger.info(f"Institution already exists: {existing_inst.name} (ID: {existing_inst.id})")
        institution = existing_inst
    else:
        # Create new institution
        institution = Institution(
            name=corporate.name,
            normalized_name=normalized,
            country=corporate.country,
            notes=f"Research startup/institution (moved from corporates)"
        )
        db.add(institution)
        db.flush()
        logger.info(f"Created institution: {institution.name} (ID: {institution.id})")

    # Get all scientists linked to patents from this corporate
    patent_links = db.query(PatentCorporate).filter_by(corporate_id=corporate.id).all()
    logger.info(f"Found {len(patent_links)} patent links")

    scientists_to_link = set()
    for link in patent_links:
        # Get inventors of this patent
        from src.database.models import PatentInventor
        inventors = db.query(PatentInventor).filter_by(patent_id=link.patent_id).all()
        for inv in inventors:
            scientists_to_link.add(inv.scientist_id)

    logger.info(f"Found {len(scientists_to_link)} scientists to link to institution")

    # Link scientists to institution
    for scientist_id in scientists_to_link:
        # Check if link already exists
        existing_link = (
            db.query(ScientistInstitution)
            .filter_by(scientist_id=scientist_id, institution_id=institution.id)
            .first()
        )
        if not existing_link:
            link = ScientistInstitution(
                scientist_id=scientist_id,
                institution_id=institution.id
            )
            db.add(link)
            scientist = db.query(Scientist).get(scientist_id)
            logger.info(f"  Linked scientist: {scientist.name if scientist else scientist_id}")

    # Delete the corporate entry (cascade will delete patent links)
    logger.info(f"Deleting corporate: {corporate.name}")
    db.delete(corporate)

    db.commit()
    logger.info(f"✅ Successfully moved {corporate_name} to institutions")


def main():
    """Main entry point."""
    db = SessionLocal()

    try:
        logger.info("Starting institution categorization fix...")

        # Move Elvesys
        move_corporate_to_institution(db, "Elvesys")

        # Move Inside Therapeutics
        move_corporate_to_institution(db, "Inside Therapeutics")

        logger.info("✅ Institution categorization fixed successfully")

    except Exception as e:
        logger.error(f"Failed to fix categorization: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
