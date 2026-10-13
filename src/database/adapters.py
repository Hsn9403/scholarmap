"""
Database-to-DTO adapters.

This module provides functions to convert database models to application DTOs
(Data Transfer Objects) used by the main script.

This allows the script to work seamlessly with database data instead of API responses.
"""
from typing import List, Optional, Dict, Any
from collections import Counter

from src.models import (
    ScholarData,
    ScholarPublication,
    CoAuthor,
    PatentsData,
    PatentItem,
)
from src.database.api import DatabaseAPI
from src.logger import logger


def scientist_to_scholar_data(
    scientist_id: Optional[int] = None,
    scientist_name: Optional[str] = None,
    api: Optional[DatabaseAPI] = None,
    use_db_only: bool = False
) -> Optional[ScholarData]:
    """
    Convert a database scientist to ScholarData DTO.

    Args:
        scientist_id: Database ID of the scientist
        scientist_name: Name of the scientist (alternative lookup)
        api: DatabaseAPI instance (creates one if not provided)
        use_db_only: If True, skip API enrichment (e.g., Semantic Scholar)

    Returns:
        ScholarData object or None if not found

    Example:
        >>> data = scientist_to_scholar_data(scientist_name="Alice Nedelec")
        >>> print(f"{data.name}: {data.citations_total} citations")
    """
    close_api = False
    if api is None:
        api = DatabaseAPI()
        close_api = True

    try:
        # Get scientist - prefer ones with Scholar ID and publications
        if scientist_id:
            scientist = api.get_scientist_by_id(scientist_id)
        elif scientist_name:
            # Search for all matching scientists
            results = api.search_scientists(scientist_name)

            if not results:
                logger.warning(f"Scientist not found: {scientist_name}")
                return None

            # Prefer scientist with Scholar ID and publications
            scientist = None
            for result in results:
                if result.scholar_id and result.publications_count > 0:
                    scientist = result
                    logger.info(f"Using scientist with Scholar ID: {result.scholar_id} ({result.publications_count} pubs)")
                    break

            # If no good match, use first result
            if not scientist:
                scientist = results[0]
                logger.info(f"Using first match: {scientist.name} (no Scholar ID)")
        else:
            return None

        if not scientist:
            logger.warning(f"Scientist not found: {scientist_name or scientist_id}")
            return None

        # Get publications
        publications = api.get_publications_by_scientist(scientist.id)

        # Initialize Semantic Scholar client for enriching truncated authors
        # (only if needed - lazy initialization)
        s2_client = None

        # Convert publications to ScholarPublication
        top_publications = []
        for pub in publications:
            # Parse authors from authors_raw field or use empty list
            # Check if authors are truncated (contain "...")
            is_truncated = pub.authors_raw and ("..." in pub.authors_raw or "…" in pub.authors_raw)

            author_names = []
            if pub.authors_raw:
                author_names = [
                    name.strip()
                    for name in pub.authors_raw.split(",")
                    if name.strip() and name.strip() not in ("...", ".", "…")
                ]

            # Try to enrich with Semantic Scholar if truncated (only if not use_db_only)
            if is_truncated and pub.title and not use_db_only:
                # Lazy initialization of Semantic Scholar client
                if s2_client is None:
                    try:
                        from src.api import SemanticScholarClient
                        s2_client = SemanticScholarClient()
                        logger.info("Semantic Scholar enabled for enriching truncated authors")
                    except Exception as e:
                        logger.warning(f"Could not initialize Semantic Scholar: {e}")
                        s2_client = False  # Mark as failed

                # Try to fetch complete authors
                if s2_client:
                    try:
                        logger.info(f"Trying Semantic Scholar for: {pub.title[:50]}...")
                        complete_authors = s2_client.get_paper_authors(pub.title)
                        if complete_authors and len(complete_authors) > len(author_names):
                            logger.info(f"✨ Enriched with Semantic Scholar: {len(complete_authors)} authors (was {len(author_names)})")
                            author_names = complete_authors
                    except Exception as e:
                        logger.warning(f"Semantic Scholar failed for '{pub.title[:50]}...': {e}")

            scholar_pub = ScholarPublication(
                title=pub.title,
                link=pub.link or "",
                cited_by=pub.cited_by,
                authors=author_names,
                year=str(pub.year) if pub.year else None,
                source=pub.source,  # Now stored in database
                abstract=pub.abstract,  # Now stored in database
            )
            top_publications.append(scholar_pub)

        # Compute co-authors from publications
        coauthors = _compute_coauthors(publications, api)

        # Create ScholarData
        scholar_data = ScholarData(
            author_id=scientist.scholar_id or scientist.scholar_url or "",
            name=scientist.name,
            affiliation=scientist.affiliation or "",
            citations_total=scientist.total_citations,
            h_index=scientist.h_index,  # Retrieved from database
            publications_total=scientist.publications_count,
            top_publications=top_publications,
            coauthors=coauthors,
        )

        logger.info(
            f"Loaded scholar data from database: {scientist.name} "
            f"({len(top_publications)} publications)"
        )

        return scholar_data

    finally:
        if close_api:
            api.close()


