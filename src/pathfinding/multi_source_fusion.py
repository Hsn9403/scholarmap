"""
Multi-source data fusion for robust co-author disambiguation.

STRATEGY:
- PRIMARY SOURCE: Google Scholar (co-authors list with scholar_id - MOST RELIABLE)
- ENRICHMENT 1: OpenAlex (affiliations, institutional history)
- ENRICHMENT 2: Google Patents (patents → assignees → corporates)
- VALIDATION: Cross-check between sources for confidence scoring

This approach gives us:
1. Google Scholar's validated co-author list (they already did disambiguation!)
2. OpenAlex's rich affiliation data (institutions over time)
3. Patents' direct corporate connections (assignees)
"""
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from src.logger import logger
from src.models import ScholarData, CoAuthor
from src.scholar.client import ScholarClient
from src.patents.client import PatentsClient
from src.pathfinding.openalex_client import OpenAlexClient
from src.pathfinding.ror_client import RORClient
from src.pathfinding.patent_inventor_validation import validate_inventor_on_patents


@dataclass
class CorporateConnection:
    """A validated corporate connection with evidence."""
    corporate_name: str
    confidence_score: float  # 0.0 to 1.0
    source: str  # "openalex_affiliation", "patent_assignee", "both"
    ror_id: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MultiSourceProfile:
    """Complete profile of a co-author from all sources."""
    name: str

    # Google Scholar data
    scholar_id: Optional[str] = None
    scholar_h_index: int = 0
    scholar_publications_count: int = 0
    scholar_affiliation: Optional[str] = None

    # OpenAlex data
    openalex_id: Optional[str] = None
    openalex_affiliations: List[Dict[str, Any]] = field(default_factory=list)

    # Patents data
    patents_count: int = 0
    patent_assignees: List[str] = field(default_factory=list)

    # Validated corporate connections
    corporate_connections: List[CorporateConnection] = field(default_factory=list)

    # Cross-source validation
    validation_score: float = 0.0  # 0.0 to 1.0 (confidence that all sources refer to same person)


