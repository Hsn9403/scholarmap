#!/usr/bin/env python3
"""
Extract and link Scholar profiles from Google search cassettes.

Finds Scholar profile links in search results and links them to existing scientists.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import APICall, Scientist
from src.database.parse_entities import extract_scholar_id_from_url
from src.logger import logger


def normalize_name_for_matching(name: str) -> str:
    """Normalize name for fuzzy matching."""
    # Remove accents, lowercase, remove extra spaces
    import unicodedata
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = name.lower().strip()
    # Remove common prefixes/suffixes
    name = name.replace('dr. ', '').replace('dr ', '').replace('prof. ', '').replace('prof ', '')
    return name


def extract_scholar_profiles(db, limit: int = None) -> dict:
    """Extract Scholar profiles from Google search cassettes."""
    stats = {
        "cassettes_processed": 0,
        "profiles_found": 0,
        "profiles_linked": 0,
        "profiles_already_linked": 0,
        "profiles_no_match": 0,
    }

    # Get all Google search API calls for Scholar
    query = (
        db.query(APICall)
        .filter(APICall.engine == "google")
        .order_by(APICall.created_at)
    )

    if limit:
        query = query.limit(limit)

    api_calls = query.all()
    logger.info(f"Processing {len(api_calls)} Google search API calls...")

    for api_call in api_calls:
        request = api_call.request_json
        response = api_call.response_json

        # Check if this is a Scholar search
        query_str = request.get('q', '')
        if 'scholar.google.com' not in query_str:
            continue

        stats["cassettes_processed"] += 1

        # Extract the name being searched
        # Query format: "Name" site:scholar.google.com/citations
        import re
        name_match = re.search(r'"([^"]+)"', query_str)
        if not name_match:
            continue

        searched_name = name_match.group(1)
        normalized_searched = normalize_name_for_matching(searched_name)

        # Get organic results
        organic_results = response.get('organic_results', [])

        for result in organic_results:
            title = result.get('title', '').strip()
            link = result.get('link', '')

            # Check if this is a Scholar profile
            if 'scholar.google.com/citations?user=' not in link:
                continue

            scholar_id = extract_scholar_id_from_url(link)
            if not scholar_id:
                continue

            stats["profiles_found"] += 1

            # Check if this profile is already in database
            existing = db.query(Scientist).filter_by(scholar_id=scholar_id).first()
            if existing:
                stats["profiles_already_linked"] += 1
                logger.debug(f"Profile already exists: {title} ({scholar_id})")
                continue

            # Try to match with existing scientist by name
            normalized_title = normalize_name_for_matching(title)

            # Try exact match first
            scientist = db.query(Scientist).filter_by(name=title).first()

            # Try fuzzy match if no exact match
            if not scientist:
                # Check if normalized names are similar
                all_scientists = db.query(Scientist).filter(
                    Scientist.scholar_id.is_(None)
                ).all()

                for s in all_scientists:
                    normalized_s = normalize_name_for_matching(s.name)

                    # Check if names are similar (contains or very close)
                    if (normalized_title in normalized_s or
                        normalized_s in normalized_title or
                        normalized_searched in normalized_s or
                        normalized_s in normalized_searched):
                        scientist = s
                        logger.info(f"Fuzzy match: '{title}' → '{s.name}'")
                        break

            if scientist:
                # Update the scientist with Scholar ID
                scientist.scholar_id = scholar_id
                stats["profiles_linked"] += 1
                logger.info(f"✓ Linked profile: {title} ({scholar_id}) → {scientist.name}")
            else:
                stats["profiles_no_match"] += 1
                logger.debug(f"No match found for: {title} ({scholar_id})")

        db.commit()

    return stats


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract Scholar profiles from cassettes")
    parser.add_argument("--limit", type=int, help="Limit number of cassettes to process")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        logger.info("Starting Scholar profile extraction...")
        stats = extract_scholar_profiles(db, limit=args.limit)

        logger.info("\n📊 Extraction Statistics:")
        logger.info(f"   Cassettes processed: {stats['cassettes_processed']}")
        logger.info(f"   Profiles found: {stats['profiles_found']}")
        logger.info(f"   Profiles linked: {stats['profiles_linked']}")
        logger.info(f"   Profiles already linked: {stats['profiles_already_linked']}")
        logger.info(f"   Profiles no match: {stats['profiles_no_match']}")

        logger.info("\n✅ Scholar profile extraction completed")

    except Exception as e:
        logger.error(f"Failed to extract profiles: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
