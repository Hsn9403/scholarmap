#!/usr/bin/env python3
"""
Migration to add enriched node tables for graph visualization.

Creates two new tables:
1. PersonEnriched - Stores enriched person/scientist data for graph nodes
2. PublicationEnriched - Stores enriched publication data for graph nodes

These tables store the detailed information displayed in graph tooltips.
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

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    JSON, Boolean, create_engine
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from src.database.database import Base, engine
from src.logger import logger


class PersonEnriched(Base):
    """
    Enriched person/scientist data for graph visualization.

    This table stores detailed information about co-authors that has been
    enriched from Scholar profiles and collaboration analysis.

    Displayed when hovering over a person node in the graph.
    """
    __tablename__ = "person_enriched"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Link to Scientists table
    scientist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=False, index=True
    )

    # Scholar profile data
    h_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scholar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    scholar_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    citations_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publications_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affiliation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Collaboration metrics (with the seed researcher)
    collaborations_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )  # Total co-publications + co-inventions
    copublications_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )
    coinventions_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )
    last_collaboration_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Example collaboration titles (JSON array of strings)
    example_titles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Format: ["Title 1", "Title 2", "Title 3"]

    # Metadata
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    enriched_for_researcher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=True, index=True
    )  # Which researcher this was enriched for (context)

    def __repr__(self) -> str:
        return f"<PersonEnriched(id={self.id}, scientist_id={self.scientist_id}, h_index={self.h_index})>"


class PublicationEnriched(Base):
    """
    Enriched publication data for graph visualization.

    This table stores detailed information about publications that has been
    enriched from Scholar and Semantic Scholar APIs.

    Displayed when hovering over a publication node in the graph.
    """
    __tablename__ = "publication_enriched"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Link to Publications table
    publication_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publications.id"), nullable=False, index=True
    )

    # Publication details
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Authors (JSON array of author names)
    authors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Format: ["Author 1", "Author 2", ...]

    # Publication metadata
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)  # Journal name
    cited_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Links
    scholar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    enriched_for_researcher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=True, index=True
    )  # Which researcher this was enriched for (context)

    def __repr__(self) -> str:
        return f"<PublicationEnriched(id={self.id}, title='{self.title[:50]}...', year={self.year})>"


def run_migration():
    """Create the enriched node tables."""
    logger.info("=" * 80)
    logger.info("Creating enriched node tables...")
    logger.info("=" * 80)

    # Create tables
    Base.metadata.create_all(bind=engine)

    logger.info("✓ Tables created:")
    logger.info("  - person_enriched")
    logger.info("  - publication_enriched")
    logger.info("=" * 80)

    print("\n✅ Migration complete!")
    print("\nNew tables:")
    print("  • person_enriched - Enriched person data (H-index, collaborations, etc.)")
    print("  • publication_enriched - Enriched publication data (abstract, authors, etc.)")
    print("\nThese tables store the detailed information displayed in graph tooltips.")


if __name__ == "__main__":
    run_migration()
