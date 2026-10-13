#!/usr/bin/env python3
"""
Discover corporate connections from Transparence Santé (French conflicts of interest database).

This script:
1. Retrieves co-authors of a researcher (with successful name disambiguation)
2. For each co-author with first name + last name, searches Transparence Santé
3. Identifies companies that paid >10,000€ to the co-author
4. Adds them to the database with evidence
5. Creates links: Researcher → Co-author → Corporate (via Transparence Santé)

METHODOLOGY:
- Only processes co-authors where disambiguation succeeded (full name available)
- Searches for financial declarations over 10,000€ threshold
- Evidence includes: amount, payment reason, declaration ID, date
- All payments are traceable to official French government database
"""

from pathlib import Path
from typing import Dict, List, Set, Tuple
import re

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.transparence_sante import (
    TransparenceSanteClient,
    FinancialDeclaration,
    TransparenceSanteSearchResult
)
from src.scholar.client import ScholarClient
from src.database.database import SessionLocal
from src.database.models import Scientist, Corporate
from src.database.add_coauthor_industry_connections import ScientistCorporate
from src.helpers import slug, name_variants
from src.logger import logger
from src.utils import NameResolver
from src.utils.coauthor_name_resolver import CoauthorNameResolver


def extract_first_last_name(full_name: str) -> Tuple[str, str]:
    """
    Extract first name and last name from a full name.

    Args:
        full_name: Full name (e.g., "Edgar Duval", "Jean-Paul Martin")

    Returns:
        Tuple of (first_name, last_name)
    """
    # Remove extra spaces
    full_name = " ".join(full_name.split())

    # Split by space
    parts = full_name.split()

    if len(parts) < 2:
        # Not enough parts for first + last name
        return "", ""

    # Last part is last name, everything else is first name
    last_name = parts[-1]
    first_name = " ".join(parts[:-1])

    return first_name, last_name


def is_valid_full_name(name: str) -> bool:
    """
    Check if a name is a valid full name (not just initials).

    Args:
        name: Name to check

    Returns:
        True if valid full name, False if initials only or invalid
    """
    # Remove spaces
    clean_name = name.replace(" ", "").replace(".", "")

    # Must have at least 4 characters total
    if len(clean_name) < 4:
        return False

    # Check if looks like initials (1-2 letters + surname)
    # Pattern: one or two uppercase letters followed by surname
    # Example: "M Berger", "CH Bruneau", "J.P. Martin"
    if re.match(r'^[A-Z]{1,2}[\s\.-]*[A-Z][a-z]+$', name):
        return False

    # Split and check each part has at least 2 characters
    parts = name.split()
    if len(parts) < 2:
        return False

    # First name should have at least 2 characters (not just an initial)
    if len(parts[0].replace(".", "")) < 2:
        return False

    return True


