"""
Publication affiliation scanner.

This module scans OpenAlex publications to find corporate affiliations
for co-authors. This is a CRITICAL source of evidence that was missing
in the original implementation.

SOURCES:
- OpenAlex authorships.institutions (direct affiliation data)
- ROR classification (to determine if institution is corporate)
"""
from typing import List, Dict, Any, Optional
from src.logger import logger
from src.pathfinding.openalex_client import OpenAlexClient
from src.pathfinding.ror_client import RORClient
from src.pathfinding.evidence_schema import Evidence, EvidenceLevel, create_publication_affiliation_evidence


def scan_coauthor_publications_for_corporate_affiliations(
    coauthor_openalex_id: str,
    coauthor_name: str,
    openalex_client: OpenAlexClient,
    ror_client: RORClient,
    max_works: int = 50,
    min_confidence: float = 0.85
) -> List[Evidence]:
    """
    Scan a co-author's publications for corporate affiliations.

    This is a DIRECT source of evidence: if a co-author lists
    "Google" as their affiliation in a publication, we have
    Level A evidence of a Google connection.

    Args:
        coauthor_openalex_id: OpenAlex ID of co-author.
        coauthor_name: Name of co-author (for logging).
        openalex_client: OpenAlex client.
        ror_client: ROR client (for classification).
        max_works: Maximum works to scan.
        min_confidence: Minimum ROR confidence to accept.

    Returns:
        List of Evidence objects (Level A).
    """
    logger.info(f"[PUBLICATION SCAN] Scanning publications for: {coauthor_name}")

    evidence_list: List[Evidence] = []

    # Get co-author's publications
    works = openalex_client.get_author_works(coauthor_openalex_id, max_results=max_works)

    if not works:
        logger.info(f"  No publications found")
        return []

    logger.info(f"  Checking {len(works)} publication(s)...")

    # Track corporates found to avoid duplicates
    corporates_seen = set()

    for work in works:
        work_id = work.get("id", "")
        work_title = work.get("title", "Untitled")
        work_year = work.get("publication_year", "?")

        # Find authorship for this co-author
        authorships = work.get("authorships", [])
        coauthor_authorship = None
        authorship_index = -1

        for idx, authorship in enumerate(authorships):
            author_data = authorship.get("author", {})
            if author_data.get("id") == coauthor_openalex_id:
                coauthor_authorship = authorship
                authorship_index = idx
                break

        if not coauthor_authorship:
            logger.debug(f"  Work {work_id}: Co-author not found in authorships")
            continue

        # Get institutions for this authorship
        institutions = coauthor_authorship.get("institutions", [])

        if not institutions:
            logger.debug(f"  Work {work_id}: No institutions listed")
            continue

        # Check each institution
        for inst_idx, institution in enumerate(institutions):
            inst_name = institution.get("display_name", "Unknown")
            inst_ror_id = institution.get("ror")
            inst_type = institution.get("type", "Unknown")

            # Skip if already seen
            if inst_name in corporates_seen:
                continue

            # Classify as corporate using ROR
            classification = ror_client.classify_organization(inst_name, ror_id=inst_ror_id)

            if classification["is_corporate"] and classification["confidence"] >= min_confidence:
                # Found a corporate affiliation!
                corporates_seen.add(inst_name)

                logger.info(
                    f"  ✓ CORPORATE AFFILIATION: {inst_name} "
                    f"(in '{work_title[:50]}...', {work_year})"
                )

                # Create Level A evidence
                evidence = create_publication_affiliation_evidence(
                    work_id=work_id,
                    work_title=work_title,
                    work_url=work_id.replace("https://openalex.org/", "https://openalex.org/works/"),
                    author_name=coauthor_name,
                    institution_name=inst_name,
                    institution_ror_id=inst_ror_id,
                    authorship_index=authorship_index,
                    institution_index=inst_idx
                )

                evidence_list.append(evidence)

    if evidence_list:
        logger.info(f"  ✓ Found {len(evidence_list)} corporate affiliation(s) in publications")
    else:
        logger.info(f"  → No corporate affiliations found in publications")

    return evidence_list