def _is_valid_coauthor_name(name: str) -> bool:
    """
    Check if a name is valid for co-author listing.

    Filters out:
    - Initials only (e.g., "J Simmchen", "A B C")
    - Names too short (< 5 characters)
    - Names with dots (e.g., "J. Smith")

    Args:
        name: Author name to check

    Returns:
        True if name is valid for co-author listing
    """
    if not name or len(name) < 5:
        return False

    # Check if name contains dots (indicates initials)
    if '.' in name:
        return False

    # Split name into parts
    parts = name.split()
    if not parts:
        return False

    # Check if all parts are single letters (initials only)
    # Allow one single letter (first name initial) but not all
    single_letter_count = sum(1 for part in parts if len(part) == 1)

    # If more than half are single letters, it's likely all initials
    if single_letter_count > len(parts) / 2:
        return False

    return True


def _compute_coauthors(publications: List, api) -> List[CoAuthor]:
    """
    Compute co-authors from a list of publications.

    Args:
        publications: List of PublicationData objects
        api: DatabaseAPI instance for looking up Scholar IDs

    Returns:
        List of CoAuthor objects
    """
    coauthor_stats: Dict[str, Dict[str, Any]] = {}

    for pub in publications:
        if not pub.authors or len(pub.authors) < 2:
            continue

        year = str(pub.year) if pub.year else None

        for author in pub.authors:
            # Filter out invalid co-author names (initials, too short, etc.)
            if not _is_valid_coauthor_name(author):
                continue

            if author not in coauthor_stats:
                coauthor_stats[author] = {
                    "count": 0,
                    "last_year": year,
                    "titles": [],
                    "scholar_id": None,
                    "h_index": None,
                    "scholar_url": None,
                }

            stats = coauthor_stats[author]
            stats["count"] += 1
            stats["titles"].append(pub.title)

            # Keep the most recent year
            if year and (not stats["last_year"] or year > stats["last_year"]):
                stats["last_year"] = year

    # Lookup Scholar IDs for co-authors
    from src.database.models import Scientist
    import unicodedata

    def normalize_for_match(n):
        """Normalize name for fuzzy matching."""
        n = unicodedata.normalize('NFD', n)
        n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
        return n.lower().strip()

    for name in coauthor_stats.keys():
        # Try exact match first
        scientist = api.db.query(Scientist).filter_by(name=name).first()

        # If no exact match, try fuzzy match (initials + last name)
        if not scientist:
            # Extract parts
            parts = name.split()
            if len(parts) >= 2:
                # Get last name
                last_name = parts[-1]
                first_initial = parts[0][0] if parts[0] else ""

                # Search for scientists with same last name
                candidates = api.db.query(Scientist).filter(
                    Scientist.name.ilike(f"%{last_name}")
                ).all()

                # Check if any candidate matches (same last name + first initial)
                # Prefer candidates with Scholar ID
                matching_candidates = []
                for candidate in candidates:
                    candidate_parts = candidate.name.split()
                    if candidate_parts:
                        candidate_last = candidate_parts[-1]
                        candidate_first = candidate_parts[0][0] if candidate_parts[0] else ""

                        # Match if same last name + same first initial
                        if (normalize_for_match(candidate_last) == normalize_for_match(last_name) and
                            candidate_first.lower() == first_initial.lower()):
                            matching_candidates.append(candidate)

                # Prefer candidate with Scholar ID
                if matching_candidates:
                    scientist = next(
                        (c for c in matching_candidates if c.scholar_id),
                        matching_candidates[0]  # Fallback to first if none have Scholar ID
                    )

        if scientist:
            # Store all available data from scientist
            if scientist.scholar_id:
                coauthor_stats[name]["scholar_id"] = scientist.scholar_id
            if scientist.h_index is not None:
                coauthor_stats[name]["h_index"] = scientist.h_index
            if scientist.scholar_url:
                coauthor_stats[name]["scholar_url"] = scientist.scholar_url

    # Convert to CoAuthor objects
    coauthors = []
    for name, stats in coauthor_stats.items():
        coauthor = CoAuthor(
            name=name,
            shared_pubs_count=stats["count"],
            last_shared_year=stats["last_year"],
            example_titles=stats["titles"][:3],  # First 3 titles
            scholar_id=stats.get("scholar_id"),
            h_index=stats.get("h_index"),
            scholar_url=stats.get("scholar_url"),
        )
        coauthors.append(coauthor)

    # Sort by collaboration count
    coauthors.sort(key=lambda x: x.shared_pubs_count, reverse=True)

    return coauthors


