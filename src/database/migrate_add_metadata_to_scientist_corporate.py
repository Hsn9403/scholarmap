#!/usr/bin/env python3
"""
Add metadata column to scientist_corporate table.

This migration adds a JSON column to store evidence and additional
information about scientist-corporate connections.
"""

from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from sqlalchemy import text
from src.database.database import engine
from src.logger import logger


def migrate():
    """Add metadata column to scientist_corporate table."""
    logger.info("="*80)
    logger.info("MIGRATION: Add metadata column to scientist_corporate")
    logger.info("="*80)

    with engine.connect() as conn:
        # Check if column already exists (PostgreSQL)
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.columns
            WHERE table_name = 'scientist_corporate'
            AND column_name = 'metadata'
        """))

        exists = result.fetchone()[0] > 0

        if exists:
            logger.info("✓ Column 'metadata' already exists")
            return

        # Add column
        logger.info("Adding 'metadata' column...")
        conn.execute(text("""
            ALTER TABLE scientist_corporate
            ADD COLUMN metadata JSON
        """))
        conn.commit()

        logger.info("✓ Column 'metadata' added successfully")

    logger.info("="*80)
    logger.info("Migration completed!")
    logger.info("="*80)


if __name__ == "__main__":
    migrate()
