#!/usr/bin/env python3
"""
Add h_index and scholar_url columns to scientists table.

This migration adds:
- h_index (Integer, nullable): Google Scholar H-index
- scholar_url (Text, nullable): Full URL to Scholar profile
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database.database import engine, SessionLocal
from src.logger import logger


def migrate_add_h_index():
    """Add h_index and scholar_url columns to scientists table."""
    db = SessionLocal()

    try:
        logger.info("Starting migration: add h_index and scholar_url columns...")

        # Check if columns already exist
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'scientists'
            AND column_name IN ('h_index', 'scholar_url')
        """))
        existing_columns = [row[0] for row in result]

        # Add h_index column if it doesn't exist
        if 'h_index' not in existing_columns:
            logger.info("Adding h_index column...")
            db.execute(text("""
                ALTER TABLE scientists
                ADD COLUMN h_index INTEGER NULL
            """))
            db.commit()
            logger.info("✓ h_index column added")
        else:
            logger.info("h_index column already exists, skipping")

        # Add scholar_url column if it doesn't exist
        if 'scholar_url' not in existing_columns:
            logger.info("Adding scholar_url column...")
            db.execute(text("""
                ALTER TABLE scientists
                ADD COLUMN scholar_url TEXT NULL
            """))
            db.commit()
            logger.info("✓ scholar_url column added")
        else:
            logger.info("scholar_url column already exists, skipping")

        # Update scholar_url for existing scientists with scholar_id
        logger.info("Updating scholar_url for existing scientists...")
        db.execute(text("""
            UPDATE scientists
            SET scholar_url = CONCAT('https://scholar.google.com/citations?user=', scholar_id)
            WHERE scholar_id IS NOT NULL
            AND (scholar_url IS NULL OR scholar_url = '')
        """))
        db.commit()

        updated = db.execute(text("""
            SELECT COUNT(*) FROM scientists
            WHERE scholar_url IS NOT NULL
        """)).scalar()

        logger.info(f"✓ Updated scholar_url for {updated} scientists")
        logger.info("✅ Migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_add_h_index()
