"""
OpenAlex-based co-author disambiguation.

This module solves the NAME MIXING problem by using OpenAlex author IDs.

KEY INSIGHT:
- When you fetch a publication from OpenAlex, it contains "authorships"
- Each authorship has the author's OpenAlex ID (e.g., "https://openalex.org/A1234567890")
- So you DON'T need to search by name → ZERO ambiguity!

Example workflow:
1. Get scientist's publications from OpenAlex
2. Extract co-authors FROM those publications (with their IDs)
3. For each co-author, fetch THEIR publications (using their ID)
4. Validate bidirectionally (shared publications)
5. Extract affiliations and classify corporates
"""
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass

from src.logger import logger
from src.pathfinding.openalex_client import OpenAlexClient
from src.pathfinding.ror_client import RORClient


@dataclass
class OpenAlexAuthor:
    """Represents an author with their OpenAlex ID."""
    openalex_id: str  # e.g., "https://openalex.org/A1234567890"
    name: str
    works_count: int = 0
    cited_by_count: int = 0
    h_index: int = 0


@dataclass
class CoauthorInfo:
    """Co-author extracted from publications with disambiguation data."""
    author: OpenAlexAuthor
    shared_works: List[str]  # List of work IDs (DOIs or OpenAlex IDs) shared with seed scientist
    affiliation_history: List[Dict[str, Any]]  # List of affiliations across publications


@dataclass
class CorporateConnection:
    """A validated connection between a co-author and a corporate."""
    corporate_name: str
    corporate_ror_id: Optional[str]
    confidence_score: float  # 0.0 to 1.0
    evidence: List[Dict[str, Any]]  # List of publications/patents with proof


def extract_coauthors_with_ids(
    scientist_name: str,
    scientist_openalex_id: Optional[str] = None,
    max_works: int = 50,
    client: Optional[OpenAlexClient] = None
) -> List[CoauthorInfo]:
    """
    Extract co-authors with their OpenAlex IDs from a scientist's publications.

    This is THE KEY function for disambiguation:
    - Co-authors are extracted FROM publications (not searched by name)
    - Each co-author has a unique OpenAlex ID
    - Zero risk of name confusion

    Args:
        scientist_name: Name of the main scientist.
        scientist_openalex_id: OpenAlex ID if known (avoids search ambiguity).
        max_works: Max publications to analyze.
        client: OpenAlexClient instance (optional).

    Returns:
        List of CoauthorInfo with unique IDs.
    """
    if not client:
        client = OpenAlexClient()

    logger.info("="*80)
    logger.info(f"Extracting co-authors with OpenAlex IDs for: {scientist_name}")
    logger.info("="*80)

    # Step 1: Get scientist's OpenAlex ID
    if not scientist_openalex_id:
        logger.info("[1/3] Finding scientist in OpenAlex...")
        scientist_data = client.search_author(scientist_name)
        if not scientist_data:
            logger.error(f"Scientist not found in OpenAlex: {scientist_name}")
            return []
        scientist_openalex_id = scientist_data["id"]
        logger.info(f"  ✓ Found: {scientist_data['display_name']} ({scientist_openalex_id})")
    else:
        logger.info(f"[1/3] Using provided OpenAlex ID: {scientist_openalex_id}")

    # Step 2: Get scientist's publications
    logger.info(f"[2/3] Fetching up to {max_works} publications...")
    works = client.get_author_works(scientist_openalex_id, max_results=max_works)

    if not works:
        logger.warning("No publications found")
        return []

    logger.info(f"  ✓ Fetched {len(works)} publications")

    # Step 3: Extract co-authors FROM publications
    logger.info("[3/3] Extracting co-authors from publications...")
    coauthors_map: Dict[str, CoauthorInfo] = {}

    for work in works:
        work_id = work.get("id", "")
        work_title = work.get("title", "")
        authorships = work.get("authorships", [])

        for authorship in authorships:
            author_data = authorship.get("author", {})
            author_id = author_data.get("id")
            author_name = author_data.get("display_name")

            # Skip if no ID or if it's the main scientist
            if not author_id or author_id == scientist_openalex_id:
                continue

            # Initialize co-author if first time seeing them
            if author_id not in coauthors_map:
                coauthors_map[author_id] = CoauthorInfo(
                    author=OpenAlexAuthor(
                        openalex_id=author_id,
                        name=author_name or "Unknown",
                        works_count=author_data.get("works_count", 0),
                        cited_by_count=author_data.get("cited_by_count", 0)
                    ),
                    shared_works=[],
                    affiliation_history=[]
                )

            # Add shared work
            coauthors_map[author_id].shared_works.append(work_id)

            # Extract affiliations from this authorship
            institutions = authorship.get("institutions", [])
            for inst in institutions:
                coauthors_map[author_id].affiliation_history.append({
                    "work_id": work_id,
                    "work_title": work_title,
                    "year": work.get("publication_year"),
                    "institution_id": inst.get("id"),
                    "institution_name": inst.get("display_name"),
                    "ror": inst.get("ror"),
                    "type": inst.get("type"),
                    "country_code": inst.get("country_code")
                })

    # Convert to list and sort by number of shared works
    coauthors_list = sorted(
        coauthors_map.values(),
        key=lambda x: len(x.shared_works),
        reverse=True
    )

    logger.info(f"✓ Extracted {len(coauthors_list)} unique co-authors (with OpenAlex IDs)")
    logger.info(f"  Top co-authors by shared publications:")
    for i, coauthor in enumerate(coauthors_list[:10], 1):
        logger.info(
            f"    {i}. {coauthor.author.name} "
            f"({len(coauthor.shared_works)} shared works, "
            f"ID: {coauthor.author.openalex_id})"
        )

    return coauthors_list