def discover_corporates_from_transparence_sante(
    researcher_name: str,
    max_coauthors: int = 50,
    min_amount: float = 0.0,
    skip_initials_only: bool = True,
    use_db_only: bool = False,
    scholar_data=None
) -> Tuple[Dict[str, Set[str]], Dict[str, List[FinancialDeclaration]]]:
    """
    Discover corporate connections from co-authors' Transparence Santé declarations.

    Creates paths: Researcher → Co-author → Corporate (via financial declarations)

    Args:
        researcher_name: Name of the main researcher
        max_coauthors: Maximum co-authors to scan
        min_amount: Minimum payment amount in euros (default: 10,000€)
        skip_initials_only: If True, skip co-authors with initials only

    Returns:
        Tuple of:
        - Dict mapping co-author name → set of companies
        - Dict mapping co-author name → list of financial declarations
    """
    logger.info("="*80)
    logger.info(f"DISCOVERING CORPORATES FROM TRANSPARENCE SANTÉ")
    logger.info(f"Main Researcher: {researcher_name}")
    logger.info(f"Payment threshold: ≥{min_amount:,.0f} €")
    logger.info("="*80)

    # Get researcher's co-authors
    ts_client = TransparenceSanteClient()

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
            num_articles=50  # More articles = more co-authors
        )

        logger.info(f"✓ Found {len(scholar_data.coauthors)} co-authors from API")

    # ── Résolution des noms (sync, avant l'async) ─────────────────────────────
    publication_resolver = CoauthorNameResolver(scholar_data)
    name_resolver = NameResolver(use_db_only=use_db_only, skip_scholar_search=True)
    ts_client = TransparenceSanteClient()

    # Prépare les co-auteurs : résolution + déduplication par (first, last) normalisé
    resolved = []  # [(original_name, first_name, last_name, name_variants)]
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

        if skip_initials_only and not is_valid_full_name(resolved_name):
            continue
        first_name, last_name = extract_first_last_name(resolved_name)
        if not first_name or not last_name:
            continue

        key = f"{last_name.upper()}|{first_name.upper()}"
        if key in seen_keys:
            logger.debug(f"⊘ Duplicate skipped: {resolved_name}")
            continue
        seen_keys.add(key)

        variants = []
        for v in name_variants(resolved_name)[1:]:
            v_first, v_last = extract_first_last_name(v)
            if v_first and v_last:
                variants.append((v_first, v_last))

        resolved.append((coauthor.name, first_name, last_name, variants))

    total = len(resolved)
    logger.info(f"[TS] {total} co-auteurs uniques à scanner (après dédup)")

    # ── Appels HTTP async avec semaphore ──────────────────────────────────────
    import asyncio
    import httpx

    TS_SEMAPHORE = 20  # requêtes simultanées max vers TS

    async def _fetch_one(session, sem, idx, original_name, first_name, last_name, variants):
        async with sem:
            logger.info(f"\n[{idx}/{total}] Scanning: {first_name} {last_name}")
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    result = await ts_client.search_by_name_async(
                        session, last_name, first_name, min_amount
                    )
                    if not result.declarations:
                        for v_first, v_last in variants:
                            logger.info(f"  ↩ Retrying as '{v_first} {v_last}'")
                            result = await ts_client.search_by_name_async(
                                session, v_last, v_first, min_amount
                            )
                            if result.declarations:
                                break
                    if result.declarations:
                        logger.info(f"  ✓ {len(result.companies_found)} company(ies)")
                        return original_name, result.companies_found, result.declarations, False
                    return original_name, None, None, False
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"  ✗ Attempt {attempt+1}/{max_retries+1} failed: {e} — retrying in 1s")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"  ✗ All attempts failed for {first_name} {last_name}: {e}")
                        return original_name, None, None, True

    async def _run_all():
        sem = asyncio.Semaphore(TS_SEMAPHORE)
        headers = {'User-Agent': 'Scholarmap/1.0', 'Accept': 'application/json'}
        async with httpx.AsyncClient(headers=headers) as session:
            tasks = [
                _fetch_one(session, sem, i, orig, fn, ln, variants)
                for i, (orig, fn, ln, variants) in enumerate(resolved, 1)
            ]
            return await asyncio.gather(*tasks)

    coauthor_companies = {}
    coauthor_declarations = {}
    skipped_coauthors = []

    for name, companies_found, declarations_found, had_error in asyncio.run(_run_all()):
        if had_error:
            skipped_coauthors.append(name)
        elif companies_found:
            coauthor_companies[name] = companies_found
            coauthor_declarations[name] = declarations_found

    total_companies = set()
    for companies in coauthor_companies.values():
        total_companies.update(companies)

    # Also scan the seed researcher themselves (not just co-authors)
    logger.info(f"\n[SEED] Scanning seed researcher in Transparence Santé: {researcher_name}")
    seed_first, seed_last = extract_first_last_name(researcher_name)
    if seed_first and seed_last and is_valid_full_name(researcher_name):
        try:
            seed_ts_client = TransparenceSanteClient()
            seed_result = seed_ts_client.search_by_name(
                last_name=seed_last,
                first_name=seed_first,
                min_amount=min_amount
            )
            if not seed_result.declarations:
                for variant in name_variants(researcher_name)[1:]:
                    v_first, v_last = extract_first_last_name(variant)
                    if not v_first or not v_last:
                        continue
                    seed_result = seed_ts_client.search_by_name(
                        last_name=v_last, first_name=v_first, min_amount=min_amount
                    )
                    if seed_result.declarations:
                        break
            if seed_result.declarations:
                logger.info(f"  ✓ Seed has {len(seed_result.companies_found)} company(ies): {', '.join(sorted(seed_result.companies_found))}")
                coauthor_companies[researcher_name] = seed_result.companies_found
                coauthor_declarations[researcher_name] = seed_result.declarations
                total_companies.update(seed_result.companies_found)
            else:
                logger.info(f"  → No declarations ≥{min_amount:,.0f}€ found for seed")
        except Exception as e:
            logger.warning(f"  ✗ Error scanning seed {researcher_name} in TS: {e}")

    logger.info(f"\n{'='*80}")
    logger.info(f"SUMMARY — {len(coauthor_companies)} co-authors with declarations, {len(total_companies)} unique companies")
    if total_companies:
        logger.info(f"Companies: {', '.join(sorted(total_companies))}")
    if skipped_coauthors:
        logger.warning(f"⚠ {len(skipped_coauthors)} co-author(s) skipped after retries: {', '.join(skipped_coauthors)}")

    return coauthor_companies, coauthor_declarations, skipped_coauthors


