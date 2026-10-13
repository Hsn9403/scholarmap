#!/usr/bin/env python3
"""Extract years from publication cassettes."""
import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Publication
from src.logger import logger


def extract_year_from_summary(summary: str):
    """Extract year from publication_info.summary."""
    if not summary:
        return None
    match = re.search(r'\b(19\d{2}|20\d{2})\b', summary)
    if match:
        return int(match.group(1))
    return None


cassettes_dir = project_root / 'src' / 'api' / 'cassettes'
db = SessionLocal()

updated = 0
processed = 0

try:
    for cassette_file in cassettes_dir.glob('*.json'):
        try:
            with open(cassette_file, 'r') as f:
                data = json.load(f)

            if data.get('request', {}).get('engine') != 'google_scholar':
                continue

            processed += 1
            results = data.get('response', {}).get('organic_results', [])

            for result in results:
                title = result.get('title')
                if not title:
                    continue

                # Find publication (case-insensitive)
                pub = db.query(Publication).filter(
                    Publication.title.ilike(title)
                ).first()

                if not pub:
                    # Try partial match
                    title_prefix = title[:50]
                    pub = db.query(Publication).filter(
                        Publication.title.ilike(f'{title_prefix}%')
                    ).first()

                if not pub or pub.year:
                    continue

                # Extract year
                pub_info = result.get('publication_info', {})
                summary = pub_info.get('summary', '')
                year = extract_year_from_summary(summary)

                if year:
                    pub.year = year
                    updated += 1
                    logger.info(f'✓ {pub.title[:60]}... → year {year}')

        except Exception as e:
            continue

    db.commit()
    logger.info(f'\n✅ Processed {processed} cassettes, updated {updated} publications with years')

except Exception as e:
    logger.error(f'Error: {e}', exc_info=True)
    db.rollback()
finally:
    db.close()