class MultiSourceFusion:
    """
    Fuse data from multiple sources (Scholar, OpenAlex, Patents) for robust disambiguation.
    """

    def __init__(
        self,
        scholar_client: Optional[ScholarClient] = None,
        openalex_client: Optional[OpenAlexClient] = None,
        patents_client: Optional[PatentsClient] = None,
        ror_client: Optional[RORClient] = None
    ):
        """Initialize with API clients."""
        self.scholar_client = scholar_client or ScholarClient()
        self.openalex_client = openalex_client or OpenAlexClient()
        self.patents_client = patents_client or PatentsClient()
        self.ror_client = ror_client or RORClient()

    def get_complete_coauthor_profile(
        self,
        coauthor: CoAuthor,
        seed_scientist_scholar_data: ScholarData,
        max_publications_openalex: int = 50,
        max_patents: int = 20
    ) -> MultiSourceProfile:
        """
        Build complete profile for a co-author by fusing all sources.

        Workflow:
        1. Start with Scholar data (already validated by Google)
        2. Enrich with OpenAlex (affiliations)
        3. Enrich with Patents (assignees)
        4. Cross-validate and compute confidence
        5. Extract corporate connections

        Args:
            coauthor: CoAuthor from Google Scholar (with scholar_id).
            seed_scientist_scholar_data: Scholar data of main scientist (for validation).
            max_publications_openalex: Max publications to fetch from OpenAlex.
            max_patents: Max patents to fetch.

        Returns:
            MultiSourceProfile with all data fused.
        """
        logger.info("="*70)
        logger.info(f"Building multi-source profile for: {coauthor.name}")
        if coauthor.scholar_id:
            logger.info(f"  Scholar ID: {coauthor.scholar_id}")
        logger.info("="*70)

        profile = MultiSourceProfile(name=coauthor.name)

        # STEP 1: Google Scholar data (PRIMARY SOURCE)
        profile = self._enrich_with_scholar(profile, coauthor)

        # STEP 2: OpenAlex enrichment (AFFILIATIONS)
        profile = self._enrich_with_openalex(
            profile,
            coauthor,
            seed_scientist_scholar_data,
            max_publications_openalex
        )

        # STEP 3: Patents enrichment (ASSIGNEES → CORPORATES)
        profile = self._enrich_with_patents(profile, coauthor.name, max_patents)

        # STEP 4: Cross-source validation
        profile.validation_score = self._compute_validation_score(profile, coauthor)

        # STEP 5: Extract and classify corporate connections
        profile.corporate_connections = self._extract_corporate_connections(profile)

        logger.info(f"\n{'='*70}")
        logger.info(f"PROFILE SUMMARY: {profile.name}")
        logger.info(f"{'='*70}")
        logger.info(f"  Validation score: {profile.validation_score:.2f}")
        logger.info(f"  Scholar publications: {profile.scholar_publications_count}")
        logger.info(f"  OpenAlex affiliations: {len(profile.openalex_affiliations)}")
        logger.info(f"  Patents: {profile.patents_count}")
        logger.info(f"  Corporate connections: {len(profile.corporate_connections)}")

        return profile

    def _enrich_with_scholar(
        self,
        profile: MultiSourceProfile,
        coauthor: CoAuthor
    ) -> MultiSourceProfile:
        """Enrich profile with Google Scholar data."""
        logger.info("\n[1/5] Enriching with Google Scholar...")

        if not coauthor.scholar_id:
            logger.warning("  → No Scholar ID available, skipping Scholar enrichment")
            return profile

        try:
            scholar_data = self.scholar_client.fetch_author_data(
                coauthor.scholar_id,
                num_articles=10  # We only need basic info
            )

            profile.scholar_id = coauthor.scholar_id
            profile.scholar_h_index = scholar_data.h_index
            profile.scholar_publications_count = len(scholar_data.top_publications)
            profile.scholar_affiliation = scholar_data.affiliation

            logger.info(f"  ✓ Scholar data: {profile.scholar_publications_count} pubs, h-index: {profile.scholar_h_index}")
            logger.info(f"    Affiliation: {profile.scholar_affiliation}")

        except Exception as e:
            logger.warning(f"  ✗ Failed to fetch Scholar data: {e}")

        return profile

    def _enrich_with_openalex(
        self,
        profile: MultiSourceProfile,
        coauthor: CoAuthor,
        seed_scientist_scholar_data: ScholarData,
        max_publications: int
    ) -> MultiSourceProfile:
        """Enrich profile with OpenAlex affiliations."""
        logger.info("\n[2/5] Enriching with OpenAlex...")

        try:
            # Search for author in OpenAlex by name
            openalex_author = self.openalex_client.search_author(coauthor.name)

            if not openalex_author:
                logger.warning(f"  → Not found in OpenAlex")
                return profile

            profile.openalex_id = openalex_author["id"]
            logger.info(f"  ✓ Found in OpenAlex: {openalex_author['display_name']}")
            logger.info(f"    ID: {profile.openalex_id}")

            # Get author's works to extract affiliations
            works = self.openalex_client.get_author_works(
                profile.openalex_id,
                max_results=max_publications
            )

            # Extract affiliations with temporal data
            affiliations = self.openalex_client.extract_affiliations_from_works(
                works,
                author_id=profile.openalex_id
            )

            profile.openalex_affiliations = affiliations
            logger.info(f"  ✓ Extracted {len(affiliations)} affiliations")

            # Show top affiliations
            for i, aff in enumerate(affiliations[:3], 1):
                logger.info(
                    f"    {i}. {aff['display_name']} "
                    f"({aff['works_count']} works, type: {aff['type']})"
                )

            # VALIDATION: Check if OpenAlex data matches Scholar data
            if profile.scholar_affiliation:
                # Simple check: does Scholar affiliation appear in OpenAlex affiliations?
                scholar_aff_normalized = profile.scholar_affiliation.lower()
                found_match = any(
                    scholar_aff_normalized in aff['display_name'].lower()
                    for aff in affiliations
                    if aff['display_name']
                )

                if found_match:
                    logger.info(f"  ✓ OpenAlex affiliations MATCH Scholar affiliation")
                else:
                    logger.warning(
                        f"  ⚠ OpenAlex affiliations DON'T match Scholar affiliation "
                        f"(might be different person or outdated data)"
                    )

        except Exception as e:
            logger.warning(f"  ✗ Failed to enrich with OpenAlex: {e}")

        return profile

    def _enrich_with_patents(
        self,
        profile: MultiSourceProfile,
        name: str,
        max_patents: int
    ) -> MultiSourceProfile:
        """Enrich profile with Patents data."""
        logger.info("\n[3/5] Enriching with Google Patents...")

        try:
            patents_data = self.patents_client.fetch_patents_data(
                inventor_name=name,
                max_patents=max_patents
            )

            # VALIDATION: Check for name mixing (avoid "Thierry + Colin" = "Thierry Colin")
            is_valid_inventor = validate_inventor_on_patents(name, patents_data)

            if not is_valid_inventor:
                logger.warning(
                    f"  ✗ Name mixing detected in patents! "
                    f"This might be a false positive (e.g., 'Thierry Iung' + 'Christine Colin'). "
                    f"Skipping patents data."
                )
                return profile

            profile.patents_count = len(patents_data.top_patents)

            # Extract unique assignees
            assignees_set = set()
            for patent in patents_data.top_patents:
                if patent.assignee:
                    assignees_set.add(patent.assignee)

            profile.patent_assignees = list(assignees_set)

            logger.info(f"  ✓ Found {profile.patents_count} patents")
            logger.info(f"  ✓ Unique assignees: {len(profile.patent_assignees)}")

            for i, assignee in enumerate(profile.patent_assignees[:5], 1):
                logger.info(f"    {i}. {assignee}")

        except Exception as e:
            logger.warning(f"  ✗ Failed to enrich with Patents: {e}")

        return profile

    def _compute_validation_score(
        self,
        profile: MultiSourceProfile,
        coauthor: CoAuthor
    ) -> float:
        """
        Compute cross-source validation score.

        High score = high confidence that all sources refer to the same person.

        Scoring factors:
        - Has Scholar ID: +0.4 (Google already validated)
        - Has OpenAlex ID: +0.2
        - OpenAlex affiliations match Scholar: +0.2
        - Has validated patents (no name mixing): +0.2
        """
        logger.info("\n[4/5] Computing validation score...")

        score = 0.0

        # Factor 1: Scholar ID (most reliable)
        if profile.scholar_id:
            score += 0.4
            logger.debug("  +0.4: Has Scholar ID (validated by Google)")

        # Factor 2: OpenAlex ID
        if profile.openalex_id:
            score += 0.2
            logger.debug("  +0.2: Has OpenAlex ID")

        # Factor 3: Affiliation consistency
        if profile.scholar_affiliation and profile.openalex_affiliations:
            scholar_aff_norm = profile.scholar_affiliation.lower()
            match_found = any(
                scholar_aff_norm in aff['display_name'].lower()
                for aff in profile.openalex_affiliations
                if aff['display_name']
            )

            if match_found:
                score += 0.2
                logger.debug("  +0.2: OpenAlex affiliations match Scholar")
            else:
                logger.debug("  +0.0: No affiliation match (might be different person)")

        # Factor 4: Patents (validated, no name mixing)
        if profile.patents_count > 0:
            score += 0.2
            logger.debug(f"  +0.2: Has {profile.patents_count} validated patents")

        logger.info(f"  → Validation score: {score:.2f}")

        return score

    def _extract_corporate_connections(
        self,
        profile: MultiSourceProfile
    ) -> List[CorporateConnection]:
        """
        Extract and classify corporate connections from all sources.

        Corporates can come from:
        1. OpenAlex affiliations (type = "company" in ROR)
        2. Patent assignees (direct corporate connection)

        Returns:
            List of CorporateConnection with confidence scores.
        """
        logger.info("\n[5/5] Extracting corporate connections...")

        connections: Dict[str, CorporateConnection] = {}

        # SOURCE 1: OpenAlex affiliations
        for aff in profile.openalex_affiliations:
            inst_name = aff.get("display_name")
            ror_id = aff.get("ror")

            if not inst_name:
                continue

            # Classify with ROR
            classification = self.ror_client.classify_organization(inst_name, ror_id)

            if classification["is_corporate"]:
                # Create or update connection
                if inst_name not in connections:
                    connections[inst_name] = CorporateConnection(
                        corporate_name=inst_name,
                        confidence_score=classification["confidence"],
                        source="openalex_affiliation",
                        ror_id=ror_id,
                        evidence=[]
                    )

                # Add evidence
                connections[inst_name].evidence.append({
                    "source": "openalex",
                    "works_count": aff.get("works_count", 0),
                    "years": aff.get("years", []),
                    "type": aff.get("type")
                })

                logger.info(
                    f"  ✓ Corporate (OpenAlex): {inst_name} "
                    f"({aff.get('works_count', 0)} works, confidence: {classification['confidence']:.2f})"
                )

        # SOURCE 2: Patent assignees
        for assignee in profile.patent_assignees:
            # Classify assignee
            classification = self.ror_client.classify_organization(assignee, ror_id=None)

            if classification["is_corporate"]:
                # Check if already exists (from OpenAlex)
                if assignee in connections:
                    # Upgrade source to "both"
                    connections[assignee].source = "both"
                    connections[assignee].confidence_score = min(
                        1.0,
                        connections[assignee].confidence_score + 0.2  # Boost confidence
                    )
                    logger.info(
                        f"  ✓ Corporate (BOTH sources): {assignee} "
                        f"(confidence boosted to {connections[assignee].confidence_score:.2f})"
                    )
                else:
                    # New connection from patents only
                    connections[assignee] = CorporateConnection(
                        corporate_name=assignee,
                        confidence_score=classification["confidence"],
                        source="patent_assignee",
                        ror_id=None,
                        evidence=[]
                    )
                    logger.info(
                        f"  ✓ Corporate (Patents): {assignee} "
                        f"(confidence: {classification['confidence']:.2f})"
                    )

                # Add patent evidence
                connections[assignee].evidence.append({
                    "source": "patents",
                    "role": "assignee"
                })

        connections_list = sorted(
            connections.values(),
            key=lambda x: x.confidence_score,
            reverse=True
        )

        logger.info(f"  → Total corporate connections: {len(connections_list)}")

        return connections_list


