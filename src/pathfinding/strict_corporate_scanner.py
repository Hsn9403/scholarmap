"""
Corporate scanner with STRICT validation.

This module contains the 3 sources for finding corporate connections:
1. Patents (with inventor validation)
2. Publication affiliations (OpenAlex)
3. ClinicalTrials.gov

These functions are used by both the CLI scripts and the webapp.
"""
from typing import List, Optional
from src.logger import logger
from src.patents.client import PatentsClient
from src.pathfinding.ror_client import RORClient
from src.pathfinding.openalex_client import OpenAlexClient
from src.clinical_trials import ClinicalTrialsClient
from src.pathfinding.evidence_schema import (
    Evidence, EvidenceLevel, EvidenceType,
    create_patent_evidence
)
from src.pathfinding.evidence_validator import validate_patent_inventor
from src.pathfinding.publication_affiliation_scanner import (
    scan_coauthor_publications_for_corporate_affiliations,
    scan_shared_publications_for_coauthor_affiliations
)


def get_corporates_via_patents_STRICT(
    coauthor_name: str,
    coauthor_openalex_id: Optional[str],
    patents_client: PatentsClient,
    ror_client: RORClient,
    use_db: bool = False
) -> List[Evidence]:
    """
    Get corporate connections via patents with STRICT validation.

    CRITICAL: Verify that the co-author's name appears in the inventors list.

    Args:
        coauthor_name: Name of co-author.
        coauthor_openalex_id: OpenAlex ID (optional).
        patents_client: Patents client.
        ror_client: ROR client.
        use_db: If True, load from database instead of SerpAPI (default: False).

    Returns:
        List of Evidence objects (Level A or REJECTED).
    """
    evidence_list: List[Evidence] = []

    try:
        # Load patents from DB or SerpAPI
        if use_db:
            from src.database.adapters import scientist_to_patents_data
            patents_data = scientist_to_patents_data(scientist_name=coauthor_name)

            # Fallback to SerpAPI if DB has no patents
            if patents_data.patents_total == 0:
                logger.info(f"  No patents in DB, falling back to SerpAPI (cached)")
                patents_data = patents_client.fetch_patents_data(coauthor_name, max_patents=20)
        else:
            patents_data = patents_client.fetch_patents_data(coauthor_name, max_patents=20)

        if not patents_data or not patents_data.top_patents:
            logger.info(f"  No patents found")
            return []

        logger.info(f"  Checking {len(patents_data.top_patents)} patent(s)...")

        for patent in patents_data.top_patents:
            if not patent.current_assignee:
                continue

            # Classify assignee as corporate
            classification = ror_client.classify_organization(
                patent.current_assignee,
                ror_id=None
            )

            if not classification["is_corporate"]:
                logger.debug(f"  Assignee '{patent.current_assignee}' is not corporate (skipped)")
                continue

            inventors_list = []

            # Get ALL inventors from patent (complete list)
            if hasattr(patent, 'inventors') and patent.inventors:
                inventors_list = patent.inventors
            else:
                # No inventors list available - REJECT
                logger.warning(
                    f"  ✗ Patent {patent.patent_id}: No inventors list available (REJECTED)"
                )
                evidence = create_patent_evidence(
                    patent_id=patent.patent_id,
                    patent_title=patent.title,
                    patent_url=patent.link,
                    assignee=patent.current_assignee,
                    inventors_list=[],
                    coauthor_name=coauthor_name,
                    inventor_confirmed=False,
                    matching_inventor=None
                )
                evidence_list.append(evidence)
                continue

            # Validate inventor
            is_valid, matching_name, confidence = validate_patent_inventor(
                coauthor_name=coauthor_name,
                patent_inventors=inventors_list,
                patent_id=patent.patent_id,
                min_confidence=0.85
            )

            # Create evidence
            evidence = create_patent_evidence(
                patent_id=patent.patent_id,
                patent_title=patent.title,
                patent_url=patent.link,
                assignee=patent.current_assignee,
                inventors_list=inventors_list,
                coauthor_name=coauthor_name,
                inventor_confirmed=is_valid,
                matching_inventor=matching_name
            )

            evidence_list.append(evidence)

            if is_valid:
                logger.info(
                    f"  ✓ VERIFIED: {patent.current_assignee} "
                    f"(patent {patent.patent_id}, inventor: {matching_name})"
                )
            else:
                logger.warning(
                    f"  ✗ REJECTED: {patent.current_assignee} "
                    f"(patent {patent.patent_id}, inventor NOT confirmed)"
                )

    except Exception as e:
        logger.error(f"  Error checking patents: {e}")

    return evidence_list


