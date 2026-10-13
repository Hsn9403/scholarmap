#!/usr/bin/env python3
"""
Re-parse Scholar author profiles to extract H-index and update database.

This script processes google_scholar_author API calls to extract:
- H-index from cited_by data
- Update scholar_url for scientists with scholar_id
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import APICall, Scientist
from src.database.parse_entities import parse_scholar_author_results
from src.logger import logger


def reparse_scholar_profiles():
    """Re-parse all google_scholar_author API calls to update H-index."""
    db = SessionLocal()
    stats = {
        "processed": 0,
        "h_index_updated": 0,
        "scholar_url_updated": 0,
        "errors": 0,
    }

    try:
        # Get all google_scholar_author API calls
        api_calls = (
            db.query(APICall)
            .filter(APICall.engine == "google_scholar_author")
            .all()
        )

        logger.info(f"Found {len(api_calls)} Scholar author profiles to process")

        for api_call in api_calls:
            try:
                stats["processed"] += 1

                # Track initial values
                initial_h_indexes = {}
                initial_urls = {}
                for scientist in db.query(Scientist).all():
                    initial_h_indexes[scientist.id] = scientist.h_index
                    initial_urls[scientist.id] = scientist.scholar_url

                # Re-parse the profile (this will update h_index and scholar_url)
                scientist, publications = parse_scholar_author_results(db, api_call)

                if scientist:
                    # Check what was updated
                    if scientist.h_index != initial_h_indexes.get(scientist.id):
                        stats["h_index_updated"] += 1
                        logger.info(
                            f"Updated H-index for {scientist.name}: "
                            f"{initial_h_indexes.get(scientist.id)} → {scientist.h_index}"
                        )

                    if scientist.scholar_url != initial_urls.get(scientist.id):
                        stats["scholar_url_updated"] += 1

                db.commit()

            except Exception as e:
                logger.error(f"Error processing API call {api_call.id}: {e}")
                stats["errors"] += 1
                db.rollback()

        logger.info("\n📊 Re-parsing Statistics:")
        logger.info(f"   Profiles processed: {stats['processed']}")
        logger.info(f"   H-index updated: {stats['h_index_updated']}")
        logger.info(f"   Scholar URL updated: {stats['scholar_url_updated']}")
        logger.info(f"   Errors: {stats['errors']}")
        logger.info("\n✅ Re-parsing completed")

    except Exception as e:
        logger.error(f"Re-parsing failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reparse_scholar_profiles()
