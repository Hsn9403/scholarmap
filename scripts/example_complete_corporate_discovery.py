#!/usr/bin/env python3
"""
Example: Complete corporate discovery workflow.

This script demonstrates how to discover corporate connections using
multiple sources in sequence:

1. Patents (existing)
2. Clinical Trials
3. Transparence Santé (NEW)

Each source provides different types of evidence and complements the others.
"""

from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.logger import logger


def discover_all_corporates(researcher_name: str, add_to_db: bool = False):
    """
    Discover corporates from all available sources.

    Args:
        researcher_name: Name of the researcher to analyze
        add_to_db: If True, persist results to database
    """
    logger.info("="*80)
    logger.info(f"COMPLETE CORPORATE DISCOVERY: {researcher_name}")
    logger.info("="*80)

    all_corporates = set()

    # =========================================================================
    # 1. CLINICAL TRIALS
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 1: Clinical Trials")
    logger.info("="*80)

    try:
        from discover_corporates_from_clinical_trials import (
            discover_corporates_from_coauthors_clinical_trials,
            add_clinical_trials_corporates_to_database
        )

        ct_coauthor_corps, ct_coauthor_links = discover_corporates_from_coauthors_clinical_trials(
            researcher_name,
            max_coauthors=30,
            max_studies_per_coauthor=20,
            skip_initials_only=True
        )

        # Collect all corporates
        for corps in ct_coauthor_corps.values():
            all_corporates.update(corps)

        logger.info(f"\n✓ Clinical Trials found {len(all_corporates)} unique corporates")

        # Add to database if requested
        if add_to_db and ct_coauthor_corps:
            for coauthor, corps in ct_coauthor_corps.items():
                logger.info(f"  → Adding {len(corps)} corporate(s) for {coauthor}")
                add_clinical_trials_corporates_to_database(
                    coauthor,
                    corps,
                    ct_coauthor_links.get(coauthor, [])
                )

    except Exception as e:
        logger.error(f"Error in Clinical Trials phase: {e}")

    # =========================================================================
    # 2. TRANSPARENCE SANTÉ
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 2: Transparence Santé")
    logger.info("="*80)

    ct_count = len(all_corporates)

    try:
        from discover_corporates_from_transparence_sante import (
            discover_corporates_from_transparence_sante,
            add_transparence_sante_to_database
        )

        ts_coauthor_companies, ts_coauthor_declarations = discover_corporates_from_transparence_sante(
            researcher_name,
            max_coauthors=50,
            min_amount=10000.0,
            skip_initials_only=True
        )

        # Collect all corporates
        for companies in ts_coauthor_companies.values():
            all_corporates.update(companies)

        ts_new = len(all_corporates) - ct_count
        logger.info(f"\n✓ Transparence Santé found {ts_new} NEW corporates")
        logger.info(f"  Total unique corporates: {len(all_corporates)}")

        # Add to database if requested
        if add_to_db and ts_coauthor_companies:
            add_transparence_sante_to_database(
                researcher_name,
                ts_coauthor_companies,
                ts_coauthor_declarations
            )

    except Exception as e:
        logger.error(f"Error in Transparence Santé phase: {e}")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Total unique corporates discovered: {len(all_corporates)}")

    if all_corporates:
        logger.info("\nCorporates:")
        for i, corporate in enumerate(sorted(all_corporates), 1):
            logger.info(f"  {i}. {corporate}")

    if not add_to_db:
        logger.info("\n⚠️  Results NOT saved to database (use --add-to-db to persist)")

    logger.info("="*80)

    return all_corporates


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover corporate connections from all available sources"
    )
    parser.add_argument(
        "researcher",
        help="Researcher name to analyze"
    )
    parser.add_argument(
        "--add-to-db",
        action="store_true",
        help="Add discovered corporates to database"
    )

    args = parser.parse_args()

    # Run complete discovery
    corporates = discover_all_corporates(
        args.researcher,
        add_to_db=args.add_to_db
    )

    # Exit with count
    exit(0 if corporates else 1)


if __name__ == "__main__":
    main()
