#!/usr/bin/env python3
"""
Backfill corporate countries using a single GPT-4o-mini batch call.

Usage:
    python scripts/backfill_corporate_countries.py [--dry-run]
"""
import json
import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'webapp'))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / '.env')
except ImportError:
    pass

from src.logger import logger
from src.database.database import SessionLocal
from src.database.models import Corporate


SYSTEM_PROMPT = """You are a corporate intelligence assistant. Given a list of company names, identify which country each company is headquartered in.

Rules:
- Return ONLY a JSON object mapping each company name (exactly as given) to its ISO country name (e.g. "USA", "France", "Germany", "UK", "Switzerland", "Japan", etc.)
- Use "USA" for US companies, not "United States"
- If you are not confident about a company, use null
- Do not include any explanation, just the JSON object"""


def resolve_countries_batch(names: list[str]) -> dict[str, str | None]:
    """Send all names in one GPT call, return {name: country_or_null}."""
    import openai
    import os

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Split into chunks of 100 to stay within token limits
    chunk_size = 100
    results = {}

    for i in range(0, len(names), chunk_size):
        chunk = names[i:i + chunk_size]
        logger.info(f"Sending batch {i // chunk_size + 1} ({len(chunk)} names)...")

        user_content = json.dumps(chunk, ensure_ascii=False)

        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )

        raw = response.choices[0].message.content
        chunk_result = json.loads(raw)
        results.update(chunk_result)
        logger.info(f"  Got {sum(1 for v in chunk_result.values() if v)} resolved / {len(chunk)} total")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Get all corporates without country
        all_corps = db.query(Corporate).filter(Corporate.country.is_(None)).all()
        logger.info(f"Found {len(all_corps)} corporates without country")

        if not all_corps:
            logger.info("Nothing to do.")
            return

        names = [c.name for c in all_corps]
        country_map = resolve_countries_batch(names)

        # Apply results
        updated = 0
        for corp in all_corps:
            country = country_map.get(corp.name)
            if country:
                if args.dry_run:
                    print(f"  {corp.name} → {country}")
                else:
                    corp.country = country
                    updated += 1

        if not args.dry_run:
            db.commit()
            logger.info(f"✓ Updated {updated} / {len(all_corps)} corporates with country")
        else:
            no_result = [n for n in names if not country_map.get(n)]
            if no_result:
                print(f"\nNo result for {len(no_result)} corporates:")
                for n in no_result:
                    print(f"  {n}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
