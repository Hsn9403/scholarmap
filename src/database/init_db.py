"""Initialize the database schema."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import engine, Base
from src.database.models import (
    Scientist,
    Publication,
    Patent,
    Institution,
    Corporate,
    APICall,
    PublicationAuthor,
    PatentInventor,
    PatentCorporate,
    ScientistInstitution,
)
from src.logger import logger


def init_database(drop_existing: bool = False) -> None:
    """
    Initialize database schema by creating all tables.

    Args:
        drop_existing: If True, drop all existing tables before creating new ones.
                      WARNING: This will delete all data!

    Example:
        >>> init_database()  # Create tables if they don't exist
        >>> init_database(drop_existing=True)  # Drop and recreate all tables
    """
    try:
        if drop_existing:
            logger.warning("Dropping all existing tables...")
            Base.metadata.drop_all(bind=engine)
            logger.info("All tables dropped successfully")

        logger.info("Creating database tables...")
        from src.database.database import create_all_tables
        create_all_tables()
        logger.info("Database tables created successfully")

        # Print created tables
        tables = Base.metadata.tables.keys()
        logger.info(f"Created {len(tables)} tables:")
        for table in sorted(tables):
            logger.info(f"  - {table}")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize the database schema")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating new ones (WARNING: deletes all data)",
    )
    args = parser.parse_args()

    if args.drop:
        confirm = input(
            "⚠️  WARNING: This will DELETE ALL DATA in the database. Continue? (yes/no): "
        )
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    init_database(drop_existing=args.drop)
