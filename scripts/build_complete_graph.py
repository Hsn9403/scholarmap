#!/usr/bin/env python3
"""
Build complete graph with Scholar + Patents + Industry Connections.

This script demonstrates the full workflow:
1. Fetch Scholar data (publications, co-authors)
2. Fetch Patents data
3. Build graph with build_graph_data()
4. Enrich with industry connections from DB
5. Visualize the complete graph
"""
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("Warning: python-dotenv not installed")

from src.scholar.client import ScholarClient
from src.patents.client import PatentsClient
from src.graph.builder import build_graph_data
from src.graph.visualizer import render_graph_html
from src.graph.enrich_with_industry import enrich_graph_with_industry_connections
from src.database.database import SessionLocal
from src.logger import logger
from src.helpers import slug

# Import patent-based corporate discovery
import sys
import importlib.util
spec = importlib.util.spec_from_file_location(
    "discover_corporates_from_patents",
    Path(__file__).parent / "discover_corporates_from_patents.py"
)
if spec and spec.loader:
    discover_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discover_module)
    discover_corporates_from_patents_func = discover_module.discover_corporates_from_patents
    add_corporates_to_database_func = discover_module.add_corporates_to_database
else:
    discover_corporates_from_patents_func = None
    add_corporates_to_database_func = None


def build_complete_graph_for_researcher(
    researcher_name: str,
    max_publications: int = 100,
    max_patents: int = 10,
    enrich_persons: bool = False,
    discover_corporates_from_patents: bool = True
):
    """
    Build a complete graph for a researcher including industry connections.

    Args:
        researcher_name: Name of the researcher.
        max_publications: Max Scholar publications to include.
        max_patents: Max patents to include.
        enrich_persons: Whether to enrich person nodes with Scholar data.
        discover_corporates_from_patents: Whether to auto-discover corporates from patents.
    """
    logger.info("=" * 80)
    logger.info(f"Building complete graph for: {researcher_name}")
    logger.info("=" * 80)

    # Step 1: Fetch Scholar data
    logger.info("Step 1: Fetching Google Scholar data...")
    scholar_client = ScholarClient()

    try:
        candidates = scholar_client.find_candidates(researcher_name, num=5)
        if not candidates:
            logger.error(f"No Scholar profile found for: {researcher_name}")
            return

        author_id = candidates[0].author_id
        logger.info(f"Found Scholar profile: {candidates[0].title}")

        scholar_data = scholar_client.fetch_author_data(
            author_id,
            num_articles=max_publications
        )
        logger.info(f"✓ Retrieved {len(scholar_data.top_publications)} publications")

    except Exception as e:
        logger.error(f"Error fetching Scholar data: {e}")
        scholar_data = None

    # Step 2: Fetch Patents data
    logger.info("\nStep 2: Fetching Patents data...")
    from src.models import PatentsData
    patents_client = PatentsClient()

    if max_patents > 0:
        try:
            patents_data = patents_client.fetch_patents_data(
                inventor_name=researcher_name,
                max_patents=max_patents
            )
            logger.info(f"✓ Retrieved {len(patents_data.top_patents)} patents")
        except Exception as e:
            logger.warning(f"Could not fetch patents: {e}")
            patents_data = PatentsData(top_patents=[], patents_total=0)
    else:
        logger.info("Skipping patents (max_patents=0)")
        patents_data = PatentsData(top_patents=[], patents_total=0)

    # Step 3: Build base graph from Scholar + Patents
    logger.info("\nStep 3: Building base graph from Scholar + Patents...")
    graph = build_graph_data(
        researcher_name=researcher_name,
        scholar=scholar_data,
        patents=patents_data,
        max_patents=max_patents,
        patents_client=patents_client,
        enrich_persons=enrich_persons,
        scholar_client=scholar_client if enrich_persons else None
    )

    logger.info(f"✓ Base graph built:")
    logger.info(f"  Nodes: {len(graph.get('nodes', []))}")
    logger.info(f"  Edges: {len(graph.get('edges', []))}")

    # Step 3.5: Auto-discover corporates from patents (OPTIONAL)
    if discover_corporates_from_patents and discover_corporates_from_patents_func:
        logger.info("\nStep 3.5: Auto-discovering corporates from patents...")
        try:
            corporates_found = discover_corporates_from_patents_func(
                researcher_name=researcher_name,
                max_patents=max_patents if max_patents > 0 else 20
            )
            if corporates_found and add_corporates_to_database_func:
                new_links = add_corporates_to_database_func(
                    researcher_name=researcher_name,
                    corporates=corporates_found,
                    affiliation_type="patent_assignee"
                )
                logger.info(f"✓ Auto-discovered {len(corporates_found)} corporates from patents")
                logger.info(f"✓ Added {new_links} new corporate connections to database")
        except Exception as e:
            logger.warning(f"Could not auto-discover corporates from patents: {e}")
            logger.info("Continuing without patent-based corporate discovery...")

    # Step 4: Enrich with industry connections from DB
    logger.info("\nStep 4: Enriching with industry connections from database...")
    db = SessionLocal()
    try:
        enriched_graph = enrich_graph_with_industry_connections(
            graph=graph,
            db=db,
            add_coauthor_nodes=False  # Only enrich existing co-authors (prevents mixing researchers)
        )

        logger.info(f"✓ Graph enriched:")
        logger.info(f"  Total nodes: {enriched_graph['meta']['nodes_count']}")
        logger.info(f"  Total edges: {enriched_graph['meta']['edges_count']}")
        if enriched_graph['meta'].get('corporates_count', 0) > 0:
            logger.info(f"  Corporate nodes: {enriched_graph['meta']['corporates_count']}")

    except Exception as e:
        logger.error(f"Error enriching graph: {e}")
        enriched_graph = graph
    finally:
        db.close()

    # Step 5: Visualize the complete graph
    logger.info("\nStep 5: Creating visualization...")

    # Save in project root with format: firstname_lastname_network.html
    html_path = Path(f"{slug(researcher_name)}_network.html")

    render_graph_html(
        graph=enriched_graph,
        out_html=str(html_path)
    )

    logger.info("=" * 80)
    logger.info("✓ COMPLETE GRAPH GENERATED")
    logger.info("=" * 80)

    print(f"\n📊 Final Graph Summary:")
    print(f"  • Total nodes: {enriched_graph['meta']['nodes_count']}")
    print(f"  • Total edges: {enriched_graph['meta']['edges_count']}")
    print(f"  • Publications: {len([n for n in enriched_graph['nodes'] if n.get('type') == 'publication'])}")
    print(f"  • Patents: {len([n for n in enriched_graph['nodes'] if n.get('type') == 'patent'])}")
    print(f"  • People: {len([n for n in enriched_graph['nodes'] if n.get('type') == 'person'])}")
    print(f"  • Corporates: {enriched_graph['meta'].get('corporates_count', 0)}")

    print(f"\n📁 Output file:")
    print(f"  {html_path}")
    print(f"\n💡 Open the HTML file to view the interactive graph.")
    print(f"  The graph includes:")
    print(f"    - Scholar publications and co-authors")
    print(f"    - Patents and co-inventors")
    print(f"    - Industry connections (Corporate nodes)")
    print("=" * 80)


