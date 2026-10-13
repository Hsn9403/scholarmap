#!/usr/bin/env python3
"""
Add UNIQUE constraints to prevent duplicates.

Steps:
1. Add normalized_title column to publications
2. Add normalized_name column to scientists
3. Add normalized_name column to corporates
4. Populate normalized values from existing data
5. Find and merge remaining duplicates
6. Add UNIQUE constraints
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal, engine
from src.database.models import Publication, Scientist, Corporate
from sqlalchemy import text
from src.logger import logger


def normalize_text(text: str) -> str:
    """Normalize text for deduplication (lowercase, no extra spaces)."""
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


def add_normalized_columns():
    """Add normalized columns to tables."""
    logger.info("Step 1: Adding normalized columns...")

    with engine.connect() as conn:
        # Add normalized_title to publications
        conn.execute(text("""
            ALTER TABLE publications
            ADD COLUMN IF NOT EXISTS normalized_title TEXT
        """))
        logger.info("✓ Added publications.normalized_title")

        # Add normalized_name to scientists
        conn.execute(text("""
            ALTER TABLE scientists
            ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)
        """))
        logger.info("✓ Added scientists.normalized_name")

        # Add normalized_name to corporates (if not exists)
        # Note: corporates already has normalized_name, but let's make sure
        conn.execute(text("""
            ALTER TABLE corporates
            ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)
        """))
        logger.info("✓ Added/verified corporates.normalized_name")

        conn.commit()


def populate_normalized_values():
    """Populate normalized columns from existing data."""
    logger.info("\nStep 2: Populating normalized values...")

    db = SessionLocal()

    try:
        # Publications
        pubs = db.query(Publication).all()
        for pub in pubs:
            pub.normalized_title = normalize_text(pub.title)
        db.commit()
        logger.info(f"✓ Normalized {len(pubs)} publication titles")

        # Scientists
        scientists = db.query(Scientist).all()
        for scientist in scientists:
            scientist.normalized_name = normalize_text(scientist.name)
        db.commit()
        logger.info(f"✓ Normalized {len(scientists)} scientist names")

        # Corporates
        corporates = db.query(Corporate).all()
        for corp in corporates:
            corp.normalized_name = normalize_text(corp.name)
        db.commit()
        logger.info(f"✓ Normalized {len(corporates)} corporate names")

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
        # Find duplicate publications
        dup_pubs = db.execute(text("""
            SELECT normalized_title, COUNT(*) as count
            FROM publications
            WHERE normalized_title IS NOT NULL AND normalized_title != ''
            GROUP BY normalized_title
            HAVING COUNT(*) > 1
        """)).fetchall()

        if dup_pubs:
            logger.warning(f"⚠️  Found {len(dup_pubs)} duplicate publication titles:")
            for row in dup_pubs[:5]:  # Show first 5
                logger.warning(f"   - '{row[0][:60]}...' ({row[1]} times)")
            logger.warning("   Run merge_duplicate_publications.py to fix!")
        else:
            logger.info("✓ No duplicate publications")

        # Find duplicate scientists
        dup_scientists = db.execute(text("""
            SELECT normalized_name, COUNT(*) as count
            FROM scientists
            WHERE normalized_name IS NOT NULL AND normalized_name != ''
            GROUP BY normalized_name
            HAVING COUNT(*) > 1
        """)).fetchall()

        if dup_scientists:
            logger.warning(f"⚠️  Found {len(dup_scientists)} duplicate scientist names:")
            for row in dup_scientists[:5]:
                logger.warning(f"   - '{row[0]}' ({row[1]} times)")
            logger.warning("   Run merge_scientist_duplicates.py to fix!")
        else:
            logger.info("✓ No duplicate scientists")

        # Find duplicate corporates
        dup_corporates = db.execute(text("""
            SELECT normalized_name, COUNT(*) as count
            FROM corporates
            WHERE normalized_name IS NOT NULL AND normalized_name != ''
            GROUP BY normalized_name
            HAVING COUNT(*) > 1
        """)).fetchall()

        if dup_corporates:
            logger.warning(f"⚠️  Found {len(dup_corporates)} duplicate corporate names:")
            for row in dup_corporates[:5]:
                logger.warning(f"   - '{row[0]}' ({row[1]} times)")
        else:
            logger.info("✓ No duplicate corporates")

        return len(dup_pubs) + len(dup_scientists) + len(dup_corporates)

    finally:
        db.close()


def add_unique_constraints():
    """Add UNIQUE constraints on normalized columns."""
    logger.info("\nStep 4: Adding UNIQUE constraints...")

    with engine.connect() as conn:
        try:
            # Publications
            conn.execute(text("""
                ALTER TABLE publications
                ADD CONSTRAINT unique_normalized_title
                UNIQUE (normalized_title)
            """))
            logger.info("✓ Added UNIQUE constraint on publications.normalized_title")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("✓ UNIQUE constraint on publications.normalized_title already exists")
            else:
                raise

        try:
            # Scientists
            conn.execute(text("""
                ALTER TABLE scientists
                ADD CONSTRAINT unique_normalized_name
                UNIQUE (normalized_name)
            """))
            logger.info("✓ Added UNIQUE constraint on scientists.normalized_name")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("✓ UNIQUE constraint on scientists.normalized_name already exists")
            else:
                raise

        try:
            # Corporates
            conn.execute(text("""
                ALTER TABLE corporates
                ADD CONSTRAINT unique_corporate_normalized_name
                UNIQUE (normalized_name)
            """))
            logger.info("✓ Added UNIQUE constraint on corporates.normalized_name")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("✓ UNIQUE constraint on corporates.normalized_name already exists")
            else:
                raise

        conn.commit()


def add_indexes():
    """Add indexes on normalized columns for faster lookups."""
    logger.info("\nStep 5: Adding indexes...")

    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_publications_normalized_title
                ON publications(normalized_title)
            """))
            logger.info("✓ Added index on publications.normalized_title")
        except:
            pass

        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scientists_normalized_name
                ON scientists(normalized_name)
            """))
            logger.info("✓ Added index on scientists.normalized_name")
        except:
            pass

        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_corporates_normalized_name
                ON corporates(normalized_name)
            """))
            logger.info("✓ Added index on corporates.normalized_name")
        except:
            pass

        conn.commit()


def main():
    """Run all migration steps."""
    logger.info("=" * 80)
    logger.info("MIGRATION: Adding UNIQUE constraints to prevent duplicates")
    logger.info("=" * 80)

    try:
        # Step 1: Add columns
        add_normalized_columns()

        # Step 2: Populate values
        populate_normalized_values()

        # Step 3: Check for duplicates
        duplicates_count = find_duplicates()

        if duplicates_count > 0:
            logger.warning("\n⚠️  DUPLICATES FOUND!")
            logger.warning("Please run the following scripts to merge duplicates:")
            logger.warning("  - python src/database/merge_duplicate_publications.py")
            logger.warning("  - python src/database/merge_all_scientist_duplicates.py")
            logger.warning("\nThen run this migration again to add UNIQUE constraints.")
            return

        # Step 4: Add UNIQUE constraints
        add_unique_constraints()

        # Step 5: Add indexes
        add_indexes()

        logger.info("\n" + "=" * 80)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("1. Update models.py to include normalized columns")
        logger.info("2. Update parsing code to check for duplicates before insertion")

    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
