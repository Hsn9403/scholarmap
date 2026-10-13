#!/usr/bin/env python3
"""
Build Ultra-Complete Graph - All-in-One Researcher Analysis.

This script performs COMPLETE research and analysis for a researcher:

PHASE 1: Data Collection
  1. Scholar: Publications + Co-authors
  2. Patents: Inventor patents + assignees
  3. Clinical Trials: Co-authors as PIs → Corporates
  4. Transparence Santé: Co-authors financial declarations → Corporates

PHASE 2: Database Storage
  - All corporates discovered are saved to database
  - Links are created with full evidence/metadata

PHASE 3: Graph Generation
  - Interactive HTML graph with all connections
  - Nodes: Publications, Patents, People, Corporates
  - Edges: Co-authorship, Inventorship, Industry links

Usage:
    python3 build_ultra_complete_graph.py "Researcher Name"
    python3 build_ultra_complete_graph.py "Researcher Name" --max-publications 100
    python3 build_ultra_complete_graph.py "Researcher Name" --skip-clinical-trials
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.logger import logger
from scripts.modules.phase1_data_collection import collect_all_data
from scripts.modules.phase2_database_storage import store_all_to_database
from scripts.modules.phase3_graph_generation import generate_complete_graph


def build_ultra_complete_graph(
    researcher_name: str,
    max_publications: int = 100,
    max_patents: int = 10,
    max_coauthors_ct: int = 30,
    max_coauthors_ts: int = 50,
    min_amount_ts: float = 10000.0,
    skip_clinical_trials: bool = False,
    skip_transparence_sante: bool = False,
    skip_patents: bool = False,
    enrich_persons: bool = True,
    use_db_only: bool = False,
    scholar_id: str = None,
    openalex_id: str = None,
):
    """
    Build ultra-complete graph with all available data sources.

    Args:
        researcher_name: Name of the researcher
        max_publications: Max Scholar publications (default: 100)
        max_patents: Max patents to analyze (default: 10, 0 to skip)
        max_coauthors_ct: Max co-authors for Clinical Trials (default: 30)
        max_coauthors_ts: Max co-authors for Transparence Santé (default: 50)
        min_amount_ts: Min payment in Transparence Santé in € (default: 10,000)
        skip_clinical_trials: Skip Clinical Trials search
        skip_transparence_sante: Skip Transparence Santé search
        skip_patents: Skip Patents search
        enrich_persons: Enrich co-author nodes with Scholar data
    """
    logger.info("="*80)
    logger.info("ULTRA-COMPLETE GRAPH GENERATION")
    logger.info(f"Researcher: {researcher_name}")
    logger.info("="*80)

    # =========================================================================
    # PHASE 1: DATA COLLECTION
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 1: DATA COLLECTION")
    logger.info("="*80)

    data = collect_all_data(
        researcher_name=researcher_name,
        max_publications=max_publications,
        max_patents=max_patents if not skip_patents else 0,
        max_coauthors_ct=max_coauthors_ct,
        max_coauthors_ts=max_coauthors_ts,
        min_amount_ts=min_amount_ts,
        skip_clinical_trials=skip_clinical_trials,
        skip_transparence_sante=skip_transparence_sante,
        use_db_only=use_db_only,
        scholar_id=scholar_id,
        openalex_id=openalex_id,
    )

    # =========================================================================
    # PHASE 2: DATABASE STORAGE
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 2: DATABASE STORAGE")
    logger.info("="*80)

    store_all_to_database(
        researcher_name=researcher_name,
        data=data
    )

    # =========================================================================
    # PHASE 3: GRAPH GENERATION
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 3: GRAPH GENERATION")
    logger.info("="*80)

    output_file = generate_complete_graph(
        researcher_name=researcher_name,
        scholar_data=data['scholar'],
        patents_data=data.get('patents'),
        enrich_persons=enrich_persons and not use_db_only,  # Disable enrichment in DB-only mode
        discover_coauthor_patents_api=True
    )

    # =========================================================================
    # PHASE 4: EXCEL REPORT GENERATION
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("PHASE 4: EXCEL REPORT GENERATION")
    logger.info("="*80)

    excel_file = None
    try:
        from src.export.excel import ExcelExporter
        from src.models import PatentsData, PatentItem
        from src.helpers import slug
        from src.database.database import SessionLocal
        from src.database.models import Scientist, Patent as DBPatent

        # Get patents from DB (since API might be exhausted)
        db = SessionLocal()
        patents_list = []

        try:
            scientist = db.query(Scientist).filter(
                (Scientist.name == researcher_name) |
                (Scientist.normalized_name == slug(researcher_name))
            ).first()

            if scientist:
                db_patents = db.query(DBPatent).join(DBPatent.inventors).filter(
                    Scientist.id == scientist.id
                ).all()

                # Convert DB patents to Patent model
                for db_patent in db_patents:
                    # Claims: stored as newline-separated text
                    claims_top3 = []
                    if db_patent.claims_excerpt:
                        claims_top3 = [c.strip() for c in db_patent.claims_excerpt.split("\n\n") if c.strip()][:3]

                    # All inventors (including main researcher): prefer raw inventors_json
                    # fall back to DB inventor relationships
                    if db_patent.inventors_json:
                        raw_inventors = db_patent.inventors_json if isinstance(db_patent.inventors_json, list) else []
                        co_inventors = [
                            inv if isinstance(inv, str) else inv.get("name", "")
                            for inv in raw_inventors
                        ]
                        co_inventors = [c for c in co_inventors if c.strip()]
                    else:
                        co_inventors = [inv.name for inv in db_patent.inventors]

                    # Citing companies: assignees of patents that cite this one (forward citations)
                    citing_list = db_patent.citing_patents_json or []
                    citing_assignees = list({
                        c.get("assignee", "").strip()
                        for c in citing_list
                        if isinstance(c, dict) and c.get("assignee", "").strip()
                    })

                    # Cited companies: assignees of patents cited by this one (backward citations)
                    cited_list = db_patent.cited_patents_json or []
                    cited_assignees = list({
                        c.get("assignee", "").strip()
                        for c in cited_list
                        if isinstance(c, dict) and c.get("assignee", "").strip()
                    })

                    patent = PatentItem(
                        title=db_patent.title,
                        link=db_patent.link or "",
                        patent_id=db_patent.patent_id or "",
                        current_assignee=db_patent.assignee,
                        publication_date=str(db_patent.publication_date) if db_patent.publication_date else None,
                        claims_top3=claims_top3,
                        co_inventors=co_inventors,
                        cited_assignees=cited_assignees,
                        citing_assignees=citing_assignees,
                    )
                    patents_list.append(patent)

                logger.info(f"Loaded {len(patents_list)} patents from DB for Excel report")
        finally:
            db.close()

        # Use DB patents if available, otherwise use API patents
        if patents_list:
            patents_obj = PatentsData(
                top_patents=patents_list,
                patents_total=len(patents_list)
            )
        elif data.get('patents'):
            patents_obj = PatentsData(
                top_patents=data.get('patents', []),
                patents_total=len(data.get('patents', []))
            )
        else:
            patents_obj = PatentsData(top_patents=[], patents_total=0)

        # Generate Excel report
        safe_name = slug(researcher_name)
        excel_filename = f"{safe_name}_report.xlsx"

        # Save to webapp static directory for serving
        webapp_reports_dir = Path(__file__).parent.parent / "webapp" / "static" / "reports"
        webapp_reports_dir.mkdir(parents=True, exist_ok=True)
        excel_path = webapp_reports_dir / excel_filename

        exporter = ExcelExporter()
        exporter.write(
            out_path=str(excel_path),
            researcher_name=researcher_name,
            scholar=data['scholar'],
            patents=patents_obj
        )

        excel_file = excel_filename
        logger.info(f"✓ Excel report generated: {excel_filename}")
        logger.info(f"  Saved to: {excel_path}")

    except Exception as e:
        logger.warning(f"Could not generate Excel report: {e}")
        import traceback
        traceback.print_exc()

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("✓ ULTRA-COMPLETE GRAPH GENERATED")
    logger.info("="*80)

    print("\n📊 Data Collection Summary:")
    print(f"  • Publications: {len(data['scholar'].top_publications) if data['scholar'] else 0}")
    print(f"  • Co-authors: {len(data['scholar'].coauthors) if data['scholar'] else 0}")
    print(f"  • Patents: {len(data.get('patents', [])) if data.get('patents') else 0}")

    if not skip_clinical_trials:
        ct_corporates = sum(len(corps) for corps in data.get('clinical_trials_corporates', {}).values())
        print(f"  • Clinical Trials corporates: {ct_corporates}")

    if not skip_transparence_sante:
        ts_corporates = sum(len(corps) for corps in data.get('transparence_sante_corporates', {}).values())
        print(f"  • Transparence Santé corporates: {ts_corporates}")

    print(f"\n📁 Output files:")
    print(f"  Graph: {output_file}")
    if excel_file:
        print(f"  Excel: webapp/static/reports/{excel_file}")

    print("\n💡 Open the HTML file to view the interactive graph.")
    if excel_file:
        print("💡 Excel report is available for download via the webapp.")
    print("="*80)

    return output_file


def main():
    """Main execution with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build ultra-complete graph with all data sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full analysis with default settings
  python3 build_ultra_complete_graph.py "Andre Imbert"

  # With custom parameters
  python3 build_ultra_complete_graph.py "Edgar Duval" \\
    --max-publications 150 \\
    --max-coauthors-ct 50 \\
    --min-amount-ts 20000

  # Skip some data sources
  python3 build_ultra_complete_graph.py "Researcher Name" \\
    --skip-clinical-trials \\
    --skip-patents
        """
    )

    parser.add_argument(
        "researcher_name",
        help="Name of the researcher to analyze"
    )

    parser.add_argument(
        "--max-publications",
        type=int,
        default=100,
        help="Maximum publications from Scholar (default: 100)"
    )

    parser.add_argument(
        "--max-patents",
        type=int,
        default=10,
        help="Maximum patents to analyze (default: 10, use 0 to skip)"
    )

    parser.add_argument(
        "--max-coauthors-ct",
        type=int,
        default=30,
        help="Maximum co-authors for Clinical Trials (default: 30)"
    )

    parser.add_argument(
        "--max-coauthors-ts",
        type=int,
        default=50,
        help="Maximum co-authors for Transparence Santé (default: 50)"
    )

    parser.add_argument(
        "--min-amount-ts",
        type=float,
        default=10000.0,
        help="Minimum payment amount for Transparence Santé in € (default: 10000)"
    )

    parser.add_argument(
        "--skip-clinical-trials",
        action="store_true",
        help="Skip Clinical Trials search"
    )

    parser.add_argument(
        "--skip-transparence-sante",
        action="store_true",
        help="Skip Transparence Santé search"
    )

    parser.add_argument(
        "--skip-patents",
        action="store_true",
        help="Skip Patents search"
    )

    parser.add_argument(
        "--no-enrich-persons",
        dest="enrich_persons",
        action="store_false",
        default=True,
        help="Skip enriching co-author nodes with Scholar data"
    )

    parser.add_argument(
        "--use-db-only",
        action="store_true",
        help="Use only database data, no SerpAPI calls (saves credits)"
    )

    args = parser.parse_args()

    # Build the ultra-complete graph
    build_ultra_complete_graph(
        researcher_name=args.researcher_name,
        max_publications=args.max_publications,
        max_patents=args.max_patents,
        max_coauthors_ct=args.max_coauthors_ct,
        max_coauthors_ts=args.max_coauthors_ts,
        min_amount_ts=args.min_amount_ts,
        skip_clinical_trials=args.skip_clinical_trials,
        skip_transparence_sante=args.skip_transparence_sante,
        skip_patents=args.skip_patents,
        enrich_persons=args.enrich_persons,
        use_db_only=args.use_db_only
    )


if __name__ == "__main__":
    main()
