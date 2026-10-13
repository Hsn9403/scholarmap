"""Migrate JSON cassettes to database."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import APICall, Scientist
from src.logger import logger


def load_cassette(cassette_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load a cassette JSON file.

    Args:
        cassette_path: Path to the cassette file

    Returns:
        Cassette data as dict, or None if loading fails
    """
    try:
        with open(cassette_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load cassette {cassette_path.name}: {e}")
        return None


def extract_scientist_name(cassette_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract scientist name from cassette request query.

    Args:
        cassette_data: Cassette data dictionary

    Returns:
        Scientist name if found, None otherwise

    Example:
        >>> data = {"request": {"q": '"M Keller" site:scholar.google.com'}}
        >>> extract_scientist_name(data)
        'M Keller'
    """
    try:
        query = cassette_data.get("request", {}).get("q", "")
        # Extract text between quotes
        if '"' in query:
            parts = query.split('"')
            if len(parts) >= 2:
                return parts[1].strip()
    except Exception as e:
        logger.warning(f"Failed to extract scientist name: {e}")
    return None


def find_or_create_scientist(
    db, name: str, scholar_id: Optional[str] = None
) -> Optional[Scientist]:
    """
    Find existing scientist or create new one.

    Args:
        db: Database session
        name: Scientist name
        scholar_id: Optional Google Scholar ID

    Returns:
        Scientist object
    """
    try:
        # Try to find by scholar_id first
        if scholar_id:
            scientist = db.query(Scientist).filter_by(scholar_id=scholar_id).first()
            if scientist:
                return scientist

        # Try to find by name
        scientist = db.query(Scientist).filter_by(name=name).first()
        if scientist:
            # Update scholar_id if provided and not set
            if scholar_id and not scientist.scholar_id:
                scientist.scholar_id = scholar_id
                db.commit()
            return scientist

        # Create new scientist
        scientist = Scientist(name=name, scholar_id=scholar_id)
        db.add(scientist)
        db.commit()
        db.refresh(scientist)
        logger.info(f"Created scientist: {name}")
        return scientist

    except Exception as e:
        logger.error(f"Failed to find/create scientist {name}: {e}")
        db.rollback()
        return None


def import_cassette(db, cassette_path: Path) -> bool:
    """
    Import a single cassette into the database.

    Args:
        db: Database session
        cassette_path: Path to cassette file

    Returns:
        True if import succeeded, False otherwise
    """
    try:
        # Load cassette
        cassette_data = load_cassette(cassette_path)
        if not cassette_data:
            return False

        # Extract request hash from filename
        request_hash = cassette_path.stem

        # Check if already imported
        existing = db.query(APICall).filter_by(request_hash=request_hash).first()
        if existing:
            logger.debug(f"Cassette {request_hash[:8]}... already imported")
            return True

        # Extract scientist name from query
        scientist_name = extract_scientist_name(cassette_data)
        scientist_id = None

        if scientist_name:
            scientist = find_or_create_scientist(db, scientist_name)
            if scientist:
                scientist_id = scientist.id

        # Get engine from request
        engine = cassette_data.get("request", {}).get("engine", "unknown")

        # Get creation date from response metadata if available
        created_at = datetime.utcnow()
        if "response" in cassette_data:
            metadata = cassette_data["response"].get("search_metadata", {})
            created_str = metadata.get("created_at")
            if created_str:
                try:
                    created_at = datetime.strptime(
                        created_str, "%Y-%m-%d %H:%M:%S %Z"
                    )
                except Exception:
                    pass

        # Create API call entry
        api_call = APICall(
            scientist_id=scientist_id,
            engine=engine,
            request_json=cassette_data.get("request", {}),
            response_json=cassette_data.get("response", {}),
            request_hash=request_hash,
            created_at=created_at,
        )

        db.add(api_call)
        db.commit()

        logger.info(
            f"Imported cassette {request_hash[:8]}... (scientist: {scientist_name or 'unknown'})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to import cassette {cassette_path.name}: {e}")
        db.rollback()
        return False


def migrate_all_cassettes(cassettes_dir: Path) -> Dict[str, int]:
    """
    Migrate all cassettes from directory to database.

    Args:
        cassettes_dir: Directory containing cassette JSON files

    Returns:
        Statistics dictionary with counts
    """
    db = SessionLocal()
    stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

    try:
        # Get all JSON files
        cassette_files = list(cassettes_dir.glob("*.json"))
        stats["total"] = len(cassette_files)

        logger.info(f"Found {stats['total']} cassettes to migrate")

        for cassette_path in cassette_files:
            if import_cassette(db, cassette_path):
                stats["imported"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Migration complete: {stats['imported']} imported, {stats['failed']} failed"
        )

    except Exception as e:
        logger.error(f"Migration failed: {e}")

    finally:
        db.close()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate cassettes to database")
    parser.add_argument(
        "--cassettes-dir",
        type=Path,
        default=Path("src/api/cassettes"),
        help="Directory containing cassette files",
    )
    args = parser.parse_args()

    if not args.cassettes_dir.exists():
        logger.error(f"Cassettes directory not found: {args.cassettes_dir}")
        sys.exit(1)

    logger.info("Starting cassette migration...")
    stats = migrate_all_cassettes(args.cassettes_dir)

    logger.info("\n📊 Migration Statistics:")
    logger.info(f"   Total cassettes: {stats['total']}")
    logger.info(f"   Successfully imported: {stats['imported']}")
    logger.info(f"   Failed: {stats['failed']}")
