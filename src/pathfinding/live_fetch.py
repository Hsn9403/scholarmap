"""
Live data fetching from Scholar and Patents APIs.

Used when data is not available in database.
"""
from typing import Optional, Tuple

from src.logger import logger
from src.scholar.client import ScholarClient
from src.patents.client import PatentsClient
from src.models import ScholarData, PatentsData


def fetch_live_data(
    scientist_name: str,
    max_publications: int = 30,
    max_patents: int = 20,
    scholar_id: Optional[str] = None
) -> Tuple[Optional[ScholarData], PatentsData]:
    """
    Fetch scientist data live from Scholar and Patents APIs.

    Args:
        scientist_name: Name of the scientist.
        max_publications: Max publications to fetch.
        max_patents: Max patents to fetch.
        scholar_id: Optional Google Scholar ID for precise fetching (avoids ambiguity).

    Returns:
        Tuple of (ScholarData, PatentsData).
        ScholarData may be None if not found.
    """
    scholar_client = ScholarClient()
    patents_client = PatentsClient()

    # Fetch Scholar data
    scholar_data = None
    try:
        if scholar_id:
            # Use scholar_id directly for precise match (no ambiguity!)
            logger.debug(f"Fetching Scholar data by ID: {scholar_id} ({scientist_name})")
            scholar_data = scholar_client.fetch_author_data(
                scholar_id,
                num_articles=max_publications
            )
            logger.info(f"  ✓ Fetched {len(scholar_data.top_publications)} publications (by ID)")
        else:
            # Fall back to name search (may be ambiguous for "E Lombardi")
            logger.debug(f"Searching Scholar by name: {scientist_name}")
            candidates = scholar_client.find_candidates(scientist_name, num=5)

            if candidates:
                author_id = candidates[0].author_id
                logger.debug(f"Found Scholar profile: {candidates[0].title}")

                scholar_data = scholar_client.fetch_author_data(
                    author_id,
                    num_articles=max_publications
                )
                logger.info(f"  ✓ Fetched {len(scholar_data.top_publications)} publications")
            else:
                logger.debug(f"No Scholar profile found for: {scientist_name}")

    except Exception as e:
        logger.warning(f"Error fetching Scholar data: {e}")

    # Fetch Patents data
    patents_data = PatentsData(patents_total=0, top_patents=[])
    try:
        logger.debug(f"Searching Patents for: {scientist_name}")
        patents_data = patents_client.fetch_patents_data(
            inventor_name=scientist_name,
            max_patents=max_patents
        )
        logger.info(f"  ✓ Fetched {len(patents_data.top_patents)} patents")

    except Exception as e:
        logger.warning(f"Error fetching Patents data: {e}")

    return scholar_data, patents_data
