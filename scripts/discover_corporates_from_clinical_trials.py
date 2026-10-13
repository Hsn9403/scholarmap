#!/usr/bin/env python3
"""
Discover corporate connections from clinical trials.

This script:
1. Searches clinical trials for a researcher (and their co-authors)
2. Identifies trials where researcher/co-author is Principal Investigator
3. Extracts corporates from:
   - Direct sponsors
   - Products/devices used (via product → corporate mapping)
4. Adds them to the database
5. Creates links: Researcher → Co-author → Corporate (via ClinicalTrials)

METHODOLOGY:
- Only accepts trials where person is Principal Investigator
- Detects corporates via:
  - Explicit sponsor name
  - Product/device name (In.Pact → Medtronic, Lutonix → C.R. Bard, etc.)
- Evidence is traceable with NCT ID and study URL
"""
import re
from pathlib import Path
from typing import Set, Dict, List, Tuple

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.clinical_trials import ClinicalTrialsClient, CorporateLink
from src.scholar.client import ScholarClient
from src.database.database import SessionLocal
from src.database.models import Scientist, Corporate
from src.database.add_coauthor_industry_connections import ScientistCorporate
from src.helpers import slug, name_variants
from src.logger import logger
from src.utils import NameResolver
from src.utils.coauthor_name_resolver import CoauthorNameResolver


def discover_corporates_from_clinical_trials(
    researcher_name: str,
    max_studies: int = 50
) -> Tuple[Set[str], List[CorporateLink]]:
    """
    Discover corporate connections from researcher's clinical trials.

    Args:
        researcher_name: Name of the researcher.
        max_studies: Maximum studies to analyze.

    Returns:
        Tuple of (set of corporate names, list of evidence links)
    """
    logger.info("="*80)
    logger.info(f"DISCOVERING CORPORATES FROM CLINICAL TRIALS: {researcher_name}")
    logger.info("="*80)

    ct_client = ClinicalTrialsClient()
    corporates = set()
    all_links = []

    try:
        # Search clinical trials
        logger.info(f"\n1. Searching clinical trials for: {researcher_name}")
        results = ct_client.find_corporate_links(researcher_name, max_studies)

        logger.info(f"✓ Found {results.total_studies_found} total studies")
        logger.info(f"✓ {results.studies_as_pi} studies where researcher is PI")
        logger.info(f"✓ {len(results.corporate_links)} corporate link(s) detected\n")

        # Extract corporates and links
        for link in results.corporate_links:
            corporates.add(link.corporate)
            all_links.append(link)

            logger.info(
                f"  ✓ {link.corporate} (via {link.detection_field})"
                f"\n    Study: {link.nct_id} - {link.study_title[:60]}..."
            )

        logger.info(f"\n✓ Found {len(corporates)} unique corporate entities")

    except Exception as e:
        logger.error(f"Error extracting corporates from clinical trials: {e}")

    return corporates, all_links