def get_corporates_via_publications_STRICT(
    main_researcher_openalex_id: str,
    coauthor_name: str,
    coauthor_openalex_id: str,
    openalex_client: OpenAlexClient,
    ror_client: RORClient
) -> List[Evidence]:
    """
    Get corporate connections via publication affiliations.

    Args:
        main_researcher_openalex_id: Main researcher's OpenAlex ID.
        coauthor_name: Co-author's name.
        coauthor_openalex_id: Co-author's OpenAlex ID.
        openalex_client: OpenAlex client.
        ror_client: ROR client.

    Returns:
        List of Evidence objects (Level A).
    """
    logger.info(f"  Scanning publication affiliations...")

    # Scan SHARED publications first (more precise)
    evidence_list = scan_shared_publications_for_coauthor_affiliations(
        main_researcher_openalex_id=main_researcher_openalex_id,
        coauthor_openalex_id=coauthor_openalex_id,
        coauthor_name=coauthor_name,
        openalex_client=openalex_client,
        ror_client=ror_client
    )

    # If no results in shared publications, scan all co-author publications
    if not evidence_list:
        logger.info(f"  No corporate affiliations in shared publications, scanning all publications...")
        evidence_list = scan_coauthor_publications_for_corporate_affiliations(
            coauthor_openalex_id=coauthor_openalex_id,
            coauthor_name=coauthor_name,
            openalex_client=openalex_client,
            ror_client=ror_client,
            max_works=50
        )

    return evidence_list


def get_corporates_via_clinical_trials_STRICT(
    coauthor_name: str,
    clinical_trials_client: ClinicalTrialsClient,
    ror_client: RORClient
) -> List[Evidence]:
    """
    Get corporate connections via ClinicalTrials.gov.

    Only accepts trials where the co-author is Principal Investigator (PI).
    Detects corporates from sponsors and product/device names.

    Args:
        coauthor_name: Co-author's name.
        clinical_trials_client: ClinicalTrials client.
        ror_client: ROR client.

    Returns:
        List of Evidence objects (Level A if PI, otherwise REJECTED).
    """
    evidence_list: List[Evidence] = []

    try:
        # Search clinical trials for this co-author
        ct_results = clinical_trials_client.find_corporate_links(
            coauthor_name,
            max_studies=50
        )

        if ct_results.total_studies_found == 0:
            logger.info(f"  No clinical trials found")
            return []

        logger.info(f"  Found {ct_results.total_studies_found} clinical trial(s)")
        logger.info(f"  PI in {ct_results.studies_as_pi} trial(s)")

        # Process each corporate link
        for link in ct_results.corporate_links:
            # Classify as corporate (ClinicalTrials client already filters for corporates)
            classification = ror_client.classify_organization(
                link.corporate,
                ror_id=None
            )

            if not classification["is_corporate"]:
                logger.debug(f"  Sponsor '{link.corporate}' is not corporate (skipped)")
                continue

            # Create evidence
            evidence = Evidence(
                corporate_name=link.corporate,
                evidence_type=EvidenceType.CLINICAL_TRIAL,
                evidence_level=EvidenceLevel.LEVEL_A,  # PI = Level A
                raw_data={
                    "nct_id": link.nct_id,
                    "study_title": link.study_title,
                    "study_url": link.study_url,
                    "detection_field": link.detection_field,
                    "raw_value": link.raw_value,
                    "investigator_role": "Principal Investigator"
                },
                confidence_score=1.0,
                validation_notes=f"Co-author is PI on clinical trial {link.nct_id}"
            )

            evidence_list.append(evidence)

            logger.info(
                f"  ✓ {link.corporate} (NCT: {link.nct_id}, via {link.detection_field})"
            )

    except Exception as e:
        logger.error(f"  Error checking clinical trials: {e}")

    return evidence_list
