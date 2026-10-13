#!/usr/bin/env python3
"""
Extract scholar_id from thumbnail URLs in cassettes and update database.

The scholar_id is not in author.author_id but in the thumbnail URL parameter.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Scientist
from src.logger import logger


def extract_scholar_id_from_thumbnail(thumbnail_url: str) -> str:
    """
    Extract scholar ID from thumbnail URL.

    Example: https://scholar.googleusercontent.com/citations?view_op=view_photo&user=SKZLZuoAAAAJ&citpid=1
    Returns: SKZLZuoAAAAJ
    """
    if not thumbnail_url:
        return None

    try:
        parsed = urlparse(thumbnail_url)
        params = parse_qs(parsed.query)
        return params.get('user', [None])[0]
    except Exception:
        return None


def update_scholar_ids_from_cassettes():
    """Extract scholar IDs from cassettes and update database."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"
    db = SessionLocal()

    stats = {
        'processed': 0,
        'found_scholar_id': 0,
        'updated': 0,
        'already_had_id': 0,
        'not_found_in_db': 0
    }

    try:
        logger.info("Extracting scholar IDs from cassettes...")

        for cassette_file in cassettes_dir.glob('*.json'):
            try:
                with open(cassette_file, 'r') as f:
                    data = json.load(f)

                if data.get('request', {}).get('engine') != 'google_scholar_author':
                    continue

                stats['processed'] += 1

                response = data.get('response', {})
                author = response.get('author', {})

                name = author.get('name')
                if not name:
                    continue

                # Extract scholar_id from thumbnail
                thumbnail = author.get('thumbnail', '')
                scholar_id = extract_scholar_id_from_thumbnail(thumbnail)

                if not scholar_id:
                    logger.debug(f"No scholar_id in thumbnail for: {name}")
                    continue

                stats['found_scholar_id'] += 1

                # Find scientist in database by name
                scientist = db.query(Scientist).filter_by(name=name).first()

                if not scientist:
                    logger.warning(f"Scientist not found in DB: {name}")
                    stats['not_found_in_db'] += 1
                    continue

                # Update scholar_id if not already set
                if scientist.scholar_id and scientist.scholar_id == scholar_id:
                    stats['already_had_id'] += 1
                    logger.debug(f"Already has scholar_id: {name}")
                else:
                    old_id = scientist.scholar_id
                    scientist.scholar_id = scholar_id

                    # Also update scholar_url
                    scientist.scholar_url = f"https://scholar.google.com/citations?user={scholar_id}"

                    db.commit()
                    stats['updated'] += 1

                    logger.info(f"✓ Updated {name}: {old_id or 'None'} → {scholar_id}")

            except Exception as e:
                logger.error(f"Error processing {cassette_file.name}: {e}")
                db.rollback()
                continue

        logger.info("\n📊 Statistics:")
        logger.info(f"   Cassettes processed: {stats['processed']}")
        logger.info(f"   Scholar IDs found in thumbnails: {stats['found_scholar_id']}")
        logger.info(f"   Scientists updated: {stats['updated']}")
        logger.info(f"   Already had scholar_id: {stats['already_had_id']}")
        logger.info(f"   Not found in DB: {stats['not_found_in_db']}")
        logger.info("\n✅ Scholar ID extraction completed")

    except Exception as e:
        logger.error(f"Failed to extract scholar IDs: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    update_scholar_ids_from_cassettes()
