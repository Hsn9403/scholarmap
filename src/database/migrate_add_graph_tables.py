#!/usr/bin/env python3
"""
Migration: Add graph optimization tables.

Creates:
1. patent_citations - Replace JSON fields with proper table
2. collaborations - Pre-calculated collaboration weights
3. Adds weight and citation_context to patents_corporate
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database.database import engine, SessionLocal
from src.database.models import Base, PatentCitation, Collaboration
from src.logger import logger


def create_tables():
    """Create the new tables."""
    logger.info("🚀 Creating new graph optimization tables...")

    # Create patent_citations and collaborations tables
    PatentCitation.__table__.create(engine, checkfirst=True)
    logger.info("✅ Created table: patent_citations")

    Collaboration.__table__.create(engine, checkfirst=True)
    logger.info("✅ Created table: collaborations")

    logger.info("✅ All tables created successfully!")


def add_columns_to_patents_corporate():
    """Add weight and citation_context columns to patents_corporate if they don't exist."""
    logger.info("🔧 Adding columns to patents_corporate...")

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'patents_corporate'
            AND column_name IN ('weight', 'citation_context')
        """))
        existing_columns = {row[0] for row in result.fetchall()}

        # Add weight column if missing
        if 'weight' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE patents_corporate
                ADD COLUMN weight INTEGER NOT NULL DEFAULT 1
            """))
            logger.info("✅ Added column: patents_corporate.weight")
        else:
            logger.info("ℹ️  Column patents_corporate.weight already exists")

        # Add citation_context column if missing
        if 'citation_context' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE patents_corporate
                ADD COLUMN citation_context VARCHAR(100)
            """))
            logger.info("✅ Added column: patents_corporate.citation_context")
        else:
            logger.info("ℹ️  Column patents_corporate.citation_context already exists")

        conn.commit()


def verify_tables():
    """Verify that all tables were created successfully."""
    logger.info("\n📊 Verifying tables...")

    with engine.connect() as conn:
        # Check patent_citations
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'patent_citations'
        """))
        if result.fetchone()[0] == 1:
            logger.info("✅ patent_citations table exists")
        else:
            logger.error("❌ patent_citations table missing!")
            return False

        # Check collaborations
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'collaborations'
        """))
        if result.fetchone()[0] == 1:
            logger.info("✅ collaborations table exists")
        else:
            logger.error("❌ collaborations table missing!")
            return False

        # Check patents_corporate columns
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'patents_corporate'
            AND column_name IN ('weight', 'citation_context')
        """))
        columns = {row[0] for row in result.fetchall()}

        if 'weight' in columns:
            logger.info("✅ patents_corporate.weight column exists")
        else:
            logger.error("❌ patents_corporate.weight column missing!")
            return False

        if 'citation_context' in columns:
            logger.info("✅ patents_corporate.citation_context column exists")
        else:
            logger.error("❌ patents_corporate.citation_context column missing!")
            return False

    return True


def main():
    """Run the migration."""
    logger.info("=" * 80)
    logger.info("📦 MIGRATION: Add Graph Optimization Tables")
    logger.info("=" * 80)

    try:
        # Step 1: Create new tables
        create_tables()

        # Step 2: Add columns to existing table
        add_columns_to_patents_corporate()

        # Step 3: Verify
        if verify_tables():
            logger.info("\n" + "=" * 80)
            logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info("\nNext steps:")
            logger.info("1. Run: python src/database/migrate_patent_citations.py")
            logger.info("   (to migrate JSON data to patent_citations table)")
            logger.info("2. Run: python src/database/compute_collaborations.py")
            logger.info("   (to pre-calculate collaboration weights)")
        else:
            logger.error("\n❌ Migration verification failed!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