def validate_coauthor_bidirectional_openalex(
    seed_scientist_id: str,
    coauthor: CoauthorInfo,
    min_shared_works: int = 1,
    client: Optional[OpenAlexClient] = None
) -> bool:
    """
    Validate co-author bidirectionally using OpenAlex.

    This function checks if:
    1. The co-author's publications list includes works where the seed scientist appears
    2. There are at least min_shared_works publications in common

    Args:
        seed_scientist_id: OpenAlex ID of the main scientist.
        coauthor: CoauthorInfo to validate.
        min_shared_works: Minimum shared publications required.
        client: OpenAlexClient instance.

    Returns:
        True if validated, False otherwise.
    """
    if not client:
        client = OpenAlexClient()

    logger.info(f"Validating co-author bidirectionally: {coauthor.author.name}")

    # Get co-author's publications
    coauthor_works = client.get_author_works(
        coauthor.author.openalex_id,
        max_results=100  # Fetch more to ensure we find shared works
    )

    if not coauthor_works:
        logger.warning(f"  → No publications found for {coauthor.author.name}")
        return False

    # Extract work IDs where seed scientist appears
    shared_work_ids_found: Set[str] = set()
    for work in coauthor_works:
        authorships = work.get("authorships", [])
        for authorship in authorships:
            author_id = authorship.get("author", {}).get("id")
            if author_id == seed_scientist_id:
                shared_work_ids_found.add(work.get("id"))
                break

    # Check if we found the expected shared works
    expected_shared = set(coauthor.shared_works)
    confirmed_shared = shared_work_ids_found & expected_shared

    if len(confirmed_shared) >= min_shared_works:
        logger.info(
            f"  ✓ VALIDATED: {coauthor.author.name} has {len(confirmed_shared)} "
            f"confirmed shared publications"
        )
        return True
    else:
        logger.warning(
            f"  ✗ FAILED: {coauthor.author.name} has only {len(confirmed_shared)} "
            f"confirmed shared publications (expected at least {min_shared_works})"
        )
        logger.warning(f"    Expected shared works: {list(expected_shared)[:3]}")
        logger.warning(f"    Found in their profile: {list(shared_work_ids_found)[:3]}")
        return False


def classify_affiliations_as_corporate(
    affiliations: List[Dict[str, Any]],
    ror_client: Optional[RORClient] = None
) -> List[Dict[str, Any]]:
    """
    Classify affiliations as corporate or academic using ROR.

    Args:
        affiliations: List of affiliation dicts from CoauthorInfo.affiliation_history.
        ror_client: RORClient instance.

    Returns:
        List of corporate affiliations with classification data.
    """
    if not ror_client:
        ror_client = RORClient()

    corporates = []

    # Deduplicate by institution_id
    unique_institutions: Dict[str, Dict[str, Any]] = {}
    for aff in affiliations:
        inst_id = aff.get("institution_id")
        if not inst_id:
            continue

        if inst_id not in unique_institutions:
            unique_institutions[inst_id] = {
                "institution_id": inst_id,
                "institution_name": aff.get("institution_name"),
                "ror": aff.get("ror"),
                "type": aff.get("type"),
                "country_code": aff.get("country_code"),
                "works": []
            }

        unique_institutions[inst_id]["works"].append({
            "work_id": aff.get("work_id"),
            "work_title": aff.get("work_title"),
            "year": aff.get("year")
        })

    logger.info(f"Classifying {len(unique_institutions)} unique institutions...")

    for inst in unique_institutions.values():
        inst_name = inst["institution_name"]
        ror_id = inst["ror"]

        # Classify with ROR
        classification = ror_client.classify_organization(inst_name, ror_id)

        if classification["is_corporate"]:
            corporates.append({
                "name": inst_name,
                "ror_id": ror_id,
                "confidence": classification["confidence"],
                "classification_source": classification.get("source", "ROR"),
                "works_count": len(inst["works"]),
                "evidence": inst["works"]
            })

            logger.info(
                f"  ✓ CORPORATE: {inst_name} "
                f"(confidence: {classification['confidence']:.2f}, "
                f"{len(inst['works'])} works)"
            )
        else:
            logger.debug(
                f"  → Academic: {inst_name} "
                f"(type: {inst['type']})"
            )

    logger.info(f"✓ Found {len(corporates)} corporate affiliations")
    return corporates