def main():
    """Main CLI entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a complete research network graph with industry connections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_complete_graph.py "Andre Imbert"
  python build_complete_graph.py "Marie Curie" --max-publications 50
  python build_complete_graph.py "Alice Nedelec" --max-patents 20 --no-enrich-persons
  python build_complete_graph.py "John Smith" --no-discover-patents
        """
    )

    parser.add_argument(
        "researcher_name",
        type=str,
        help="Name of the researcher to analyze"
    )

    parser.add_argument(
        "--max-publications",
        type=int,
        default=100,
        help="Maximum number of publications to include (default: 100)"
    )

    parser.add_argument(
        "--max-patents",
        type=int,
        default=10,
        help="Maximum number of patents to analyze (default: 10, use 0 to skip)"
    )

    parser.add_argument(
        "--enrich-persons",
        dest="enrich_persons",
        action="store_true",
        default=True,
        help="Enrich co-author nodes with Scholar profiles (default: enabled)"
    )

    parser.add_argument(
        "--no-enrich-persons",
        dest="enrich_persons",
        action="store_false",
        help="Skip enriching co-author nodes (faster)"
    )

    parser.add_argument(
        "--discover-patents",
        dest="discover_corporates_from_patents",
        action="store_true",
        default=True,
        help="Auto-discover corporates from patent assignees (default: enabled)"
    )

    parser.add_argument(
        "--no-discover-patents",
        dest="discover_corporates_from_patents",
        action="store_false",
        help="Skip auto-discovery from patents"
    )

    args = parser.parse_args()

    # Build the graph
    build_complete_graph_for_researcher(
        researcher_name=args.researcher_name,
        max_publications=args.max_publications,
        max_patents=args.max_patents,
        enrich_persons=args.enrich_persons,
        discover_corporates_from_patents=args.discover_corporates_from_patents
    )


if __name__ == "__main__":
    main()