def scientist_to_patents_data(
    scientist_id: Optional[int] = None,
    scientist_name: Optional[str] = None,
    api: Optional[DatabaseAPI] = None
) -> PatentsData:
    """
    Convert database patents to PatentsData DTO.

    Args:
        scientist_id: Database ID of the scientist
        scientist_name: Name of the scientist (alternative lookup)
        api: DatabaseAPI instance (creates one if not provided)

    Returns:
        PatentsData object (empty if scientist not found)

    Example:
        >>> data = scientist_to_patents_data(scientist_name="Alice Nedelec")
        >>> print(f"Patents: {data.patents_total}")
    """
    close_api = False
    if api is None:
        api = DatabaseAPI()
        close_api = True

    try:
        # Get scientist - prefer ones with Scholar ID and publications
        if scientist_id:
            scientist = api.get_scientist_by_id(scientist_id)
        elif scientist_name:
            # Search for all matching scientists
            results = api.search_scientists(scientist_name)

            if not results:
                logger.warning(f"Scientist not found: {scientist_name}")
                return PatentsData(patents_total=0, top_patents=[])

            # Prefer scientist with Scholar ID and publications
            scientist = None
            for result in results:
                if result.scholar_id and result.publications_count > 0:
                    scientist = result
                    break

            # If no good match, use first result
            if not scientist:
                scientist = results[0]
        else:
            return PatentsData(patents_total=0, top_patents=[])

        if not scientist:
            logger.warning(f"Scientist not found: {scientist_name or scientist_id}")
            return PatentsData(patents_total=0, top_patents=[])

        # Get patents
        patents = api.get_patents_by_scientist(scientist.id)

        # Convert patents to PatentItem
        top_patents = []
        for patent in patents:
            # Get co-inventors
            # First try from inventors_json (complete list from patent)
            if patent.inventors_json and "inventors" in patent.inventors_json:
                all_inventors = patent.inventors_json["inventors"]
                co_inventors = [inv for inv in all_inventors if inv.lower() != scientist.name.lower()]
            else:
                # Fallback to database relationships (only linked scientists)
                inventor_scientists = api.get_patent_inventors(patent.id)
                all_inventors = [inv.name for inv in inventor_scientists]
                co_inventors = [
                    inv.name for inv in inventor_scientists
                    if inv.name != scientist.name
                ]

            # Get assignee(s) (corporate)
            from src.database.models import Corporate, PatentCorporate
            assignee_links = (
                api.db.query(Corporate)
                .join(PatentCorporate)
                .filter(PatentCorporate.patent_id == patent.id)
                .filter(PatentCorporate.role == "assignee")
                .all()
            )
            # Join multiple assignees with comma if there are several
            if assignee_links:
                assignee_names = [corp.name for corp in assignee_links]
                current_assignee = ", ".join(assignee_names)
            else:
                # Fallback to patent.assignee field (populated when importing from SerpAPI)
                current_assignee = patent.assignee

            # Format claims for display
            claims_list = None
            if patent.claims_excerpt:
                # Split by numbered items and take first 3
                claims_list = [c.strip() for c in patent.claims_excerpt.split('\n\n') if c.strip()][:3]

            # Format cited/citing patents for display
            cited_patents_list = None
            if patent.cited_patents_json:
                cited_patents_list = patent.cited_patents_json.get('patents', [])

            citing_patents_list = None
            if patent.citing_patents_json:
                citing_patents_list = patent.citing_patents_json.get('patents', [])

            # Extract cited assignees from cited_patents_json
            cited_assignees_list = None
            if patent.cited_patents_json:
                assignees = [p.get('assignee') for p in patent.cited_patents_json.get('patents', []) if p.get('assignee')]
                cited_assignees_list = list(set(assignees))[:10]  # Unique, limit to 10

            patent_item = PatentItem(
                title=patent.title,
                link=patent.link or "",
                patent_id=patent.patent_id,
                publication_date=patent.publication_date,  # Now stored in database
                filing_date=patent.filing_date,  # Now stored in database
                priority_date=patent.priority_date,  # Now stored in database
                current_assignee=current_assignee,
                claims_top3=claims_list,  # From database
                cited_by=patent.cited_by_count,  # From database
                cited_assignees=cited_assignees_list,  # Extracted from cited_patents_json
                citing_assignees=None,  # Not available
                cited_patents=cited_patents_list,  # From database
                citing_patents=citing_patents_list,  # From database
                co_inventors=co_inventors if co_inventors else None,
                inventors=all_inventors if all_inventors else None,  # ALL inventors (for validation)
            )
            top_patents.append(patent_item)

        patents_data = PatentsData(
            patents_total=len(patents),
            top_patents=top_patents,
        )

        logger.info(
            f"Loaded patents data from database: {scientist.name} "
            f"({len(top_patents)} patents)"
        )

        return patents_data

    finally:
        if close_api:
            api.close()


