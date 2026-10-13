#!/usr/bin/env python3
"""
Interactive Phase 2.5 test: Validate a single coauthor against secondary sources.

Usage:
    python test_phase2_5_interactive.py "Cédric Tessier" a5110685580
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.logger import logger
from src.pathfinding.openalex_client import OpenAlexClient
from src.transparence_sante import TransparenceSanteClient
from src.clinical_trials.client import ClinicalTrialsClient
from src.pathfinding.coauthor_matcher_openai import CoauthorMatcherOpenAI


def test_coauthor_validation(coauthor_name: str, openalex_id: str):
    """Test Phase 2.5 validation for a single coauthor."""

    print("\n" + "=" * 80)
    print(f"PHASE 2.5 INTERACTIVE TEST: {coauthor_name}")
    print("=" * 80)

    # Step 1: Get coauthor from OpenAlex
    print(f"\n1️⃣  Fetching OpenAlex profile: {openalex_id}")
    try:
        oa_client = OpenAlexClient()
        coauthor_data = oa_client.get_author(openalex_id)
        if not coauthor_data:
            print(f"❌ OpenAlex profile not found: {openalex_id}")
            return

        oa_name = coauthor_data.get('display_name', coauthor_name)

        # Extract domains from topics
        topics = coauthor_data.get('topics', [])
        oa_domains = [t.get('display_name', '') for t in topics[:3]]  # Top 3 topics

        # Get years from counts_by_year
        counts_by_year = coauthor_data.get('counts_by_year', [])
        years = [c.get('year') for c in counts_by_year if c.get('year')]
        oa_years_min = min(years) if years else 2000
        oa_years_max = max(years) if years else 2026

        works_count = coauthor_data.get('works_count', 0)

        print(f"   ✓ Name: {oa_name}")
        print(f"   ✓ Domains: {oa_domains}")
        print(f"   ✓ Active: {oa_years_min}-{oa_years_max}")
        print(f"   ✓ Works: {works_count}")

    except Exception as e:
        print(f"❌ Error fetching OpenAlex: {e}")
        return

    # Initialize matcher
    matcher = CoauthorMatcherOpenAI()

    # Initialize variables
    validated_ts = []
    ts_declarations = []
    validated_ct = []
    ct_links = []
    validated_patents = []
    patents = []

    # Step 2: Search Transparence Santé
    print(f"\n2️⃣  Searching Transparence Santé...")
    try:
        ts_client = TransparenceSanteClient()
        first_name, last_name = coauthor_name.rsplit(" ", 1) if " " in coauthor_name else ("", coauthor_name)

        ts_result = ts_client.search_by_name(last_name, first_name, max_results=10)
        ts_declarations = ts_result.declarations if ts_result else []

        print(f"   Found {len(ts_declarations)} declarations")

        if ts_declarations:
            print("\n   Validating TS matches:")
            validated_ts = []
            for decl in ts_declarations:
                is_same = matcher.is_same_person(
                    oa_name=oa_name,
                    oa_domains=oa_domains,
                    oa_years_min=oa_years_min,
                    oa_years_max=oa_years_max,
                    candidate_name=decl.full_beneficiary_name,
                    candidate_year=int(decl.date.split('-')[0]) if decl.date else 2020,
                    candidate_context=f"Sector: {decl.sector}, Profession: {decl.beneficiary_profession}"
                )

                status = "✅ ACCEPTED" if is_same else "❌ REJECTED"
                print(f"     {status}: {decl.full_beneficiary_name} ({decl.sector})")

                if is_same:
                    validated_ts.append(decl)

            print(f"   → Validated: {len(validated_ts)}/{len(ts_declarations)}")

    except Exception as e:
        print(f"❌ Error searching TS: {e}")

    # Step 3: Search Clinical Trials
    print(f"\n3️⃣  Searching Clinical Trials...")
    try:
        ct_client = ClinicalTrialsClient()
        ct_result = ct_client.find_corporate_links(coauthor_name)
        ct_links = ct_result.corporate_links if ct_result else []

        print(f"   Found {len(ct_links)} trial links")

        if ct_links:
            print("\n   Validating CT matches:")
            validated_ct = []
            for link in ct_links:
                is_same = matcher.is_same_person(
                    oa_name=oa_name,
                    oa_domains=oa_domains,
                    oa_years_min=oa_years_min,
                    oa_years_max=oa_years_max,
                    candidate_name=link.researcher,
                    candidate_year=2020,  # CT doesn't always have year
                    candidate_context=link.study_title
                )

                status = "✅ ACCEPTED" if is_same else "❌ REJECTED"
                print(f"     {status}: {link.researcher} - {link.study_title[:50]}...")

                if is_same:
                    validated_ct.append(link)

            print(f"   → Validated: {len(validated_ct)}/{len(ct_links)}")

    except Exception as e:
        print(f"❌ Error searching CT: {e}")

    # Step 4: Search Patents (via SerpAPI)
    print(f"\n4️⃣  Searching Patents...")
    try:
        from src.patents.client import PatentsClient
        patents_client = PatentsClient()
        patents_data = patents_client.fetch_patents_data(coauthor_name, max_patents=10)
        patents = patents_data.top_patents if patents_data else []

        print(f"   Found {len(patents)} patents")

        if patents:
            print("\n   Validating Patent matches (parallel)...")
            from concurrent.futures import ThreadPoolExecutor

            def validate_patent(args):
                i, patent = args
                patent_title = getattr(patent, 'title', 'N/A')
                patent_year = getattr(patent, 'year', 2020) or 2020
                patent_id = getattr(patent, 'patent_id', 'N/A')
                inventors = getattr(patent, 'inventors', [])

                is_same = matcher.is_same_person(
                    oa_name=oa_name,
                    oa_domains=oa_domains,
                    oa_years_min=oa_years_min,
                    oa_years_max=oa_years_max,
                    candidate_name=coauthor_name,
                    candidate_year=patent_year,
                    candidate_context=f"Title: {patent_title}"
                )

                return (i, is_same, patent, patent_title, patent_id, patent_year, inventors)

            validated_patents = []
            results = []

            # Parallelize with 4 workers
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(validate_patent, enumerate(patents, 1)))

            # Sort by index and display
            results.sort(key=lambda x: x[0])
            for i, is_same, patent, patent_title, patent_id, patent_year, inventors in results:
                status = "✅ ACCEPTED" if is_same else "❌ REJECTED"
                print(f"\n     [{i}] {status}")
                print(f"         Title: {patent_title[:60]}...")
                print(f"         Patent ID: {patent_id}")
                print(f"         Year: {patent_year}")
                print(f"         Inventors: {inventors}")

                if is_same:
                    validated_patents.append(patent)

            print(f"\n   → Validated: {len(validated_patents)}/{len(patents)}")

    except Exception as e:
        print(f"❌ Error searching Patents: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Transparence Santé:  {len(validated_ts)} / {len(ts_declarations)} accepted")
    print(f"Clinical Trials:     {len(validated_ct)} / {len(ct_links)} accepted")
    print(f"Patents:             {len(validated_patents)} / {len(patents)} accepted")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_phase2_5_interactive.py <name> <openalex_id>")
        print("Example: python test_phase2_5_interactive.py 'Cédric Tessier' a5110685580")
        sys.exit(1)

    name = sys.argv[1]
    openalex_id = sys.argv[2]

    test_coauthor_validation(name, openalex_id)
