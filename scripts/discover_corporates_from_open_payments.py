#!/usr/bin/env python3
"""
Discover corporate connections from CMS Open Payments (U.S. Sunshine Act).

This script:
1. Retrieves co-authors of a researcher (with successful name disambiguation)
2. For each co-author with first name + last name, searches CMS Open Payments
3. Identifies companies that paid >$10,000 to the co-author
4. Adds them to the database with evidence
5. Creates links: Researcher → Co-author → Corporate (via Open Payments)

METHODOLOGY:
- Only processes co-authors where disambiguation succeeded (full name available)
- Searches for financial declarations over $10,000 threshold (equivalent to
  the €10,000 threshold used for Transparence Santé)
- Evidence includes: amount (USD), nature of payment, record ID, date, program year
- All payments are traceable to the official U.S. federal CMS Open Payments database
- Source: https://openpaymentsdata.cms.gov (Sunshine Act / ACA §6002)
"""

from pathlib import Path
from typing import Dict, List, Set, Tuple
import re

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.open_payments import (
    OpenPaymentsClient,
    OpenPaymentsRecord,
    OpenPaymentsSearchResult,
)
from src.open_payments.client import DEFAULT_YEAR
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
        full_name: Full name (e.g., "John Smith", "Mary-Jane Watson")

    Returns:
        Tuple of (first_name, last_name)
    """
    full_name = " ".join(full_name.split())
    parts = full_name.split()

    if len(parts) < 2:
        return "", ""

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
    clean_name = name.replace(" ", "").replace(".", "")

    if len(clean_name) < 4:
        return False

    if re.match(r'^[A-Z]{1,2}[\s\.-]*[A-Z][a-z]+$', name):
        return False

    parts = name.split()
    if len(parts) < 2:
        return False

    if len(parts[0].replace(".", "")) < 2:
        return False

    return True


def discover_corporates_from_open_payments(
    researcher_name: str,
    max_coauthors: int = 50,
    min_amount_usd: float = 10000.0,
    program_year: int = DEFAULT_YEAR,
    skip_initials_only: bool = True,
    use_db_only: bool = False,
    scholar_data=None,
) -> Tuple[Dict[str, Set[str]], Dict[str, List[OpenPaymentsRecord]]]:
    """
    Discover corporate connections from co-authors' CMS Open Payments records.

    Creates paths: Researcher → Co-author → Corporate (via Open Payments)

    Args:
        researcher_name: Name of the main researcher
        max_coauthors: Maximum co-authors to scan
        min_amount_usd: Minimum payment amount in USD (default: $10,000)
        program_year: CMS program year to query (default: most recent)
        skip_initials_only: If True, skip co-authors with initials only
        use_db_only: If True, load co-authors from DB instead of Scholar API
        scholar_data: Pre-fetched scholar data (avoids extra API call)

    Returns:
        Tuple of:
        - Dict mapping co-author name → set of companies
        - Dict mapping co-author name → list of OpenPaymentsRecord
    """
    logger.info("=" * 80)
    logger.info("DISCOVERING CORPORATES FROM CMS OPEN PAYMENTS (U.S. SUNSHINE ACT)")
    logger.info(f"Main Researcher: {researcher_name}")
    logger.info(f"Payment threshold: >=${min_amount_usd:,.0f} USD  |  Year: {program_year}")
    logger.info("=" * 80)

    op_client = OpenPaymentsClient()

    logger.info(f"\n1. Finding co-authors of {researcher_name}...")

    if scholar_data is not None:
        logger.info(f"✓ Reusing existing scholar data: {len(scholar_data.coauthors or [])} co-authors")
    elif use_db_only:
        from src.database.adapters import scientist_to_scholar_data
        scholar_data = scientist_to_scholar_data(
            scientist_name=researcher_name,
            use_db_only=use_db_only,
        )
        if not scholar_data:
            logger.error(f"Researcher not found in database: {researcher_name}")
            return {}, {}
        logger.info(f"✓ Loaded {len(scholar_data.coauthors)} co-authors from DB")
    else:
        scholar_client = ScholarClient()
        candidates = scholar_client.find_candidates(researcher_name, num=5)
        if not candidates:
            logger.error(f"Researcher not found: {researcher_name}")
            return {}, {}

        scholar_data = scholar_client.fetch_author_data(
            candidates[0].author_id,
            num_articles=50,
        )
        logger.info(f"✓ Found {len(scholar_data.coauthors)} co-authors from API")

    name_resolver = NameResolver(use_db_only=use_db_only, skip_scholar_search=True)
    publication_resolver = CoauthorNameResolver(scholar_data)

    coauthor_companies: Dict[str, Set[str]] = {}
    coauthor_records: Dict[str, List[OpenPaymentsRecord]] = {}

    processed = 0
    skipped_initials = 0
    skipped_no_name = 0
    found_declarations = 0

    for i, coauthor in enumerate(scholar_data.coauthors[:max_coauthors], 1):
        resolved_name = coauthor.name
        source = "original"

        pub_resolved = publication_resolver.resolve(coauthor.name)
        if pub_resolved and pub_resolved != coauthor.name:
            resolved_name = pub_resolved
            source = "publications"
        else:
            api_resolved, api_source = name_resolver.resolve(
                coauthor.name,
                scholar_id=coauthor.scholar_id,
                context_name=researcher_name,
            )
            if api_resolved != coauthor.name:
                resolved_name = api_resolved
                source = api_source

        if skip_initials_only and not is_valid_full_name(resolved_name):
            skipped_initials += 1
            logger.debug(f"⊘ Skipping '{resolved_name}' (initials only or invalid)")
            continue

        first_name, last_name = extract_first_last_name(resolved_name)
        if not first_name or not last_name:
            skipped_no_name += 1
            logger.debug(f"⊘ Skipping '{resolved_name}' (cannot extract first/last name)")
            continue

        processed += 1

        if source != "original":
            logger.info(f"\n[{processed}] Scanning: {coauthor.name} → {resolved_name} (via {source})")
        else:
            logger.info(f"\n[{processed}] Scanning: {resolved_name}")

        try:
            result = op_client.search_by_name(
                last_name=last_name,
                first_name=first_name,
                min_amount_usd=min_amount_usd,
                program_year=program_year,
            )

            # If no result and name has a middle name/initial, retry without it
            if not result.records:
                for variant in name_variants(resolved_name)[1:]:
                    v_first, v_last = extract_first_last_name(variant)
                    if not v_first or not v_last:
                        continue
                    logger.info(
                        f"  ↩ No results — retrying as '{v_first} {v_last}' (no middle name)"
                    )
                    result = op_client.search_by_name(
                        last_name=v_last,
                        first_name=v_first,
                        min_amount_usd=min_amount_usd,
                        program_year=program_year,
                    )
                    if result.records:
                        logger.info(f"  ✓ Found results with variant '{variant}'")
                        break

            if result.records:
                coauthor_companies[coauthor.name] = result.companies_found
                coauthor_records[coauthor.name] = result.records
                found_declarations += 1

                logger.info(
                    f"  ✓ Found {len(result.companies_found)} company(ies): "
                    f"{', '.join(sorted(result.companies_found))}"
                )
                logger.info(f"    Total amount: ${result.total_amount_usd:,.2f}")
            else:
                logger.info(f"  → No records >=${min_amount_usd:,.0f} found")

        except Exception as e:
            logger.warning(f"  ✗ Error scanning {resolved_name}: {e}")

    total_companies: Set[str] = set()
    for companies in coauthor_companies.values():
        total_companies.update(companies)

    logger.info(f"\n{'=' * 80}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 80}")
    logger.info(f"Co-authors processed: {processed}")
    logger.info(f"Skipped (initials only): {skipped_initials}")
    logger.info(f"Skipped (name extraction failed): {skipped_no_name}")
    logger.info(f"Co-authors with Open Payments records: {found_declarations}")
    logger.info(f"Total unique companies: {len(total_companies)}")
    if total_companies:
        logger.info(f"Companies: {', '.join(sorted(total_companies))}")

    return coauthor_companies, coauthor_records


def add_open_payments_to_database(
    researcher_name: str,
    coauthor_companies: Dict[str, Set[str]],
    coauthor_records: Dict[str, List[OpenPaymentsRecord]],
) -> int:
    """
    Add CMS Open Payments corporate connections to the database.

    Creates links: Scientist (researcher) → Scientist (co-author) → Corporate

    Args:
        researcher_name: Name of the main researcher
        coauthor_companies: Dict mapping co-author name → set of companies
        coauthor_records: Dict mapping co-author name → list of records

    Returns:
        Number of new links created
    """
    if not coauthor_companies:
        logger.info("No companies to add.")
        return 0

    logger.info("\n3. Adding to database...")

    db = SessionLocal()
    new_links = 0

    try:
        # ── Batch lookup : tout charger en mémoire en quelques requêtes ──────
        all_coauthor_names = list(coauthor_companies.keys())
        all_company_names  = list({c for companies in coauthor_companies.values() for c in companies})

        all_slugs_sci  = {slug(researcher_name)} | {slug(n) for n in all_coauthor_names}
        all_slugs_corp = {slug(n) for n in all_company_names}

        existing_scientists = {
            s.normalized_name: s
            for s in db.query(Scientist).filter(
                Scientist.normalized_name.in_(all_slugs_sci)
            ).all()
        }
        existing_corporates = {
            c.normalized_name: c
            for c in db.query(Corporate).filter(
                Corporate.normalized_name.in_(all_slugs_corp)
            ).all()
        }

        # ── Researcher ────────────────────────────────────────────────────────
        researcher = existing_scientists.get(slug(researcher_name))
        if not researcher:
            logger.warning(f"Main researcher not found in DB: {researcher_name}")
            researcher = Scientist(
                name=researcher_name,
                normalized_name=slug(researcher_name),
            )
            db.add(researcher)
            db.flush()
            existing_scientists[slug(researcher_name)] = researcher

        # ── Co-auteurs et corporates manquants : flush pour obtenir les IDs ──
        for coauthor_name in all_coauthor_names:
            if slug(coauthor_name) not in existing_scientists:
                coauthor = Scientist(
                    name=coauthor_name,
                    normalized_name=slug(coauthor_name),
                )
                db.add(coauthor)
                db.flush()
                existing_scientists[slug(coauthor_name)] = coauthor
                logger.info(f"  ✓ Created co-author: {coauthor_name}")

        for company_name in all_company_names:
            if slug(company_name) not in existing_corporates:
                corporate = Corporate(
                    name=company_name,
                    normalized_name=slug(company_name),
                    notes="Discovered from CMS Open Payments (U.S. Sunshine Act)",
                )
                db.add(corporate)
                db.flush()
                existing_corporates[slug(company_name)] = corporate
                logger.info(f"    ✓ Added new corporate: {company_name}")

        # ── Batch lookup des liens existants ──────────────────────────────────
        sci_ids  = {s.id for s in existing_scientists.values()}
        corp_ids = {c.id for c in existing_corporates.values()}
        existing_link_keys = {
            (lk.scientist_id, lk.corporate_id)
            for lk in db.query(ScientistCorporate).filter(
                ScientistCorporate.scientist_id.in_(sci_ids),
                ScientistCorporate.corporate_id.in_(corp_ids),
                ScientistCorporate.affiliation_type == "open_payments",
            ).all()
        }

        # ── Construire tous les nouveaux liens en mémoire ─────────────────────
        new_link_objects = []
        for coauthor_name, companies in coauthor_companies.items():
            coauthor = existing_scientists[slug(coauthor_name)]
            for company_name in companies:
                corporate = existing_corporates[slug(company_name)]
                key = (coauthor.id, corporate.id)

                if key in existing_link_keys:
                    logger.info(f"    → Link already exists: {coauthor_name} → {company_name}")
                    continue

                evidence = []
                total_amount = 0.0
                for rec in coauthor_records.get(coauthor_name, []):
                    if rec.company_name.lower() == company_name.lower():
                        evidence.append({
                            "record_id": rec.record_id,
                            "date": rec.date,
                            "amount_usd": rec.amount_usd,
                            "nature_of_payment": rec.nature_of_payment,
                            "recipient_type": rec.recipient_type,
                            "recipient_specialty": rec.recipient_specialty,
                            "recipient_state": rec.recipient_state,
                            "company_state": rec.company_state,
                            "program_year": rec.program_year,
                        })
                        total_amount += rec.amount_usd

                new_link_objects.append(ScientistCorporate(
                    scientist_id=coauthor.id,
                    corporate_id=corporate.id,
                    affiliation_type="open_payments",
                    notes=(
                        f"CMS Open Payments: {len(evidence)} payment(s), "
                        f"total: ${total_amount:,.2f} USD"
                    ),
                    evidence_data={"evidence": evidence} if evidence else None,
                ))
                existing_link_keys.add(key)
                new_links += 1
                logger.info(
                    f"    ✓ Created link: {coauthor_name} → {company_name} "
                    f"(${total_amount:,.2f} USD)"
                )

        # ── Un seul commit pour tout ──────────────────────────────────────────
        if new_link_objects:
            db.add_all(new_link_objects)
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
        description="Discover corporate connections from CMS Open Payments (U.S. Sunshine Act)"
    )
    parser.add_argument(
        "researcher",
        help="Researcher name to analyze",
    )
    parser.add_argument(
        "--max-coauthors",
        type=int,
        default=50,
        help="Maximum co-authors to scan (default: 50)",
    )
    parser.add_argument(
        "--min-amount",
        type=float,
        default=10000.0,
        help="Minimum payment amount in USD (default: 10,000)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_YEAR,
        help=f"CMS program year to query (default: {DEFAULT_YEAR})",
    )
    parser.add_argument(
        "--no-skip-initials",
        action="store_true",
        help="Include co-authors with initials only (will attempt name resolution)",
    )
    parser.add_argument(
        "--add-to-db",
        action="store_true",
        help="Add discovered corporates to database",
    )

    args = parser.parse_args()

    coauthor_companies, coauthor_records = discover_corporates_from_open_payments(
        args.researcher,
        max_coauthors=args.max_coauthors,
        min_amount_usd=args.min_amount,
        program_year=args.year,
        skip_initials_only=not args.no_skip_initials,
    )

    if args.add_to_db:
        add_open_payments_to_database(
            args.researcher,
            coauthor_companies,
            coauthor_records,
        )
    else:
        logger.info("\n" + "=" * 80)
        logger.info("DONE (not added to database — use --add-to-db to persist)")
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