def find_corporate_connections_for_coauthors(
    scientist_name: str,
    scientist_openalex_id: Optional[str] = None,
    max_works: int = 50,
    max_coauthors: int = 20,
    min_shared_works: int = 1,
    openalex_client: Optional[OpenAlexClient] = None,
    ror_client: Optional[RORClient] = None
) -> Dict[str, Any]:
    """
    Complete workflow: Find corporate connections for all co-authors.

    This is the main function implementing the PRIORITY #1 use case.

    Args:
        scientist_name: Name of the main scientist.
        scientist_openalex_id: OpenAlex ID if known.
        max_works: Max publications to analyze for seed scientist.
        max_coauthors: Max co-authors to process.
        min_shared_works: Min shared publications for validation.
        openalex_client: OpenAlexClient instance.
        ror_client: RORClient instance.

    Returns:
        Dict with results:
        {
            "scientist": {...},
            "coauthors_analyzed": int,
            "coauthor_corporate_connections": {
                "coauthor_name": {
                    "openalex_id": "...",
                    "shared_works_count": int,
                    "corporates": [...]
                }
            }
        }
    """
    if not openalex_client:
        openalex_client = OpenAlexClient()
    if not ror_client:
        ror_client = RORClient()

    logger.info("="*80)
    logger.info(f"FINDING CORPORATE CONNECTIONS VIA CO-AUTHORS (OpenAlex)")
    logger.info(f"Scientist: {scientist_name}")
    logger.info("="*80)

    # Step 1: Extract co-authors with IDs
    coauthors = extract_coauthors_with_ids(
        scientist_name,
        scientist_openalex_id,
        max_works,
        openalex_client
    )

    if not coauthors:
        return {
            "error": "No co-authors found",
            "scientist": {"name": scientist_name},
            "coauthors_analyzed": 0,
            "coauthor_corporate_connections": {}
        }

    # Get scientist ID for validation
    if not scientist_openalex_id:
        scientist_data = openalex_client.search_author(scientist_name)
        scientist_openalex_id = scientist_data["id"] if scientist_data else None

    # Step 2: For each co-author, validate and find corporates
    results = {}
    coauthors_to_process = coauthors[:max_coauthors]

    logger.info(f"\nProcessing {len(coauthors_to_process)} co-authors...")

    for i, coauthor in enumerate(coauthors_to_process, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i}/{len(coauthors_to_process)}] {coauthor.author.name}")
        logger.info(f"  OpenAlex ID: {coauthor.author.openalex_id}")
        logger.info(f"  Shared works: {len(coauthor.shared_works)}")
        logger.info(f"{'='*60}")

        # Validate bidirectionally
        if scientist_openalex_id:
            is_valid = validate_coauthor_bidirectional_openalex(
                scientist_openalex_id,
                coauthor,
                min_shared_works,
                openalex_client
            )

            if not is_valid:
                logger.warning(f"  → Skipping {coauthor.author.name}: failed validation")
                continue

        # Classify affiliations
        corporates = classify_affiliations_as_corporate(
            coauthor.affiliation_history,
            ror_client
        )

        if corporates:
            results[coauthor.author.name] = {
                "openalex_id": coauthor.author.openalex_id,
                "shared_works_count": len(coauthor.shared_works),
                "h_index": coauthor.author.h_index,
                "cited_by_count": coauthor.author.cited_by_count,
                "corporates": corporates
            }

            logger.info(f"  ✓ Found {len(corporates)} corporate connection(s)")
        else:
            logger.info(f"  → No corporate connections found")

    # Step 3: Summary
    total_corporates = sum(
        len(data["corporates"])
        for data in results.values()
    )

    summary = {
        "scientist": {
            "name": scientist_name,
            "openalex_id": scientist_openalex_id
        },
        "coauthors_total": len(coauthors),
        "coauthors_analyzed": len(results),
        "total_corporate_connections": total_corporates,
        "coauthor_corporate_connections": results
    }

    logger.info(f"\n{'='*80}")
    logger.info(f"SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Co-authors analyzed: {len(results)}")
    logger.info(f"Total corporate connections: {total_corporates}")

    return summary
