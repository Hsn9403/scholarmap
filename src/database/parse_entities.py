"""Parse entities (scientists, publications, etc.) from API responses."""

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    APICall,
    Scientist,
    Publication,
    Patent,
    PublicationAuthor,
    PatentInventor,
    PatentCorporate,
    Corporate,
    Institution,
    ScientistInstitution,
)
from src.database.deduplication import (
    find_or_create_scientist,
    find_or_create_publication,
    find_or_create_corporate,
    find_or_create_patent,
)
from src.logger import logger


def extract_scholar_id_from_url(url: str) -> Optional[str]:
    """
    Extract Google Scholar ID from URL.

    Args:
        url: Google Scholar profile URL

    Returns:
        Scholar ID or None

    Example:
        >>> extract_scholar_id_from_url("https://scholar.google.com/citations?user=xmZKGsYAAAAJ")
        'xmZKGsYAAAAJ'
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get("user", [None])[0]
    except Exception:
        return None


def normalize_name(name: str) -> str:
    """
    Normalize institution/corporate name for deduplication.

    Args:
        name: Original name

    Returns:
        Normalized name (lowercase, no special chars)

    Example:
        >>> normalize_name("MIT - Massachusetts Institute")
        'mit massachusetts institute'
    """
    # Lowercase
    normalized = name.lower()
    # Remove special characters
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    # Remove extra spaces
    normalized = " ".join(normalized.split())
    return normalized


def find_or_create_institution(db, name: str, country: Optional[str] = None) -> Institution:
    """
    Find existing institution or create new one.

    Args:
        db: Database session
        name: Institution name
        country: Optional country

    Returns:
        Institution object
    """
    normalized = normalize_name(name)

    # Try to find by normalized name
    institution = db.query(Institution).filter_by(normalized_name=normalized).first()
    if institution:
        return institution

    # Create new institution
    institution = Institution(
        name=name,
        normalized_name=normalized,
        country=country,
    )
    db.add(institution)
    db.flush()  # Get ID without committing
    logger.debug(f"Created institution: {name}")
    return institution


def parse_google_scholar_results(
    db, api_call: APICall
) -> Tuple[List[Scientist], List[Publication]]:
    """
    Parse Google Scholar search results from API call.

    Args:
        db: Database session
        api_call: APICall object with response_json

    Returns:
        Tuple of (scientists_found, publications_created)
    """
    scientists = []
    publications = []

    try:
        response = api_call.response_json
        organic_results = response.get("organic_results", [])

        for result in organic_results:
            # Extract scholar profile info
            title = result.get("title", "").strip()
            link = result.get("link", "")

            # Check if this is a scholar profile
            if "scholar.google.com/citations" in link:
                scholar_id = extract_scholar_id_from_url(link)

                # Find or create scientist
                scientist, created = find_or_create_scientist(
                    db,
                    name=title,
                    scholar_id=scholar_id,
                )
                scientists.append(scientist)

                if created:
                    logger.info(f"✓ Found scientist: {title} ({scholar_id})")
                else:
                    logger.debug(f"→ Existing scientist: {title}")

            # Extract snippets that might contain publications
            snippet = result.get("snippet", "")
            if snippet and any(
                keyword in snippet.lower()
                for keyword in ["published", "paper", "article", "journal"]
            ):
                # Create publication from snippet (basic parsing)
                pub_title = snippet[:200]  # Truncate to reasonable length

                publication, created = find_or_create_publication(
                    db,
                    title=pub_title,
                    link=link,
                )
                publications.append(publication)

                if created:
                    logger.debug(f"✓ Found potential publication: {pub_title[:50]}...")
                else:
                    logger.debug(f"→ Existing publication: {pub_title[:50]}...")

    except Exception as e:
        logger.error(f"Failed to parse Google Scholar results: {e}")

    return scientists, publications


def parse_scholar_author_results(
    db, api_call: APICall
) -> Tuple[Optional[Scientist], List[Publication]]:
    """
    Parse Google Scholar author profile results from API call.

    Args:
        db: Database session
        api_call: APICall object with response_json

    Returns:
        Tuple of (scientist, publications_list)
    """
    scientist = None
    publications = []

    try:
        response = api_call.response_json
        author = response.get("author", {})

        if author:
            # Extract author info
            name = author.get("name", "").strip()
            scholar_id = author.get("author_id", "").strip() or None  # Convert empty string to None
            affiliations = author.get("affiliations", "")

            # Use find_or_create to prevent duplicates and auto-update
            scientist, created = find_or_create_scientist(
                db,
                name=name,
                scholar_id=scholar_id,
                affiliation=affiliations,
            )

            if created:
                logger.info(f"✓ Created scientist profile: {name}")
            else:
                logger.debug(f"→ Found existing scientist: {name}")

            # Extract and update H-index from cited_by section
            cited_by_data = response.get("cited_by", {})
            if cited_by_data and isinstance(cited_by_data, dict):
                table = cited_by_data.get("table", [])
                # H-index is usually in table[1].indice_h.all or table[1].h_index.all
                if len(table) > 1:
                    h_index_entry = table[1]
                    # Try both "indice_h" (French) and "h_index" (English)
                    h_index_data = h_index_entry.get("indice_h") or h_index_entry.get("h_index")
                    if h_index_data and isinstance(h_index_data, dict):
                        h_index_value = h_index_data.get("all")
                        if h_index_value is not None and (scientist.h_index is None or scientist.h_index == 0):
                            scientist.h_index = h_index_value
                            logger.info(f"Updated H-index for {name}: {h_index_value}")

            # Update Scholar URL if scholar_id is present
            if scholar_id and (not scientist.scholar_url or scientist.scholar_url == ""):
                scientist.scholar_url = f"https://scholar.google.com/citations?user={scholar_id}"
                logger.debug(f"Updated scholar_url for {name}")

            # Parse institution from affiliation
            if affiliations:
                institution = find_or_create_institution(db, affiliations)
                # Link scientist to institution
                link_exists = (
                    db.query(ScientistInstitution)
                    .filter_by(scientist_id=scientist.id, institution_id=institution.id)
                    .first()
                )
                if not link_exists:
                    link = ScientistInstitution(
                        scientist_id=scientist.id,
                        institution_id=institution.id,
                    )
                    db.add(link)

        # Extract publications (articles)
        articles = response.get("articles", [])
        for article in articles:
            title = article.get("title", "").strip()
            link = article.get("link", "")
            citation_id = article.get("citation_id", "")
            cited_by = article.get("cited_by", {}).get("value")
            year_str = article.get("year", "")
            authors_str = article.get("authors", "")
            source = article.get("publication", "")  # Journal/venue info

            # Parse year
            year = None
            if year_str:
                try:
                    year = int(year_str)
                except ValueError:
                    pass

            # Use find_or_create to prevent duplicates and auto-update
            if title:
                publication, created = find_or_create_publication(
                    db,
                    title=title,
                    source_id=citation_id or None,
                    link=link or None,
                    cited_by=cited_by,
                    year=year,
                    source=source or None,
                    authors_raw=authors_str or None,
                )

                if created:
                    logger.debug(f"✓ Added publication: {title[:50]}... ({year})")
                else:
                    logger.debug(f"→ Updated publication: {title[:50]}...")

                # Add to publications list if not already there
                if publication not in publications:
                    publications.append(publication)
            else:
                publication = None

            # Parse and link ALL authors (including co-authors) - even for existing publications
            if publication and authors_str:
                # Split authors by comma and filter out placeholders
                author_names = [
                    name.strip()
                    for name in authors_str.split(",")
                    if name.strip() and name.strip() not in ("...", ".", "…")
                ]

                for author_name in author_names:
                    # Find or create scientist for this author
                    author_scientist, created = find_or_create_scientist(db, name=author_name)
                    if created:
                        logger.debug(f"✓ Created co-author: {author_name}")

                    # Check if link already exists
                    link_exists = (
                        db.query(PublicationAuthor)
                        .filter_by(publication_id=publication.id, author_id=author_scientist.id)
                        .first()
                    )

                    if not link_exists:
                        pub_author = PublicationAuthor(
                            publication_id=publication.id,
                            author_id=author_scientist.id,
                        )
                        db.add(pub_author)

    except Exception as e:
        logger.error(f"Failed to parse Scholar author results: {e}")

    return scientist, publications


def parse_google_patents_results(db, api_call: APICall) -> List:
    """
    Parse Google Patents search results from API call.

    Args:
        db: Database session
        api_call: APICall object with response_json

    Returns:
        List of patents created
    """
    patents_created = []

    try:
        response = api_call.response_json
        organic_results = response.get("organic_results", [])

        for result in organic_results:
            patent_id = result.get("patent_id", "")
            title = result.get("title", "").strip()
            link = result.get("pdf", "") or result.get("link", "")
            assignee_name = result.get("assignee", "").strip()
            inventor_name = result.get("inventor", "").strip()
            publication_date = result.get("publication_date", "")
            filing_date = result.get("filing_date", "")
            priority_date = result.get("priority_date", "")

            if not patent_id or not title:
                continue

            # Find or create patent (checks both patent_id and normalized_title)
            patent, created = find_or_create_patent(
                db,
                title=title,
                patent_id=patent_id,
                link=link,
                publication_date=publication_date or None,
                filing_date=filing_date or None,
                priority_date=priority_date or None,
            )

            if created:
                patents_created.append(patent)
                logger.debug(f"✓ Added patent: {patent_id} - {title[:50]}...")
            else:
                logger.debug(f"→ Updated patent: {patent_id} - {title[:50]}...")

            # Link to inventor (scientist)
            if inventor_name:
                # Find or create scientist for inventor
                inventor_scientist, created = find_or_create_scientist(db, name=inventor_name)
                if created:
                    logger.debug(f"✓ Created inventor: {inventor_name}")

                # Link patent to inventor
                link_exists = (
                    db.query(PatentInventor)
                    .filter_by(patent_id=patent.id, scientist_id=inventor_scientist.id)
                    .first()
                )
                if not link_exists:
                    patent_link = PatentInventor(
                        patent_id=patent.id,
                        scientist_id=inventor_scientist.id,
                    )
                    db.add(patent_link)

            # Link to assignee (corporate)
            if assignee_name:
                # Find or create corporate for assignee
                corporate, created = find_or_create_corporate(db, name=assignee_name)
                if created:
                    logger.debug(f"✓ Created corporate: {assignee_name}")

                # Link patent to corporate
                link_exists = (
                    db.query(PatentCorporate)
                    .filter_by(patent_id=patent.id, corporate_id=corporate.id)
                    .first()
                )
                if not link_exists:
                    corp_link = PatentCorporate(
                        patent_id=patent.id,
                        corporate_id=corporate.id,
                        role="assignee",
                    )
                    db.add(corp_link)

    except Exception as e:
        logger.error(f"Failed to parse Google Patents results: {e}")

    return patents_created


def parse_api_calls(limit: Optional[int] = None) -> Dict[str, int]:
    """
    Parse all API calls and extract entities.

    Args:
        limit: Optional limit of API calls to process

    Returns:
        Statistics dictionary
    """
    db = SessionLocal()
    stats = {
        "processed": 0,
        "scientists": 0,
        "publications": 0,
        "patents": 0,
        "institutions": 0,
        "errors": 0,
    }

    try:
        # Get all API calls that haven't been parsed yet
        query = db.query(APICall).order_by(APICall.created_at)
        if limit:
            query = query.limit(limit)

        api_calls = query.all()
        logger.info(f"Processing {len(api_calls)} API calls...")

        for api_call in api_calls:
            try:
                engine = api_call.engine
                response = api_call.response_json

                # Determine type of response and parse accordingly
                if "author" in response:
                    # Scholar author profile
                    scientist, pubs = parse_scholar_author_results(db, api_call)
                    if scientist:
                        stats["scientists"] += 1
                    stats["publications"] += len(pubs)

                elif "organic_results" in response:
                    # Check if it's patents or regular search
                    if engine in ["google_patents", "google_patents_details"]:
                        # Patent search results
                        patents = parse_google_patents_results(db, api_call)
                        stats["patents"] += len(patents)
                    else:
                        # Google search results
                        scientists, pubs = parse_google_scholar_results(db, api_call)
                        stats["scientists"] += len(scientists)
                        stats["publications"] += len(pubs)

                stats["processed"] += 1

                # Commit after each API call
                db.commit()

                if stats["processed"] % 10 == 0:
                    logger.info(f"Processed {stats['processed']}/{len(api_calls)} API calls...")

            except Exception as e:
                logger.error(f"Failed to parse API call {api_call.id}: {e}")
                db.rollback()
                stats["errors"] += 1

        # Count institutions
        stats["institutions"] = db.query(Institution).count()

    except Exception as e:
        logger.error(f"Parsing failed: {e}")

    finally:
        db.close()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse entities from API responses")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of API calls to process",
    )
    args = parser.parse_args()

    logger.info("Starting entity parsing...")
    stats = parse_api_calls(limit=args.limit)

    logger.info("\n📊 Parsing Statistics:")
    logger.info(f"   API calls processed: {stats['processed']}")
    logger.info(f"   Scientists found: {stats['scientists']}")
    logger.info(f"   Publications created: {stats['publications']}")
    logger.info(f"   Patents created: {stats['patents']}")
    logger.info(f"   Institutions found: {stats['institutions']}")
    logger.info(f"   Errors: {stats['errors']}")
