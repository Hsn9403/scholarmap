#!/usr/bin/env python3
"""
Main script for generating researcher reports.

Usage:
    python3 script.py "First Last"

Generates:
    - Excel report with Scholar and Patent data
    - Interactive HTML network graph
    - JSON graph data
"""
from __future__ import annotations

import re
import sys
import json
import os

# Ensure parent directory is in path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_env
from src.logger import logger, setup_logger
from src.exceptions import ConfigurationError

# Import new classes
from src.api import SerpAPIClient
from src.scholar import ScholarClient
from src.patents import PatentsClient
from src.graph import build_graph_data, extract_two_hop_subgraph, render_graph_html
from src.export import ExcelExporter
from src.helpers import slug

load_env()


def main():
    """Main entry point for the researcher report generation."""
    import argparse

    setup_logger(level=20)  # INFO level

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate researcher report with Scholar and Patent data"
    )
    parser.add_argument(
        "researcher_name",
        type=str,
        help="Name of the researcher to analyze"
    )
    parser.add_argument(
        "--use-database",
        action="store_true",
        help="Use database instead of API calls (faster, free, requires prior data migration)"
    )

    args = parser.parse_args()
    researcher_name = args.researcher_name.strip()
    use_database = args.use_database

    logger.info(f"Generating report for: {researcher_name}")

    if use_database:
        logger.info("🗄️  MODE: Using database (no API calls)")

        # Import database adapters
        from src.database.adapters import get_scientist_data_from_database

        # Fetch data from database
        scholar_data, patents_data = get_scientist_data_from_database(researcher_name)

        # For database mode, we don't need API clients
        scholar_client = None
        patents_client = None

    else:
        logger.info("🌐 MODE: Using API calls (with cassette cache)")

        # Initialize API client
        try:
            api_client = SerpAPIClient()
        except ConfigurationError as e:
            logger.error(str(e))
            sys.exit(1)

        # Initialize domain clients (share the same API client)
        scholar_client = ScholarClient(api_client=api_client, hl="fr")
        patents_client = PatentsClient(api_client=api_client)

        # Search for Google Scholar profile
        logger.info("Searching for Google Scholar profile...")
        author_id = scholar_client.resolve_author_id(researcher_name)

        if author_id == "__QUIT__":
            logger.info("User quit during disambiguation")
            sys.exit(0)

        # Fetch Scholar data
        scholar_data = None
        if author_id:
            scholar_data = scholar_client.fetch_author_data(author_id)
        else:
            logger.warning("Google Scholar profile not found - report will be partial")

        # Fetch Patents data
        inventor_for_patents = (
            scholar_data.name.strip()
            if scholar_data and scholar_data.name
            else researcher_name
        )
        logger.info(f"Fetching patents for: {inventor_for_patents}")
        patents_data = patents_client.fetch_patents_data(inventor_for_patents)

    # Check if we have any usable data
    def _patents_is_zero(p) -> bool:
        v = p.patents_total
        return v in (0, "0", None, "")

    if scholar_data is None and _patents_is_zero(patents_data):
        logger.error("No usable data found (no Scholar profile, no patents) - no report generated")
        sys.exit(0)

    # Generate Excel report
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", researcher_name).strip("_")
    out_path = f"researcher_report_{safe_name}.xlsx"

    logger.info(f"Generating Excel report: {out_path}")
    exporter = ExcelExporter()
    exporter.write(out_path, researcher_name, scholar_data, patents_data)

    # Build KOL network graph
    logger.info("Building KOL network graph...")

    # Person enrichment is DISABLED by default (costs 2 API calls per person)
    # To enable: set ENRICH_PERSONS=true in .env or export ENRICH_PERSONS=true
    # Note: Enrichment is automatically disabled in database mode
    enrich_persons = False if use_database else os.getenv("ENRICH_PERSONS", "false").lower() in ("true", "1", "yes")

    if use_database and os.getenv("ENRICH_PERSONS", "false").lower() in ("true", "1", "yes"):
        logger.warning("Person enrichment is not available in database mode (would require API calls)")

    if enrich_persons:
        logger.warning("Person enrichment ENABLED - this will make additional API calls!")
        logger.warning("Set CASSETTE_MODE=offline to use cached responses only")

    graph = build_graph_data(
        researcher_name=researcher_name,
        scholar=scholar_data,
        patents=patents_data,
        max_patents=10,
        patents_client=patents_client,
        enrich_persons=enrich_persons,
        scholar_client=scholar_client if enrich_persons else None
    )

    graph_2hop = extract_two_hop_subgraph(graph)

    # Save graph files
    author_label = (
        scholar_data.name.strip()
        if scholar_data and scholar_data.name
        else researcher_name
    ).strip()
    base = f"{slug(author_label)}_network"

    json_path = f"{base}_2hop.json"
    html_path = f"{base}_2hop.html"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(graph_2hop, f, ensure_ascii=False, indent=2)
    logger.info(f"2-hop graph JSON saved: {json_path}")

    render_graph_html(graph_2hop, html_path)

    # Log summary
    types = {}
    for n in graph_2hop["nodes"]:
        types[n["type"]] = types.get(n["type"], 0) + 1

    logger.info(f"Graph summary: {len(graph_2hop['nodes'])} nodes, {len(graph_2hop['edges'])} edges")
    logger.info(f"Node types: {types}")
    logger.info(
        f"Report generated: {out_path} | "
        f"Scholar: {scholar_data.author_id if scholar_data else 'NOT_FOUND'} | "
        f"Patents: {patents_data.patents_total}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