def get_scientist_data_from_database(
    scientist_name: str,
    scholar_id: Optional[str] = None
) -> tuple[Optional[ScholarData], PatentsData]:
    """
    Get complete scientist data (Scholar + Patents) from database.

    This is the main entry point for database-backed data retrieval.

    Args:
        scientist_name: Name of the scientist to look up
        scholar_id: Optional Google Scholar ID for precise matching (avoids ambiguity)

    Returns:
        Tuple of (ScholarData, PatentsData)
        ScholarData may be None if not found

    Example:
        >>> scholar, patents = get_scientist_data_from_database("Alice Nedelec")
        >>> print(f"Scholar: {scholar.name if scholar else 'Not found'}")
        >>> print(f"Patents: {patents.patents_total}")

        >>> # With Scholar ID for precise matching (avoids "E Lombardi" ambiguity)
        >>> scholar, patents = get_scientist_data_from_database("E Lombardi", scholar_id="xJaxiEEAAAAJ")
    """
    with DatabaseAPI() as api:
        # If scholar_id provided, search by ID first (most precise)
        if scholar_id:
            results = api.search_scientists(scholar_id=scholar_id)
            if results:
                scientist = results[0]
                logger.info(
                    f"Found scientist by Scholar ID: {scientist.name} "
                    f"(ID: {scientist.scholar_id})"
                )
                # Return early with precise match
                scholar_data = scientist_to_scholar_data(scientist_id=scientist.id, api=api)
                patents_data = scientist_to_patents_data(scientist_id=scientist.id, api=api)
                return scholar_data, patents_data

        # Fall back to name search
        results = api.search_scientists(scientist_name)

        if not results:
            logger.warning(f"Scientist not found in database: {scientist_name}")
            return None, PatentsData(patents_total=0, top_patents=[])

        # If scholar_id provided, try to find exact match in results
        scientist = None
        if scholar_id:
            for result in results:
                if result.scholar_id == scholar_id:
                    scientist = result
                    logger.info(
                        f"Matched by Scholar ID in name search: {scientist.name} "
                        f"(ID: {scientist.scholar_id})"
                    )
                    break

        # Otherwise, prefer scientist with Scholar ID and publications
        if not scientist:
            for result in results:
                if result.scholar_id and result.publications_count > 0:
                    scientist = result
                    logger.info(
                        f"Using scientist with Scholar ID: {result.scholar_id} "
                        f"({result.publications_count} pubs)"
                    )
                    break

        # If still no match, use first result
        if not scientist:
            scientist = results[0]
            logger.info(f"Using first match: {scientist.name}")

        # Get scholar data
        scholar_data = scientist_to_scholar_data(scientist_id=scientist.id, api=api)

        # Get patents data
        patents_data = scientist_to_patents_data(scientist_id=scientist.id, api=api)

        return scholar_data, patents_data
