"""
Phase 2.5: Filter secondary source matches using coauthor validation.

After Phase 1 collects data from TS/CT/Patents, this module:
1. Extracts coauthor metadata (domains, years active) from OpenAlex
2. Validates each matched coauthor on secondary sources
3. Returns filtered data (only validated matches)

This ensures we only create corporate links for the RIGHT person
(avoids homonymes).
"""

from typing import Dict, List, Set, Tuple, Any
from src.logger import logger
from src.pathfinding.coauthor_matcher_openai import CoauthorMatcherOpenAI
from src.transparence_sante import FinancialDeclaration


def _extract_coauthor_metadata(coauthor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from OpenAlex coauthor for validation.

    Returns:
        {
            'name': str,
            'domains': list,
            'years_min': int,
            'years_max': int
        }
    """
    # Get years from publications
    pubs = coauthor.get('publications', [])
    years = [p.get('year') for p in pubs if p.get('year')]

    return {
        'name': coauthor.get('name', ''),
        'domains': coauthor.get('research_areas', []),
        'years_min': min(years) if years else 2000,
        'years_max': max(years) if years else 2026
    }


def filter_transparence_sante_matches(
    coauthor_oa: Dict[str, Any],
    ts_declarations: List[FinancialDeclaration],
    matcher: CoauthorMatcherOpenAI
) -> List[FinancialDeclaration]:
    """
    Filter TS declarations: keep only matches that validate as same person.

    Args:
        coauthor_oa: Coauthor from OpenAlex with domains/years
        ts_declarations: List of TS declarations found for this coauthor
        matcher: CoauthorMatcherOpenAI instance

    Returns:
        Validated TS declarations only
    """
    if not ts_declarations:
        return []

    metadata = _extract_coauthor_metadata(coauthor_oa)
    validated = []

    for decl in ts_declarations:
        # Validate: is this the same person?
        is_same = matcher.is_same_person(
            oa_name=metadata['name'],
            oa_domains=metadata['domains'],
            oa_years_min=metadata['years_min'],
            oa_years_max=metadata['years_max'],
            candidate_name=decl.full_beneficiary_name,
            candidate_year=int(decl.date.split('-')[0]) if decl.date else 2020,
            candidate_context=f"Sector: {decl.sector}, Profession: {decl.beneficiary_profession}"
        )

        if is_same:
            validated.append(decl)
        else:
            logger.debug(
                f"  ✗ TS rejected homonyme: {decl.full_beneficiary_name} "
                f"({decl.sector}) is not {metadata['name']}"
            )

    logger.info(
        f"  ✓ TS: {len(validated)}/{len(ts_declarations)} declarations validated for {metadata['name']}"
    )
    return validated


def filter_clinical_trials_matches(
    coauthor_oa: Dict[str, Any],
    ct_links: List[Dict[str, Any]],
    matcher: CoauthorMatcherOpenAI
) -> List[Dict[str, Any]]:
    """
    Filter Clinical Trials links: keep only matches that validate as same person.

    Args:
        coauthor_oa: Coauthor from OpenAlex
        ct_links: List of trial links found
        matcher: CoauthorMatcherOpenAI instance

    Returns:
        Validated CT links only
    """
    if not ct_links:
        return []

    metadata = _extract_coauthor_metadata(coauthor_oa)
    validated = []

    for link in ct_links:
        # Validate: is this the same person?
        is_same = matcher.is_same_person(
            oa_name=metadata['name'],
            oa_domains=metadata['domains'],
            oa_years_min=metadata['years_min'],
            oa_years_max=metadata['years_max'],
            candidate_name=link.get('researcher', link.get('pi_name', '')),
            candidate_year=link.get('year', 2020),
            candidate_context=link.get('study_title', '')
        )

        if is_same:
            validated.append(link)
        else:
            logger.debug(
                f"  ✗ CT rejected homonyme: {link.get('researcher')} "
                f"is not {metadata['name']}"
            )

    logger.info(
        f"  ✓ CT: {len(validated)}/{len(ct_links)} trials validated for {metadata['name']}"
    )
    return validated


def filter_patents_by_coauthor(
    coauthor_oa: Dict[str, Any],
    all_patents: List[Dict[str, Any]],
    matcher: CoauthorMatcherOpenAI
) -> List[Dict[str, Any]]:
    """
    Filter Patents for a specific coauthor: keep only matches that validate as same person.

    Args:
        coauthor_oa: Coauthor from OpenAlex
        all_patents: Full list of patents (will search for ones with this coauthor)
        matcher: CoauthorMatcherOpenAI instance

    Returns:
        Validated patents for this coauthor only
    """
    if not all_patents:
        return []

    metadata = _extract_coauthor_metadata(coauthor_oa)
    coauthor_name = metadata['name']
    validated = []

    for patent in all_patents:
        # Check if coauthor is listed in co_inventors
        co_inventors = patent.get('co_inventors', [])

        # Find matches in co_inventors
        matching_inventors = [
            inv for inv in co_inventors
            if inv.lower() == coauthor_name.lower() or
               inv.split()[-1].lower() == coauthor_name.split()[-1].lower()
        ]

        if not matching_inventors:
            continue  # This patent doesn't involve this coauthor

        # Validate: is this the same person?
        for inventor_name in matching_inventors:
            is_same = matcher.is_same_person(
                oa_name=metadata['name'],
                oa_domains=metadata['domains'],
                oa_years_min=metadata['years_min'],
                oa_years_max=metadata['years_max'],
                candidate_name=inventor_name,
                candidate_year=patent.get('year', 2020),
                candidate_context=f"Title: {patent.get('title', '')}"
            )

            if is_same:
                validated.append(patent)
                break  # Only add patent once per coauthor
            else:
                logger.debug(
                    f"  ✗ Patent rejected homonyme: {inventor_name} "
                    f"is not {metadata['name']}"
                )

    logger.info(
        f"  ✓ Patents: {len(validated)} patents validated for {metadata['name']}"
    )
    return validated


def apply_phase2_5_filtering(
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply Phase 2.5 validation filtering to collected data.

    Modifies data in-place, keeping only validated matches.

    Data structure expected:
    - data['scholar']: OpenAlex profile
    - data['coauthors']: List of coauthors (from scholar)
    - data['patents']: List of patents (global, not keyed by coauthor)
    - data['transparence_sante_declarations']: Dict[coauthor_name, List[FinancialDeclaration]]
    - data['clinical_trials_links']: Dict[coauthor_name, List[CorporateLink]]

    Args:
        data: Dictionary with Phase 1 collected data

    Returns:
        Same data dict (modified with filtered results)
    """
    logger.info("\n2️⃣.5️⃣  Phase 2.5: Validating coauthor matches...")

    matcher = CoauthorMatcherOpenAI()

    coauthors = data.get('coauthors', [])
    ts_declarations = data.get('transparence_sante_declarations', {})
    ct_links = data.get('clinical_trials_links', {})
    all_patents = data.get('patents', [])

    # Filter each source by coauthor
    for coauthor in coauthors:
        coauthor_name = coauthor.get('name', '')

        # Filter TS for this coauthor
        if coauthor_name in ts_declarations:
            ts_declarations[coauthor_name] = filter_transparence_sante_matches(
                coauthor,
                ts_declarations[coauthor_name],
                matcher
            )

        # Filter CT for this coauthor
        if coauthor_name in ct_links:
            ct_links[coauthor_name] = filter_clinical_trials_matches(
                coauthor,
                ct_links[coauthor_name],
                matcher
            )

        # Filter Patents for this coauthor (from global patents list)
        coauthor_patents = filter_patents_by_coauthor(
            coauthor,
            all_patents,
            matcher
        )

        # Store validated patents in a dict (for consistency with TS/CT)
        if coauthor_patents:
            if 'patents_by_coauthor' not in data:
                data['patents_by_coauthor'] = {}
            data['patents_by_coauthor'][coauthor_name] = coauthor_patents

    logger.info(f"⏱  Phase 2.5 complete")
    return data
