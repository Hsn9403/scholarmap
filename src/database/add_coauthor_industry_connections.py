#!/usr/bin/env python3
"""
Add co-author industry connections to the database.

This script:
1. Creates a new junction table (ScientistCorporate) for scientist-company affiliations
2. Inserts Andre Imbert and his co-authors with industry connections
3. Links them to their respective companies

Example data:
- Andre Imbert (seed researcher)
  - F Larocca @ Meta Platforms Inc
  - P Iannelli @ OHB System AG
"""
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from sqlalchemy import Column, Integer, String, ForeignKey, Index, Text, JSON, select
from sqlalchemy.orm import Session

from src.database.database import SessionLocal, engine, Base
from src.database.models import Scientist, Corporate, Publication, PublicationAuthor
from src.logger import logger
from src.helpers import slug


# Check if ScientistCorporate table exists, if not create it
class ScientistCorporate(Base):
    """Junction table linking scientists to corporates (via affiliation)."""

    __tablename__ = "scientist_corporate"

    id = Column(Integer, primary_key=True, index=True)
    scientist_id = Column(Integer, ForeignKey("scientists.id"), nullable=False, index=True)
    corporate_id = Column(Integer, ForeignKey("corporates.id"), nullable=False, index=True)
    affiliation_type = Column(String(50), nullable=False, default="employment", index=True)
    # Types: employment, collaboration, consulting, clinical_trials, transparence_sante, etc.
    notes = Column(Text, nullable=True)  # Source of information
    evidence_data = Column(JSON, nullable=True)  # Evidence and additional data

    __table_args__ = (
        Index("ix_scientist_corporate_sci_corp", "scientist_id", "corporate_id"),
    )

    def __repr__(self):
        return f"<ScientistCorporate(scientist_id={self.scientist_id}, corporate_id={self.corporate_id}, type='{self.affiliation_type}')>"


def get_or_create_scientist(db: Session, name: str, scholar_id: str = None, affiliation: str = None) -> Scientist:
    """Get existing scientist or create new one."""
    # Try to find by scholar_id first
    if scholar_id:
        scientist = db.query(Scientist).filter_by(scholar_id=scholar_id).first()
        if scientist:
            logger.info(f"Found existing scientist: {scientist.name}")
            return scientist

    # Try to find by normalized name
    normalized = slug(name)
    scientist = db.query(Scientist).filter_by(normalized_name=normalized).first()

    if scientist:
        logger.info(f"Found existing scientist by name: {scientist.name}")
        return scientist

    # Create new scientist
    scientist = Scientist(
        name=name,
        normalized_name=normalized,
        scholar_id=scholar_id,
        affiliation=affiliation
    )
    db.add(scientist)
    db.commit()
    db.refresh(scientist)
    logger.info(f"Created new scientist: {scientist.name}")
    return scientist


def get_or_create_corporate(db: Session, name: str, country: str = None) -> Corporate:
    """Get existing corporate or create new one."""
    normalized = slug(name)

    corporate = db.query(Corporate).filter_by(normalized_name=normalized).first()

    if corporate:
        logger.info(f"Found existing corporate: {corporate.name}")
        return corporate

    # Create new corporate
    corporate = Corporate(
        name=name,
        normalized_name=normalized,
        country=country
    )
    db.add(corporate)
    db.commit()
    db.refresh(corporate)
    logger.info(f"Created new corporate: {corporate.name}")
    return corporate


def link_scientist_to_corporate(
    db: Session,
    scientist: Scientist,
    corporate: Corporate,
    affiliation_type: str = "employment",
    notes: str = None
):
    """Link scientist to corporate via affiliation."""
    # Check if link already exists
    existing = db.query(ScientistCorporate).filter_by(
        scientist_id=scientist.id,
        corporate_id=corporate.id
    ).first()

    if existing:
        logger.info(f"Link already exists: {scientist.name} → {corporate.name}")
        return existing

    # Create new link
    link = ScientistCorporate(
        scientist_id=scientist.id,
        corporate_id=corporate.id,
        affiliation_type=affiliation_type,
        notes=notes
    )
    db.add(link)
    db.commit()
    logger.info(f"Created link: {scientist.name} → {corporate.name} ({affiliation_type})")
    return link


def add_andre_imbert_connections(db: Session):
    """Add Andre Imbert and his co-authors with industry connections."""
    logger.info("=" * 80)
    logger.info("Adding Andre Imbert industry connections")
    logger.info("=" * 80)

    # 1. Create/get Andre Imbert
    andre = get_or_create_scientist(
        db,
        name="Andre Imbert",
        scholar_id="q0IH-fAAAAAJ",  # His actual Scholar ID
        affiliation="Université de Bordeaux"
    )

    # 2. Create/get co-authors with industry affiliations
    f_larocca = get_or_create_scientist(
        db,
        name="F Larocca",
        scholar_id="eRcfGQYAAAAJ",
        affiliation="Meta Platforms Inc"
    )

    p_iannelli = get_or_create_scientist(
        db,
        name="P Iannelli",
        scholar_id="eASjuygAAAAJ",
        affiliation="AOCS & GNC Engineer, OHB System AG"
    )

    # 3. Create/get companies
    meta = get_or_create_corporate(
        db,
        name="Meta Platforms Inc",
        country="USA"
    )

    ohb = get_or_create_corporate(
        db,
        name="OHB System AG",
        country="Germany"
    )

    # 4. Link co-authors to companies
    link_scientist_to_corporate(
        db,
        scientist=f_larocca,
        corporate=meta,
        affiliation_type="employment",
        notes="Source: Google Scholar affiliation (2026-02)"
    )

    link_scientist_to_corporate(
        db,
        scientist=p_iannelli,
        corporate=ohb,
        affiliation_type="employment",
        notes="Source: Google Scholar affiliation (2026-02) - AOCS & GNC Engineer"
    )

    logger.info("=" * 80)
    logger.info("Summary of connections:")
    logger.info(f"  Andre Imbert (seed researcher)")
    logger.info(f"    ├─ F Larocca → Meta Platforms Inc (2 publications)")
    logger.info(f"    └─ P Iannelli → OHB System AG (1 publication)")
    logger.info("=" * 80)

    return {
        "seed": andre,
        "coauthors": [f_larocca, p_iannelli],
        "companies": [meta, ohb]
    }


def main():
    """Main function to add industry connections."""
    logger.info("Starting database insertion...")

    # Create tables if they don't exist
    logger.info("Creating tables if needed...")
    Base.metadata.create_all(bind=engine)

    # Insert data
    db = SessionLocal()
    try:
        result = add_andre_imbert_connections(db)
        logger.info("\n✓ Successfully added industry connections to database!")

        # Print summary
        print("\n" + "=" * 80)
        print("DATABASE INSERTION COMPLETE")
        print("=" * 80)
        print(f"\nSeed Researcher: {result['seed'].name} (ID: {result['seed'].id})")
        print(f"\nCo-authors with industry connections:")
        for coauthor in result['coauthors']:
            print(f"  • {coauthor.name} (ID: {coauthor.id}) @ {coauthor.affiliation}")
        print(f"\nCompanies:")
        for company in result['companies']:
            print(f"  • {company.name} (ID: {company.id})")

        print("\n" + "=" * 80)
        print("Next steps:")
        print("  1. Run visualization script to see the graph")
        print("  2. Use database API to query connections")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Error during insertion: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