def find_repeated_affiliations(
    coauthor_openalex_id: str,
    coauthor_name: str,
    openalex_client: OpenAlexClient,
    ror_client: RORClient,
    max_works: int = 100,
    min_occurrences: int = 3
) -> List[Dict[str, Any]]:
    """
    Find corporate affiliations that appear repeatedly across publications.

    This provides Level B evidence: if a co-author lists "Microsoft"
    in 5 different publications, it's strong evidence of a Microsoft link.

    Args:
        coauthor_openalex_id: OpenAlex ID of co-author.
        coauthor_name: Name of co-author.
        openalex_client: OpenAlex client.
        ror_client: ROR client.
        max_works: Maximum works to scan.
        min_occurrences: Minimum occurrences to consider "repeated".

    Returns:
        List of dicts with corporate info and occurrence count.
    """
    logger.info(f"[REPEATED AFFILIATIONS] Scanning for: {coauthor_name}")

    # Get co-author's publications
    works = openalex_client.get_author_works(coauthor_openalex_id, max_results=max_works)

    if not works:
        return []

    logger.info(f"  Checking {len(works)} publication(s)...")

    # Count occurrences
    corporate_counts: Dict[str, Dict[str, Any]] = {}

    for work in works:
        work_id = work.get("id", "")
        work_title = work.get("title", "Untitled")

        # Find authorship for this co-author
        authorships = work.get("authorships", [])
        coauthor_authorship = None

        for authorship in authorships:
            author_data = authorship.get("author", {})
            if author_data.get("id") == coauthor_openalex_id:
                coauthor_authorship = authorship
                break

        if not coauthor_authorship:
            continue

        # Get institutions
        institutions = coauthor_authorship.get("institutions", [])

        for institution in institutions:
            inst_name = institution.get("display_name", "Unknown")
            inst_ror_id = institution.get("ror")

            # Classify as corporate
            classification = ror_client.classify_organization(inst_name, ror_id=inst_ror_id)

            if classification["is_corporate"]:
                if inst_name not in corporate_counts:
                    corporate_counts[inst_name] = {
                        "name": inst_name,
                        "ror_id": inst_ror_id,
                        "count": 0,
                        "works": []
                    }

                corporate_counts[inst_name]["count"] += 1
                corporate_counts[inst_name]["works"].append({
                    "work_id": work_id,
                    "title": work_title
                })

    # Filter by min_occurrences
    repeated = [
        data for data in corporate_counts.values()
        if data["count"] >= min_occurrences
    ]

    # Sort by count (descending)
    repeated.sort(key=lambda x: x["count"], reverse=True)

    if repeated:
        logger.info(f"  ✓ Found {len(repeated)} repeated corporate affiliation(s):")
        for corp in repeated:
            logger.info(f"    - {corp['name']}: {corp['count']} publications")
    else:
        logger.info(f"  → No repeated corporate affiliations (need {min_occurrences}+ occurrences)")

    return repeated


def scan_shared_publications_for_coauthor_affiliations(
    main_researcher_openalex_id: str,
    coauthor_openalex_id: str,
    coauthor_name: str,
    openalex_client: OpenAlexClient,
    ror_client: RORClient
) -> List[Evidence]:
    """
    Scan SHARED publications between main researcher and co-author
    to find co-author's corporate affiliations.

    This is more precise than scanning all co-author publications,
    because we only look at the collaboration period.

    Args:
        main_researcher_openalex_id: Main researcher's OpenAlex ID.
        coauthor_openalex_id: Co-author's OpenAlex ID.
        coauthor_name: Co-author's name.
        openalex_client: OpenAlex client.
        ror_client: ROR client.

    Returns:
        List of Evidence objects.
    """
    logger.info(f"[SHARED PUBLICATIONS] Scanning for: {coauthor_name}")

    evidence_list: List[Evidence] = []

    # Get main researcher's publications
    works = openalex_client.get_author_works(main_researcher_openalex_id, max_results=100)

    if not works:
        return []

    # Filter to shared publications
    shared_works = []
    for work in works:
        authorships = work.get("authorships", [])
        author_ids = [a.get("author", {}).get("id") for a in authorships]

        if coauthor_openalex_id in author_ids:
            shared_works.append(work)

    if not shared_works:
        logger.info(f"  No shared publications found")
        return []

    logger.info(f"  Checking {len(shared_works)} shared publication(s)...")

    corporates_seen = set()

    for work in shared_works:
        work_id = work.get("id", "")
        work_title = work.get("title", "Untitled")

        # Find co-author's authorship
        authorships = work.get("authorships", [])
        coauthor_authorship = None
        authorship_index = -1

        for idx, authorship in enumerate(authorships):
            author_data = authorship.get("author", {})
            if author_data.get("id") == coauthor_openalex_id:
                coauthor_authorship = authorship
                authorship_index = idx
                break

        if not coauthor_authorship:
            continue

        # Get institutions
        institutions = coauthor_authorship.get("institutions", [])

        for inst_idx, institution in enumerate(institutions):
            inst_name = institution.get("display_name", "Unknown")
            inst_ror_id = institution.get("ror")

            if inst_name in corporates_seen:
                continue

            # Classify
            classification = ror_client.classify_organization(inst_name, ror_id=inst_ror_id)

            if classification["is_corporate"]:
                corporates_seen.add(inst_name)

                logger.info(f"  ✓ {inst_name} in shared work: '{work_title[:50]}...'")

                # Create evidence
                evidence = create_publication_affiliation_evidence(
                    work_id=work_id,
                    work_title=work_title,
                    work_url=work_id,
                    author_name=coauthor_name,
                    institution_name=inst_name,
                    institution_ror_id=inst_ror_id,
                    authorship_index=authorship_index,
                    institution_index=inst_idx
                )

                evidence_list.append(evidence)

    if evidence_list:
        logger.info(f"  ✓ Found {len(evidence_list)} corporate affiliation(s) in shared publications")

    return evidence_list