def add_transparence_sante_to_database(
    researcher_name: str,
    coauthor_companies: Dict[str, Set[str]],
    coauthor_declarations: Dict[str, List[FinancialDeclaration]]
) -> int:
    """
    Add Transparence Santé corporate connections to the database.

    Creates links: Scientist (researcher) → Scientist (co-author) → Corporate

    Args:
        researcher_name: Name of the main researcher
        coauthor_companies: Dict mapping co-author name → set of companies
        coauthor_declarations: Dict mapping co-author name → list of declarations

    Returns:
        Number of new links created
    """
    if not coauthor_companies:
        logger.info("No companies to add.")
        return 0

    logger.info(f"\n3. Adding to database...")

    db = SessionLocal()
    new_links = 0
    objects_to_add = []  # Batch collect all objects

    try:
        # Get or create main researcher
        researcher = db.query(Scientist).filter_by(
            normalized_name=slug(researcher_name)
        ).first()

        if not researcher:
            logger.warning(f"Main researcher not found in DB: {researcher_name}")
            logger.info("Creating new researcher entry...")
            researcher = Scientist(
                name=researcher_name,
                normalized_name=slug(researcher_name)
            )
            # Flush so the seed has an id and is found by the co-author query
            # below (avoids creating a duplicate Scientist row).
            db.add(researcher)
            db.flush()

        # Process each co-author
        for coauthor_name, companies in coauthor_companies.items():
            # Get or create co-author
            coauthor = db.query(Scientist).filter_by(
                normalized_name=slug(coauthor_name)
            ).first()

            if not coauthor:
                coauthor = Scientist(
                    name=coauthor_name,
                    normalized_name=slug(coauthor_name)
                )
                # Flush now so coauthor.id is populated before it is used as a
                # FK in the ScientistCorporate link below (NotNullViolation otherwise).
                db.add(coauthor)
                db.flush()
                logger.info(f"  ✓ Created co-author: {coauthor_name}")

            # Process each company
            for company_name in companies:
                # Get or create corporate
                corporate = db.query(Corporate).filter_by(
                    normalized_name=slug(company_name)
                ).first()

                if not corporate:
                    corporate = Corporate(
                        name=company_name,
                        normalized_name=slug(company_name),
                        notes="Discovered from Transparence Santé"
                    )
                    # Flush now so corporate.id is populated before it is used
                    # as a FK in the ScientistCorporate link below.
                    db.add(corporate)
                    db.flush()
                    logger.info(f"    ✓ Added new corporate: {company_name}")

                # Check if link already exists
                existing_link = db.query(ScientistCorporate).filter_by(
                    scientist_id=coauthor.id,
                    corporate_id=corporate.id,
                    affiliation_type="transparence_sante"
                ).first()

                if not existing_link:
                    # Gather evidence for this company
                    evidence = []
                    total_amount = 0.0

                    declarations = coauthor_declarations.get(coauthor_name, [])
                    for decl in declarations:
                        if decl.company_name.lower() == company_name.lower():
                            evidence.append({
                                "declaration_id": decl.declaration_id,
                                "date": decl.date,
                                "amount": decl.amount,
                                "reason": decl.reason,
                                "reason_detail": decl.reason_detail,
                                "declaration_type": decl.declaration_type,
                                "sector": decl.sector,
                                "siren": decl.company_siren,
                                "status": decl.status,
                                "publication_date": decl.publication_date
                            })
                            total_amount += decl.amount

                    # Create link with evidence data
                    link = ScientistCorporate(
                        scientist_id=coauthor.id,
                        corporate_id=corporate.id,
                        affiliation_type="transparence_sante",
                        notes=f"Financial declarations: {len(evidence)} payment(s), total: {total_amount:,.2f}€",
                        evidence_data={"evidence": evidence} if evidence else None
                    )
                    objects_to_add.append(link)
                    new_links += 1

                    logger.info(
                        f"    ✓ Created link: {coauthor_name} → {company_name} "
                        f"({total_amount:,.2f}€)"
                    )
                else:
                    logger.info(f"    → Link already exists: {coauthor_name} → {company_name}")

        # Batch commit all objects at once
        for obj in objects_to_add:
            db.add(obj)
        db.commit()
        logger.info(f"\n✓ Created {new_links} new link(s)")

    except Exception as e:
        logger.error(f"Error adding to database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    return new_links


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover corporate connections from Transparence Santé"
    )
    parser.add_argument(
        "researcher",
        help="Researcher name to analyze"
    )
    parser.add_argument(
        "--max-coauthors",
        type=int,
        default=50,
        help="Maximum co-authors to scan (default: 50)"
    )
    parser.add_argument(
        "--min-amount",
        type=float,
        default=0.0,
        help="Minimum payment amount in euros (default: 10,000)"
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

    # Search Transparence Santé
    coauthor_companies, coauthor_declarations = discover_corporates_from_transparence_sante(
        args.researcher,
        max_coauthors=args.max_coauthors,
        min_amount=args.min_amount,
        skip_initials_only=not args.no_skip_initials
    )

    # Add to database if requested
    if args.add_to_db:
        add_transparence_sante_to_database(
            args.researcher,
            coauthor_companies,
            coauthor_declarations
        )
    else:
        logger.info("\n" + "="*80)
        logger.info("DONE (not added to database - use --add-to-db to persist)")
        logger.info("="*80)


if __name__ == "__main__":
    main()
