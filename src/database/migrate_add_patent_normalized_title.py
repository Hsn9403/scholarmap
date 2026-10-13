#!/usr/bin/env python3
"""
Add normalized_title to patents table.

Steps:
1. Add normalized_title column
2. Populate from existing titles
3. Add UNIQUE constraint
4. Add index
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal, engine
from src.database.models import Patent
from sqlalchemy import text
from src.logger import logger


def normalize_text(text: str) -> str:
    """Normalize text for deduplication (lowercase, no extra spaces)."""
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


def add_normalized_title_column():
    """Add normalized_title column to patents table."""
    logger.info("Step 1: Adding normalized_title column...")

    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE patents
            ADD COLUMN IF NOT EXISTS normalized_title TEXT
        """))
        logger.info("✓ Added patents.normalized_title")
        conn.commit()


def populate_normalized_values():
    """Populate normalized_title from existing titles."""
    logger.info("\nStep 2: Populating normalized values...")

    db = SessionLocal()

    try:
        patents = db.query(Patent).all()
        for patent in patents:
            patent.normalized_title = normalize_text(patent.title)
        db.commit()
        logger.info(f"✓ Normalized {len(patents)} patent titles")

    except Exception as e:
        logger.error(f"Failed to populate normalized values: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def find_duplicates():
    """Find and report duplicates before adding constraints."""
    logger.info("\nStep 3: Checking for duplicates...")

    db = SessionLocal()

    try:
        dup_patents = db.execute(text("""
            SELECT normalized_title, COUNT(*) as count
            FROM patents
            WHERE normalized_title IS NOT NULL AND normalized_title != ''
            GROUP BY normalized_title
            HAVING COUNT(*) > 1
        """)).fetchall()

        if dup_patents:
            logger.warning(f"⚠️  Found {len(dup_patents)} duplicate patent titles:")
            for row in dup_patents[:5]:
                logger.warning(f"   - '{row[0][:60]}...' ({row[1]} times)")
            return len(dup_patents)
        else:
            logger.info("✓ No duplicate patents")
            return 0

    finally:
        db.close()


def add_unique_constraint():
    """Add UNIQUE constraint on normalized_title."""
    logger.info("\nStep 4: Adding UNIQUE constraint...")

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE patents
                ADD CONSTRAINT unique_patent_normalized_title
                UNIQUE (normalized_title)
            """))
            logger.info("✓ Added UNIQUE constraint on patents.normalized_title")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("✓ UNIQUE constraint on patents.normalized_title already exists")
            else:
                raise

        conn.commit()


def add_index():
    """Add index on normalized_title."""
    logger.info("\nStep 5: Adding index...")

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_patents_normalized_title
                ON patents(normalized_title)
            """))
            logger.info("✓ Added index on patents.normalized_title")
        except:
            pass

        conn.commit()


def main():
    """Run all migration steps."""
    logger.info("=" * 80)
    logger.info("MIGRATION: Adding normalized_title to patents")
    logger.info("=" * 80)

    try:
        # Step 1: Add column
        add_normalized_title_column()

        # Step 2: Populate values
        populate_normalized_values()

        # Step 3: Check for duplicates
        duplicates_count = find_duplicates()

        if duplicates_count > 0:
            logger.warning("\n⚠️  DUPLICATES FOUND!")
            logger.warning("You need to manually resolve these duplicates before adding UNIQUE constraint.")
            logger.warning("Then run this migration again.")
            return

        # Step 4: Add UNIQUE constraint
        add_unique_constraint()

        # Step 5: Add index
        add_index()

        logger.info("\n" + "=" * 80)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
