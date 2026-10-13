#!/usr/bin/env python3
"""
Migration script to add metadata fields to Publication and Patent tables.

Adds:
- Publication: source, abstract, authors_raw
- Patent: publication_date, filing_date, priority_date
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal, engine
from src.logger import logger
from sqlalchemy import text


def migrate():
    """Run the migration."""
    db = SessionLocal()

    try:
        logger.info("Starting migration: add metadata fields")

        # Add columns to publications table
        logger.info("Adding columns to publications table...")
        db.execute(text("""
            ALTER TABLE publications
            ADD COLUMN IF NOT EXISTS source TEXT,
            ADD COLUMN IF NOT EXISTS abstract TEXT,
            ADD COLUMN IF NOT EXISTS authors_raw TEXT
        """))

        # Add columns to patents table
        logger.info("Adding columns to patents table...")
        db.execute(text("""
            ALTER TABLE patents
            ADD COLUMN IF NOT EXISTS publication_date VARCHAR(50),
            ADD COLUMN IF NOT EXISTS filing_date VARCHAR(50),
            ADD COLUMN IF NOT EXISTS priority_date VARCHAR(50)
        """))

        db.commit()
        logger.info("✅ Migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
