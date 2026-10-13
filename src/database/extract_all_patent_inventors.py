#!/usr/bin/env python3
"""
Extract all patent inventors from google_patents_details cassettes.
"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Patent, Scientist, PatentInventor
from src.logger import logger


def extract_all_inventors():
    """Extract all inventors from cassettes and update database."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"
    db = SessionLocal()

    stats = {
        'cassettes_processed': 0,
        'inventors_added': 0,
        'scientists_created': 0,
    }

    try:
        logger.info("Extracting all patent inventors from cassettes...")

        for cassette_file in cassettes_dir.glob('*.json'):
            try:
                with open(cassette_file, 'r') as f:
                    data = json.load(f)

                # Only process google_patents_details cassettes
                if data.get('request', {}).get('engine') != 'google_patents_details':
                    continue

                stats['cassettes_processed'] += 1

                # Get patent_id from request
                request_patent_id = data.get('request', {}).get('patent_id')
                if not request_patent_id:
                    continue

                # Find patent in database
                patent = db.query(Patent).filter_by(patent_id=request_patent_id).first()
                if not patent:
                    logger.debug(f"Patent not found in DB: {request_patent_id}")
                    continue

                response = data.get('response', {})
                inventors = response.get('inventors', [])

                if not inventors:
                    continue

                logger.info(f"\nProcessing patent: {request_patent_id}")
                logger.info(f"  Found {len(inventors)} inventors in cassette")

                for inventor_data in inventors:
                    inventor_name = inventor_data.get('name', '').strip()
                    if not inventor_name:
                        continue

                    # Find or create scientist
                    scientist = db.query(Scientist).filter(
                        Scientist.name.ilike(inventor_name)
                    ).first()

                    if not scientist:
                        scientist = Scientist(name=inventor_name)
                        db.add(scientist)
                        db.flush()
                        stats['scientists_created'] += 1
                        logger.info(f"    Created scientist: {inventor_name}")

                    # Check if link already exists
                    link_exists = db.query(PatentInventor).filter_by(
                        patent_id=patent.id,
                        scientist_id=scientist.id
                    ).first()

                    if not link_exists:
                        link = PatentInventor(
                            patent_id=patent.id,
                            scientist_id=scientist.id
                        )
                        db.add(link)
                        stats['inventors_added'] += 1
                        logger.info(f"    Linked inventor: {inventor_name}")

            except Exception as e:
                logger.error(f"Error processing {cassette_file.name}: {e}")
                continue

        db.commit()

        logger.info("\n📊 Statistics:")
        logger.info(f"   Cassettes processed: {stats['cassettes_processed']}")
        logger.info(f"   Inventor links added: {stats['inventors_added']}")
        logger.info(f"   Scientists created: {stats['scientists_created']}")
        logger.info("\n✅ All inventors extraction completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    extract_all_inventors()