def discover_corporates_from_coauthors_clinical_trials(
    researcher_name: str,
    max_coauthors: int = 20,
    max_studies_per_coauthor: int = 20,
    skip_initials_only: bool = True,
    use_db_only: bool = False,
    scholar_data=None
) -> Tuple[Dict[str, Set[str]], Dict[str, List[CorporateLink]]]:
    """
    Discover corporate connections from researcher's co-authors' clinical trials.

    Creates paths: Researcher → Co-author → Corporate (via ClinicalTrials)

    Args:
        researcher_name: Name of the main researcher.
        max_coauthors: Maximum co-authors to scan.
        max_studies_per_coauthor: Max studies per co-author.
        skip_initials_only: If True, skip co-authors with initials only (e.g., "M Berger")
                           unless they have a Scholar ID to resolve the full name.

    Returns:
        Tuple of:
        - Dict mapping co-author name → set of corporates
        - Dict mapping co-author name → list of evidence links
    """
    logger.info("="*80)
    logger.info(f"DISCOVERING CORPORATES FROM CO-AUTHORS' CLINICAL TRIALS")
    logger.info(f"Main Researcher: {researcher_name}")
    logger.info("="*80)

    # Get researcher's co-authors
    ct_client = ClinicalTrialsClient()

    logger.info(f"\n1. Finding co-authors of {researcher_name}...")

    if scholar_data is not None:
        # Reuse already-collected scholar data (no extra API call)
        logger.info(f"✓ Reusing existing scholar data: {len(scholar_data.coauthors or [])} co-authors")
    elif use_db_only:
        # Load co-authors from database
        from src.database.adapters import scientist_to_scholar_data

        scholar_data = scientist_to_scholar_data(
            scientist_name=researcher_name,
            use_db_only=use_db_only
        )

        if not scholar_data:
            logger.error(f"Researcher not found in database: {researcher_name}")
            return {}, {}

        logger.info(f"✓ Loaded {len(scholar_data.coauthors)} co-authors from DB")
    else:
        # Fetch from Scholar API
        scholar_client = ScholarClient()

        # Search for researcher
        candidates = scholar_client.find_candidates(researcher_name, num=5)
        if not candidates:
            logger.error(f"Researcher not found: {researcher_name}")
            return {}, {}

        # Get full scholar data with co-authors
        scholar_data = scholar_client.fetch_author_data(
            candidates[0].author_id,
            num_articles=20
        )

        logger.info(f"✓ Found {len(scholar_data.coauthors)} co-authors from API")

    # Filter co-authors if requested
    if skip_initials_only:
        filtered_coauthors = []
        skipped_count = 0

        for coauthor in scholar_data.coauthors:
            # Check if name looks like initials only (e.g., "M Berger", "CH Bruneau")
            # Pattern: 1-2 letters, optional space/dot, then surname
            import re
            is_initials_only = bool(re.match(r'^[A-Z]{1,2}[\s\.]?\s+[A-Z]', coauthor.name))

            if is_initials_only and not coauthor.scholar_id:
                # Skip: initials only without Scholar ID (high risk of false positives)
                skipped_count += 1
                logger.debug(f"⊘ Skipping '{coauthor.name}' (initials only, no Scholar ID)")
            else:
                filtered_coauthors.append(coauthor)

        scholar_data.coauthors = filtered_coauthors

        if skipped_count > 0:
            logger.warning(
                f"⚠️  Skipped {skipped_count} co-authors with initials only (no Scholar ID). "
                f"Use --no-skip-initials to include them (risk of false positives)."
            )
            logger.info(f"✓ {len(filtered_coauthors)} co-authors remaining after filtering")

    # ── Résolution des noms (sync) + déduplication ────────────────────────────
    publication_resolver = CoauthorNameResolver(scholar_data)
    name_resolver = NameResolver(use_db_only=use_db_only, skip_scholar_search=True)
    ct_client = ClinicalTrialsClient()

    resolved = []  # [(original_name, resolved_name, variants)]
    seen_keys: set = set()

    for coauthor in scholar_data.coauthors[:max_coauthors]:
        pub_resolved = publication_resolver.resolve(coauthor.name)
        if pub_resolved and pub_resolved != coauthor.name:
            resolved_name = pub_resolved
        else:
            api_resolved, _ = name_resolver.resolve(
                coauthor.name, scholar_id=coauthor.scholar_id, context_name=researcher_name
            )
            resolved_name = api_resolved

        key = resolved_name.strip().lower()
        if key in seen_keys:
            logger.debug(f"⊘ Duplicate skipped: {resolved_name}")
            continue
        seen_keys.add(key)

        variants = [v for v in name_variants(resolved_name)[1:]]
        resolved.append((coauthor.name, resolved_name, variants))

    total = len(resolved)
    logger.info(f"[CT] {total} co-auteurs uniques à scanner (après dédup)")

    # ── Appels HTTP async avec semaphore ──────────────────────────────────────
    import asyncio
    import httpx

    CT_SEMAPHORE = 20

    async def _fetch_one(session, sem, idx, original_name, resolved_name, variants):
        async with sem:
            logger.info(f"\n[{idx}/{total}] Scanning CT: {resolved_name}")
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    results = await ct_client.find_corporate_links_async(
                        session, resolved_name, max_studies=max_studies_per_coauthor
                    )
                    if not results.corporate_links:
                        for variant in variants:
                            logger.info(f"  ↩ Retrying CT as '{variant}'")
                            results = await ct_client.find_corporate_links_async(
                                session, variant, max_studies=max_studies_per_coauthor
                            )
                            if results.corporate_links:
                                break
                    if results.corporate_links:
                        logger.info(f"  ✓ {len(results.corporates_found)} corporate(s)")
                        return original_name, results.corporates_found, results.corporate_links, False
                    return original_name, None, None, False
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"  ✗ Attempt {attempt+1}/{max_retries+1} failed: {e} — retrying in 1s")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"  ✗ All attempts failed for {resolved_name}: {e}")
                        return original_name, None, None, True

    async def _run_all():
        sem = asyncio.Semaphore(CT_SEMAPHORE)
        async with httpx.AsyncClient() as session:
            tasks = [
                _fetch_one(session, sem, i, orig, resolved_name, variants)
                for i, (orig, resolved_name, variants) in enumerate(resolved, 1)
            ]
            return await asyncio.gather(*tasks)

    coauthor_corporates = {}
    coauthor_links = {}
    skipped_coauthors = []

    for name, corporates_found, links_found, had_error in asyncio.run(_run_all()):
        if had_error:
            skipped_coauthors.append(name)
        elif corporates_found:
            coauthor_corporates[name] = corporates_found
            coauthor_links[name] = links_found

    # Also scan the seed researcher themselves (not just co-authors)
    logger.info(f"\n[SEED] Scanning seed researcher in ClinicalTrials: {researcher_name}")
    try:
        seed_ct_client = ClinicalTrialsClient()
        seed_results = seed_ct_client.find_corporate_links(researcher_name, max_studies=50)
        if not seed_results.corporate_links:
            for variant in name_variants(researcher_name)[1:]:
                logger.info(f"  ↩ No results — retrying CT search as '{variant}'")
                seed_results = seed_ct_client.find_corporate_links(variant, max_studies=50)
                if seed_results.corporate_links:
                    logger.info(f"  ✓ Found results with variant '{variant}'")
                    break
        if seed_results.corporate_links:
            logger.info(f"  ✓ Seed has {len(seed_results.corporates_found)} corporate(s): {', '.join(sorted(seed_results.corporates_found))}")
            coauthor_corporates[researcher_name] = seed_results.corporates_found
            coauthor_links[researcher_name] = seed_results.corporate_links
        else:
            logger.info(f"  → No corporate links found for seed researcher")
    except Exception as e:
        logger.warning(f"  ✗ Error scanning seed {researcher_name} in CT: {e}")

    # Summary
    total_corporates = set()
    for corps in coauthor_corporates.values():
        total_corporates.update(corps)

    logger.info(f"\n{'='*80}")
    logger.info(f"SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Co-authors scanned: {len(coauthor_corporates)}")
    logger.info(f"Total unique corporates: {len(total_corporates)}")
    logger.info(f"Corporates: {', '.join(sorted(total_corporates))}")
    if skipped_coauthors:
        logger.warning(f"⚠ {len(skipped_coauthors)} co-author(s) skipped after retries: {', '.join(skipped_coauthors)}")

    return coauthor_corporates, coauthor_links, skipped_coauthors