def scan_coauthors_multi_source(
    scientist_name: str,
    scientist_scholar_id: Optional[str] = None,
    max_coauthors: int = 20,
    max_publications_openalex: int = 50,
    max_patents: int = 20,
    min_validation_score: float = 0.4
) -> Dict[str, Any]:
    """
    Main function: Scan co-authors using multi-source fusion.

    This implements the PRIORITY #1 workflow with robust disambiguation.

    Args:
        scientist_name: Name of the main scientist.
        scientist_scholar_id: Scholar ID if known.
        max_coauthors: Max co-authors to scan.
        max_publications_openalex: Max OpenAlex publications per co-author.
        max_patents: Max patents per co-author.
        min_validation_score: Minimum validation score to keep a co-author.

    Returns:
        Dict with results for each co-author.
    """
    fusion = MultiSourceFusion()

    logger.info("="*80)
    logger.info("MULTI-SOURCE CO-AUTHOR SCANNING")
    logger.info(f"Scientist: {scientist_name}")
    logger.info("="*80)

    # STEP 1: Get scientist's Scholar profile
    logger.info("\n[Step 1/3] Getting scientist's Google Scholar profile...")

    if scientist_scholar_id:
        logger.info(f"  Using provided Scholar ID: {scientist_scholar_id}")
        scientist_scholar_data = fusion.scholar_client.fetch_author_data(
            scientist_scholar_id,
            num_articles=30
        )
    else:
        # Search by name
        candidates = fusion.scholar_client.find_candidates(scientist_name, num=5)
        if not candidates:
            return {
                "error": f"Scientist not found in Google Scholar: {scientist_name}",
                "scientist": None,
                "coauthors": {}
            }

        scientist_scholar_id = candidates[0].author_id
        scientist_scholar_data = fusion.scholar_client.fetch_author_data(
            scientist_scholar_id,
            num_articles=30
        )

    logger.info(f"  ✓ Found: {scientist_scholar_data.name}")
    logger.info(f"    Co-authors listed: {len(scientist_scholar_data.coauthors)}")

    # STEP 2: Process each co-author
    logger.info(f"\n[Step 2/3] Processing {min(max_coauthors, len(scientist_scholar_data.coauthors))} co-authors...")

    results = {}
    coauthors_to_scan = scientist_scholar_data.coauthors[:max_coauthors]

    for i, coauthor in enumerate(coauthors_to_scan, 1):
        logger.info(f"\n{'#'*80}")
        logger.info(f"CO-AUTHOR {i}/{len(coauthors_to_scan)}")
        logger.info(f"{'#'*80}")

        # Build complete profile
        profile = fusion.get_complete_coauthor_profile(
            coauthor,
            scientist_scholar_data,
            max_publications_openalex,
            max_patents
        )

        # Filter by validation score
        if profile.validation_score < min_validation_score:
            logger.warning(
                f"\n✗ Skipping {profile.name}: validation score too low "
                f"({profile.validation_score:.2f} < {min_validation_score})"
            )
            continue

        # Add to results
        if profile.corporate_connections:
            results[profile.name] = {
                "scholar_id": profile.scholar_id,
                "openalex_id": profile.openalex_id,
                "validation_score": profile.validation_score,
                "scholar_h_index": profile.scholar_h_index,
                "scholar_affiliation": profile.scholar_affiliation,
                "patents_count": profile.patents_count,
                "corporate_connections": [
                    {
                        "name": conn.corporate_name,
                        "confidence": conn.confidence_score,
                        "source": conn.source,
                        "ror_id": conn.ror_id,
                        "evidence": conn.evidence
                    }
                    for conn in profile.corporate_connections
                ]
            }

            logger.info(
                f"\n✓ KEPT {profile.name}: "
                f"{len(profile.corporate_connections)} corporate connection(s), "
                f"validation: {profile.validation_score:.2f}"
            )
        else:
            logger.info(f"\n→ No corporate connections for {profile.name}")

    # STEP 3: Summary
    logger.info(f"\n{'='*80}")
    logger.info("FINAL SUMMARY")
    logger.info(f"{'='*80}")

    total_corporates = sum(
        len(data["corporate_connections"])
        for data in results.values()
    )

    summary = {
        "scientist": {
            "name": scientist_scholar_data.name,
            "scholar_id": scientist_scholar_id,
            "h_index": scientist_scholar_data.h_index,
            "affiliation": scientist_scholar_data.affiliation,
            "coauthors_total": len(scientist_scholar_data.coauthors)
        },
        "coauthors_analyzed": len(results),
        "total_corporate_connections": total_corporates,
        "coauthors": results
    }

    logger.info(f"Co-authors analyzed: {len(results)}")
    logger.info(f"Total corporate connections: {total_corporates}")

    return summary
