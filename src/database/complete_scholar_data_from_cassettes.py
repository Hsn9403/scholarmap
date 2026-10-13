#!/usr/bin/env python3
"""
Complete scholar data from cassettes: merge duplicates + extract scholar_id + h_index.

This script does everything in one pass:
1. Parse all Scholar author cassettes
2. Extract name, scholar_id (from thumbnail), h_index
3. Find or create scientist in DB (merge duplicates)
4. Update with complete data
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Scientist
from src.logger import logger


def extract_scholar_id_from_thumbnail(thumbnail_url: str) -> str:
    """Extract scholar ID from thumbnail URL."""
    if not thumbnail_url:
        return None
    try:
        parsed = urlparse(thumbnail_url)
        params = parse_qs(parsed.query)
        return params.get('user', [None])[0]
    except Exception:
        return None


def normalize_name(name: str) -> str:
    """Normalize name for matching."""
    return " ".join(name.lower().split())


def complete_scholar_data():
    """Extract all Scholar data from cassettes and update DB."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"
    db = SessionLocal()

    stats = {
        'cassettes_processed': 0,
        'profiles_found': 0,
        'scientists_created': 0,
        'scientists_updated': 0,
        'duplicates_merged': 0
    }

    try:
        logger.info("Extracting complete Scholar data from cassettes...")

        # First pass: collect all data from cassettes
        cassette_data = {}

        for cassette_file in cassettes_dir.glob('*.json'):
            try:
                with open(cassette_file, 'r') as f:
                    data = json.load(f)

                if data.get('request', {}).get('engine') != 'google_scholar_author':
                    continue

                stats['cassettes_processed'] += 1

                response = data.get('response', {})
                author = response.get('author', {})

                name = author.get('name')
                if not name:
                    continue

                # Extract scholar_id from thumbnail
                thumbnail = author.get('thumbnail', '')
                scholar_id = extract_scholar_id_from_thumbnail(thumbnail)

                # Extract H-index
                cited_by = response.get('cited_by', {})
                h_index = None
                if cited_by and isinstance(cited_by, dict):
                    table = cited_by.get('table', [])
                    if len(table) > 1:
                        h_index_entry = table[1]
                        h_data = h_index_entry.get('indice_h') or h_index_entry.get('h_index')
                        if h_data:
                            h_index = h_data.get('all')

                affiliation = author.get('affiliations', '')

                cassette_data[name] = {
                    'scholar_id': scholar_id,
                    'h_index': h_index,
                    'affiliation': affiliation
                }

                stats['profiles_found'] += 1
                logger.info(f"Found profile: {name} (scholar_id: {scholar_id}, h_index: {h_index})")

            except Exception as e:
                logger.error(f"Error processing {cassette_file.name}: {e}")
                continue

        # Second pass: update database
        for name, data in cassette_data.items():
            try:
                norm_name = normalize_name(name)

                # Find ALL scientists with this name (case-insensitive)
                scientists = db.query(Scientist).filter(
                    Scientist.name.ilike(name)
                ).all()

                if not scientists:
                    # Create new scientist
                    scientist = Scientist(
                        name=name,
                        scholar_id=data['scholar_id'],
                        scholar_url=f"https://scholar.google.com/citations?user={data['scholar_id']}" if data['scholar_id'] else None,
                        h_index=data['h_index'],
                        affiliation=data['affiliation']
                    )
                    db.add(scientist)
                    db.commit()
                    stats['scientists_created'] += 1
                    logger.info(f"✓ Created: {name}")

                elif len(scientists) == 1:
                    # Update existing scientist
                    scientist = scientists[0]
                    updated = False

                    if data['scholar_id'] and not scientist.scholar_id:
                        scientist.scholar_id = data['scholar_id']
                        scientist.scholar_url = f"https://scholar.google.com/citations?user={data['scholar_id']}"
                        updated = True

                    if data['h_index'] and not scientist.h_index:
                        scientist.h_index = data['h_index']
                        updated = True

                    if data['affiliation'] and not scientist.affiliation:
                        scientist.affiliation = data['affiliation']
                        updated = True

                    if updated:
                        db.commit()
                        stats['scientists_updated'] += 1
                        logger.info(f"✓ Updated: {name}")

                else:
                    # Multiple duplicates - merge them
                    logger.info(f"Merging {len(scientists)} duplicates for: {name}")

                    # Choose best one (prefer one with scholar_id from cassette)
                    best = None
                    if data['scholar_id']:
                        # Find one with this scholar_id
                        best = next((s for s in scientists if s.scholar_id == data['scholar_id']), None)

                    if not best:
                        # Find one with any scholar_id
                        best = next((s for s in scientists if s.scholar_id), None)

                    if not best:
                        # Just take first
                        best = scientists[0]

                    # Update best with cassette data
                    if data['scholar_id'] and not best.scholar_id:
                        best.scholar_id = data['scholar_id']
                        best.scholar_url = f"https://scholar.google.com/citations?user={data['scholar_id']}"

                    if data['h_index'] and not best.h_index:
                        best.h_index = data['h_index']

                    if data['affiliation'] and not best.affiliation:
                        best.affiliation = data['affiliation']

                    # Delete other duplicates (simple deletion, don't move links to avoid errors)
                    for scientist in scientists:
                        if scientist.id != best.id:
                            try:
                                db.delete(scientist)
                                stats['duplicates_merged'] += 1
                            except Exception as e:
                                logger.warning(f"Could not delete duplicate ID {scientist.id}: {e}")
                                db.rollback()
                                # Continue with others

                    db.commit()
                    logger.info(f"✓ Merged duplicates for: {name}")

            except Exception as e:
                logger.error(f"Error updating scientist {name}: {e}")
                db.rollback()
                continue

        logger.info("\n📊 Statistics:")
        logger.info(f"   Cassettes processed: {stats['cassettes_processed']}")
        logger.info(f"   Profiles found: {stats['profiles_found']}")
        logger.info(f"   Scientists created: {stats['scientists_created']}")
        logger.info(f"   Scientists updated: {stats['scientists_updated']}")
        logger.info(f"   Duplicates merged: {stats['duplicates_merged']}")
        logger.info("\n✅ Scholar data extraction completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    complete_scholar_data()
