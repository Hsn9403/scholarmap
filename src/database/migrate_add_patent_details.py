#!/usr/bin/env python3
"""
Add patent details fields to Patent model.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import engine
from sqlalchemy import text
from src.logger import logger


def migrate():
    """Add cited_by_count and cited_patents_json fields to patents table."""
    with engine.connect() as conn:
        try:
            # Add cited_by_count column
            conn.execute(text("""
                ALTER TABLE patents
                ADD COLUMN IF NOT EXISTS cited_by_count INTEGER
            """))
            logger.info("✓ Added cited_by_count column")

            # Add cited_patents_json column (JSON format)
            conn.execute(text("""
                ALTER TABLE patents
                ADD COLUMN IF NOT EXISTS cited_patents_json JSON
            """))
            logger.info("✓ Added cited_patents_json column")

            # Add citing_patents_json column (JSON format)
            conn.execute(text("""
                ALTER TABLE patents
                ADD COLUMN IF NOT EXISTS citing_patents_json JSON
            """))
            logger.info("✓ Added citing_patents_json column")

            conn.commit()
            logger.info("✅ Migration completed successfully")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            conn.rollback()
            raise


if __name__ == "__main__":
    migrate()