def add_clinical_trials_corporates_to_database(
    researcher_name: str,
    corporates: Set[str],
    links: List[CorporateLink] = None
) -> int:
    """
    Add clinical trials corporates to the database.

    Unlike patents, clinical trials create DIRECT links between
    Scientist and Corporate (with evidence pointing to the clinical trial).

    Args:
        researcher_name: Name of the researcher.
        corporates: Set of corporate names.
        links: List of evidence links with NCT IDs.

    Returns:
        Number of new corporates added.
    """
    if not corporates:
        logger.info("No corporates to add.")
        return 0

    logger.info(f"\n3. Adding corporates to database...")

    db = SessionLocal()
    new_corporates = 0
    objects_to_add = []  # Batch collect all objects

    try:
        # Get or create scientist
        scientist = db.query(Scientist).filter_by(
            normalized_name=slug(researcher_name)
        ).first()

        if not scientist:
            logger.warning(f"Scientist not found in DB: {researcher_name}")
            logger.info("Creating new scientist entry...")
            scientist = Scientist(
                name=researcher_name,
                normalized_name=slug(researcher_name)
            )
            # Flush so scientist.id is populated before use as a FK below.
            db.add(scientist)
            db.flush()

        # Add each corporate and create link
        for corporate_name in corporates:
            # Get or create corporate
            corporate = db.query(Corporate).filter_by(
                normalized_name=slug(corporate_name)
            ).first()

            if not corporate:
                corporate = Corporate(
                    name=corporate_name,
                    normalized_name=slug(corporate_name),
                    notes="Discovered from ClinicalTrials.gov"
                )
                # Flush so corporate.id is populated before use as a FK below.
                db.add(corporate)
                db.flush()
                new_corporates += 1
                logger.info(f"  ✓ Added new corporate: {corporate_name}")
            else:
                logger.info(f"  → Corporate already exists: {corporate_name}")

            # Create link if it doesn't exist
            existing_link = db.query(ScientistCorporate).filter_by(
                scientist_id=scientist.id,
                corporate_id=corporate.id,
                affiliation_type="clinical_trials"
            ).first()

            # Build fresh evidence for this corporate
            evidence = []
            if links:
                for link in links:
                    if link.corporate.lower() == corporate_name.lower():
                        evidence.append({
                            "nct_id": link.nct_id,
                            "study_title": link.study_title,
                            "detection_field": link.detection_field,
                            "detection_value": link.detection_value,
                            "role": link.role,
                            "url": link.study_url
                        })

            if not existing_link:
                # Create new link
                sci_corp_link = ScientistCorporate(
                    scientist_id=scientist.id,
                    corporate_id=corporate.id,
                    affiliation_type="clinical_trials",
                    notes=f"Principal Investigator on {len(evidence)} clinical trial(s)",
                    evidence_data={"evidence": evidence} if evidence else None
                )
                objects_to_add.append(sci_corp_link)
                logger.info(
                    f"  ✓ Created link: {researcher_name} → {corporate_name} "
                    f"(via clinical_trials)"
                )
            else:
                # Update existing link with refreshed evidence (detection_field may have changed)
                existing_link.evidence_data = {"evidence": evidence} if evidence else None
                existing_link.notes = f"Principal Investigator on {len(evidence)} clinical trial(s)"
                logger.info(
                    f"  ↻ Updated link: {researcher_name} → {corporate_name} "
                    f"({len(evidence)} trial(s))"
                )

        # Batch commit all objects at once
        for obj in objects_to_add:
            db.add(obj)
        db.commit()
        logger.info(f"\n✓ Added {new_corporates} new corporate(s)")

    except Exception as e:
        logger.error(f"Error adding to database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    return new_corporates


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover corporate connections from clinical trials"
    )
    parser.add_argument(
        "researcher",
        help="Researcher name to analyze"
    )
    parser.add_argument(
        "--max-studies",
        type=int,
        default=50,
        help="Maximum studies to analyze for main researcher"
    )
    parser.add_argument(
        "--include-coauthors",
        action="store_true",
        help="Also scan co-authors' clinical trials"
    )
    parser.add_argument(
        "--max-coauthors",
        type=int,
        default=20,
        help="Maximum co-authors to scan"
    )
    parser.add_argument(
        "--no-skip-initials",
        action="store_true",
        help="Include co-authors with initials only (will attempt name resolution)"
    )
    parser.add_argument(
        "--add-to-db",
        action="store_true",
        help="Add discovered corporates to database"
    )

    args = parser.parse_args()

    # Scan main researcher
    corporates, links = discover_corporates_from_clinical_trials(
        args.researcher,
        max_studies=args.max_studies
    )

    # Optionally scan co-authors
    if args.include_coauthors:
        coauthor_corps, coauthor_links = discover_corporates_from_coauthors_clinical_trials(
            args.researcher,
            max_coauthors=args.max_coauthors,
            skip_initials_only=not args.no_skip_initials
        )

        # Merge results
        for coauthor, corps in coauthor_corps.items():
            corporates.update(corps)
            if coauthor in coauthor_links:
                links.extend(coauthor_links[coauthor])

    # Add to database if requested
    if args.add_to_db:
        add_clinical_trials_corporates_to_database(
            args.researcher,
            corporates,
            links
        )
    else:
        logger.info("\n" + "="*80)
        logger.info("DONE (not added to database - use --add-to-db to persist)")
        logger.info("="*80)


if __name__ == "__main__":
    main()
