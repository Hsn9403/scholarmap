#!/usr/bin/env python3
"""
Migration to add PatentEnriched table for graph visualization.

Creates the patent_enriched table that stores detailed patent information
displayed in graph tooltips when hovering over patent nodes.
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

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Date
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from src.database.database import Base, engine
from src.logger import logger


class PatentEnriched(Base):
    """
    Enriched patent data for graph visualization.

    This table stores detailed information about patents that is
    displayed when hovering over a patent node in the graph.

    Tooltip content:
    - Patent number (e.g., FR3158313A1)
    - Co-inventors list
    - Publication/Filing/Priority dates
    - Assignee (company/organization)
    - Main claims (text)
    - Citations count
    """
    __tablename__ = "patent_enriched"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Link to Patents table
    patent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patents.id"), nullable=False, index=True
    )

    # Patent identification
    patent_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # e.g., "FR3158313A1", "US10123456B2"

    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inventors (JSON array of names)
    coinventors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Format: ["Maxime Keller", "Remy OLLIVIER", "Tristan GAUTHIER"]

    # Dates
    publication_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Format: "2025-07-18" or "2025-07-18"

    filing_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Format: "2024-01-12"

    priority_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Format: "2024-01-12"

    # Assignee (company/organization)
    assignee: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g., "Inside Therapeutics", "Université de Bordeaux"

    # Claims (main claims text)
    main_claims: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Can store as JSON array or full text
    # Format option 1 (text): "1. Module de mélange..."
    # Format option 2 (JSON): ["1. Module...", "2. Module...", "3. Module..."]

    # Citations
    cited_by_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    forward_citations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Format: ["US123456", "EP789012", ...]

    backward_citations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Format: ["US111111", "EP222222", ...]

    # Links
    patent_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g., "https://patents.google.com/patent/FR3158313A1"

    # Additional metadata
    patent_office: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # e.g., "FR", "US", "EP", "WO"

    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # e.g., "Pending", "Granted", "Expired"

    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Patent abstract/description

    # Metadata
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    enriched_for_researcher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=True, index=True
    )  # Which researcher this was enriched for (context)

    def __repr__(self) -> str:
        return f"<PatentEnriched(id={self.id}, patent_number='{self.patent_number}', assignee='{self.assignee}')>"


def run_migration():
    """Create the patent_enriched table."""
    logger.info("=" * 80)
    logger.info("Creating patent_enriched table...")
    logger.info("=" * 80)

    # Create table
    Base.metadata.create_all(bind=engine)

    logger.info("✓ Table created: patent_enriched")
    logger.info("=" * 80)

    print("\n✅ Migration complete!")
    print("\nNew table:")
    print("  • patent_enriched - Enriched patent data for graph tooltips")
    print("\nTooltip content:")
    print("  - Patent number (e.g., FR3158313A1)")
    print("  - Co-inventors")
    print("  - Publication/Filing/Priority dates")
    print("  - Assignee (company)")
    print("  - Main claims")
    print("  - Citations count")


if __name__ == "__main__":
    run_migration()
