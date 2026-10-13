"""Main script to run full migration: cassettes -> database -> parsed entities."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.migrate_cassettes import migrate_all_cassettes
from src.database.parse_entities import parse_api_calls
from src.database.database import SessionLocal
from src.database.models import Scientist, Publication, APICall, Institution
from src.logger import logger


def get_database_stats() -> dict:
    """Get current database statistics."""
    db = SessionLocal()
    try:
        stats = {
            "scientists": db.query(Scientist).count(),
            "publications": db.query(Publication).count(),
            "api_calls": db.query(APICall).count(),
            "institutions": db.query(Institution).count(),
        }
        return stats
    finally:
        db.close()


def print_stats(title: str, stats: dict) -> None:
    """Print formatted statistics."""
    logger.info(f"\n{title}")
    logger.info("=" * len(title))
    for key, value in stats.items():
        logger.info(f"   {key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run full migration from cassettes to parsed entities"
    )
    parser.add_argument(
        "--cassettes-dir",
        type=Path,
        default=Path("src/api/cassettes"),
        help="Directory containing cassette files",
    )
    parser.add_argument(
        "--skip-cassettes",
        action="store_true",
        help="Skip cassette migration (only parse existing API calls)",
    )
    parser.add_argument(
        "--skip-parsing",
        action="store_true",
        help="Skip entity parsing (only migrate cassettes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of API calls to parse",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 PHASE 2: Cassette Migration & Entity Parsing")
    logger.info("=" * 60)

    # Show initial stats
    initial_stats = get_database_stats()
    print_stats("📊 Initial Database State", initial_stats)

    # Step 1: Migrate cassettes
    if not args.skip_cassettes:
        logger.info("\n" + "=" * 60)
        logger.info("Step 1: Migrating cassettes to database...")
        logger.info("=" * 60)

        if not args.cassettes_dir.exists():
            logger.error(f"Cassettes directory not found: {args.cassettes_dir}")
            sys.exit(1)

        cassette_stats = migrate_all_cassettes(args.cassettes_dir)

        logger.info("\n✅ Cassette Migration Complete")
        logger.info(f"   Total: {cassette_stats['total']}")
        logger.info(f"   Imported: {cassette_stats['imported']}")
        logger.info(f"   Failed: {cassette_stats['failed']}")
    else:
        logger.info("\n⏭️  Skipping cassette migration")

    # Step 2: Parse entities
    if not args.skip_parsing:
        logger.info("\n" + "=" * 60)
        logger.info("Step 2: Parsing entities from API responses...")
        logger.info("=" * 60)

        parse_stats = parse_api_calls(limit=args.limit)

        logger.info("\n✅ Entity Parsing Complete")
        logger.info(f"   Processed: {parse_stats['processed']}")
        logger.info(f"   Scientists: {parse_stats['scientists']}")
        logger.info(f"   Publications: {parse_stats['publications']}")
        logger.info(f"   Institutions: {parse_stats['institutions']}")
        logger.info(f"   Errors: {parse_stats['errors']}")
    else:
        logger.info("\n⏭️  Skipping entity parsing")

    # Show final stats
    final_stats = get_database_stats()
    print_stats("\n📊 Final Database State", final_stats)

    # Show changes
    logger.info("\n📈 Changes:")
    for key in initial_stats:
        change = final_stats[key] - initial_stats[key]
        if change > 0:
            logger.info(f"   {key.replace('_', ' ').title()}: +{change}")

    logger.info("\n" + "=" * 60)
    logger.info("🎉 Phase 2 Complete!")
    logger.info("=" * 60)
