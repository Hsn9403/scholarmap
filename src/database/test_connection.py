"""Test database connection and basic operations."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database.database import engine, SessionLocal
from src.database.models import Scientist, APICall
from src.logger import logger


def test_connection() -> bool:
    """Test basic database connection."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            logger.info(f"✅ Database connection successful!")
            logger.info(f"PostgreSQL version: {version}")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


def test_tables() -> bool:
    """Test that all tables exist."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """
                )
            )
            tables = [row[0] for row in result.fetchall()]

            expected_tables = {
                "scientists",
                "publications",
                "patents",
                "institution",
                "corporates",
                "api_calls",
                "publications_author",
                "patents_inventor",
                "patents_corporate",
                "scientist_institution",
            }

            missing = expected_tables - set(tables)
            if missing:
                logger.error(f"❌ Missing tables: {missing}")
                return False

            logger.info(f"✅ All {len(expected_tables)} tables exist:")
            for table in sorted(tables):
                logger.info(f"   - {table}")
            return True

    except Exception as e:
        logger.error(f"❌ Failed to check tables: {e}")
        return False


def test_crud_operations() -> bool:
    """Test basic CRUD operations."""
    try:
        db = SessionLocal()

        # Create a test scientist
        test_scientist = Scientist(
            name="Test Scientist",
            scholar_id="test123",
            affiliation="Test University",
        )
        db.add(test_scientist)
        db.commit()
        db.refresh(test_scientist)

        logger.info(f"✅ Created test scientist: {test_scientist}")

        # Read
        found = db.query(Scientist).filter_by(scholar_id="test123").first()
        assert found is not None
        logger.info(f"✅ Read test scientist: {found}")

        # Update
        found.affiliation = "Updated University"
        db.commit()
        logger.info(f"✅ Updated scientist affiliation")

        # Delete
        db.delete(found)
        db.commit()
        logger.info(f"✅ Deleted test scientist")

        # Verify deletion
        deleted = db.query(Scientist).filter_by(scholar_id="test123").first()
        assert deleted is None
        logger.info(f"✅ Verified deletion")

        db.close()
        return True

    except Exception as e:
        logger.error(f"❌ CRUD operations failed: {e}")
        if db:
            db.rollback()
            db.close()
        return False


def test_statistics() -> None:
    """Display current database statistics."""
    try:
        db = SessionLocal()

        stats = {
            "Scientists": db.query(Scientist).count(),
            "Publications": db.query(Scientist).count(),
            "API Calls": db.query(APICall).count(),
        }

        logger.info("📊 Database statistics:")
        for entity, count in stats.items():
            logger.info(f"   {entity}: {count}")

        db.close()

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")


if __name__ == "__main__":
    logger.info("🧪 Testing database connection and operations...\n")

    # Test 1: Connection
    if not test_connection():
        logger.error("Connection test failed. Make sure PostgreSQL is running and accessible.")
        logger.error("Check your .env file for correct database credentials.")
        sys.exit(1)

    print()

    # Test 2: Tables
    if not test_tables():
        logger.error("Tables test failed. Run init_db.py first:")
        logger.error("  python src/database/init_db.py")
        sys.exit(1)

    print()

    # Test 3: CRUD operations
    if not test_crud_operations():
        logger.error("CRUD operations test failed.")
        sys.exit(1)

    print()

    # Test 4: Statistics
    test_statistics()

    print()
    logger.info("🎉 All tests passed! Database is ready.")
