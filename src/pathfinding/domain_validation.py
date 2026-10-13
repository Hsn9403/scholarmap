"""
Domain validation for co-authors.

Problem: "A Ferrero" could match Alessandro Ferrero (microwave measurements)
         instead of Andrea Ferrero (CFD), leading to false corporate connections.

Solution: Validate that co-authors work in the same research domain using:
- Publication keywords/titles
- Research area overlap
- Affiliation coherence
"""
from typing import List, Optional, Set
import re
from src.models import ScholarData
from src.logger import logger


# Domain-specific keywords
CFD_KEYWORDS = {
    # Core CFD terms
    'cfd', 'computational fluid dynamics', 'fluid dynamics', 'fluid mechanics',
    'aerodynamics', 'hydrodynamics', 'turbulence', 'turbulent', 'laminar',
    'navier stokes', 'euler equations', 'flow simulation', 'flow field',

    # Methods
    'finite volume', 'finite element', 'lattice boltzmann', 'spectral method',
    'immersed boundary', 'vortex method', 'panel method', 'adjoint',

    # Applications
    'airfoil', 'wing', 'drag', 'lift', 'pressure', 'velocity field',
    'boundary layer', 'shock wave', 'supersonic', 'subsonic', 'transonic',
    'compressible', 'incompressible', 'viscous', 'inviscid',

    # Related fields
    'numerical simulation', 'shape optimization', 'aeroacoustics',
    'multiphase flow', 'heat transfer', 'combustion', 'mixing',
    'vorticity', 'streamline', 'wake', 'separation'
}

# Non-CFD domains that should trigger warnings
NON_CFD_DOMAINS = {
    # Electronics/Electrical
    'microwave', 'antenna', 'electromagnetic', 'rf circuit', 'radar',
    'signal processing', 'wireless', 'semiconductor', 'vlsi',

    # Biology/Medicine
    'cancer', 'tumor', 'pharmaceutical', 'drug', 'protein', 'gene',
    'medical', 'clinical', 'patient', 'disease', 'therapy', 'diagnosis',
    'microbiome', 'bacteria', 'enzyme', 'antibody',

    # Chemistry/Materials
    'cosmetics', 'skincare', 'polymer', 'catalyst', 'synthesis',
    'crystallography', 'spectroscopy',

    # Agriculture/Biology
    'crop', 'plant', 'agriculture', 'pest', 'insect', 'parasite',
    'soil', 'fertilizer', 'herbicide'
}


def validate_research_domain(
    seed_scientist: ScholarData,
    candidate_coauthor: ScholarData,
    min_overlap_ratio: float = 0.1
) -> tuple[bool, str]:
    """
    Validate that a candidate co-author works in the same research domain.

    Strategy:
    1. Extract keywords from publications of both scientists
    2. Check for domain overlap (CFD keywords)
    3. Check for domain mismatch (non-CFD keywords in candidate)
    4. Calculate overlap ratio

    Args:
        seed_scientist: The main scientist's data
        candidate_coauthor: The candidate co-author's data
        min_overlap_ratio: Minimum ratio of CFD keywords in candidate's work (0.1 = 10%)

    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    # Extract keywords from publications
    seed_keywords = _extract_keywords_from_publications(seed_scientist.top_publications)
    candidate_keywords = _extract_keywords_from_publications(candidate_coauthor.top_publications)

    # Check if seed scientist is in CFD domain
    seed_cfd_count = len(seed_keywords & CFD_KEYWORDS)
    seed_is_cfd = seed_cfd_count >= 3  # At least 3 CFD keywords

    if not seed_is_cfd:
        # If seed is not CFD, we can't validate domain (no baseline)
        logger.debug(f"Seed scientist doesn't appear to be in CFD domain, skipping domain validation")
        return True, "No baseline domain detected"

    # Check candidate for CFD keywords
    candidate_cfd_count = len(candidate_keywords & CFD_KEYWORDS)
    candidate_total = len(candidate_keywords)

    if candidate_total == 0:
        logger.warning(f"No keywords extracted from candidate's publications")
        return True, "Insufficient publication data for validation"

    cfd_ratio = candidate_cfd_count / candidate_total if candidate_total > 0 else 0

    # Check for non-CFD domain keywords
    candidate_non_cfd_count = len(candidate_keywords & NON_CFD_DOMAINS)
    non_cfd_ratio = candidate_non_cfd_count / candidate_total if candidate_total > 0 else 0

    # Decision logic
    if non_cfd_ratio > 0.3:  # More than 30% non-CFD keywords
        logger.warning(
            f"✗ DOMAIN MISMATCH: Candidate has {non_cfd_ratio*100:.1f}% non-CFD keywords "
            f"(found: {candidate_keywords & NON_CFD_DOMAINS})"
        )
        return False, f"Domain mismatch: {non_cfd_ratio*100:.1f}% non-CFD keywords"

    if cfd_ratio < min_overlap_ratio:
        logger.warning(
            f"✗ LOW CFD OVERLAP: Candidate has only {cfd_ratio*100:.1f}% CFD keywords "
            f"(threshold: {min_overlap_ratio*100:.1f}%)"
        )
        return False, f"Low CFD overlap: {cfd_ratio*100:.1f}%"

    # Success
    logger.info(
        f"✓ DOMAIN MATCH: Candidate has {cfd_ratio*100:.1f}% CFD keywords, "
        f"{non_cfd_ratio*100:.1f}% non-CFD"
    )
    return True, f"Domain match: {cfd_ratio*100:.1f}% CFD keywords"


def _extract_keywords_from_publications(publications: List) -> Set[str]:
    """
    Extract keywords from publication titles and sources.

    Args:
        publications: List of ScholarPublication objects

    Returns:
        Set of normalized keywords
    """
    keywords = set()

    for pub in publications:
        # Extract from title
        if pub.title:
            text = pub.title.lower()
            keywords.update(_extract_keywords_from_text(text))

        # Extract from source (journal name)
        if pub.source:
            text = pub.source.lower()
            keywords.update(_extract_keywords_from_text(text))

    return keywords


def _extract_keywords_from_text(text: str) -> Set[str]:
    """
    Extract meaningful keywords from text.

    Args:
        text: Text to extract keywords from

    Returns:
        Set of keywords
    """
    # Normalize text
    text = text.lower()

    # Remove special characters but keep spaces and hyphens
    text = re.sub(r'[^\w\s\-]', ' ', text)

    # Extract multi-word phrases (2-3 words) and single words
    keywords = set()

    # Check for multi-word CFD terms
    for keyword in CFD_KEYWORDS:
        if keyword in text:
            keywords.add(keyword)

    # Check for multi-word non-CFD terms
    for keyword in NON_CFD_DOMAINS:
        if keyword in text:
            keywords.add(keyword)

    # Extract single words (length >= 4 to avoid noise)
    words = text.split()
    for word in words:
        word = word.strip('-')
        if len(word) >= 4:
            keywords.add(word)

    return keywords


def validate_affiliation_coherence(
    seed_affiliation: Optional[str],
    candidate_affiliation: Optional[str]
) -> tuple[bool, str]:
    """
    Validate that candidate's affiliation is coherent with seed's domain.

    Checks for obvious mismatches like:
    - "Microwave Measurements" for a CFD researcher
    - "Department of Medicine" for an engineering researcher

    Args:
        seed_affiliation: Main scientist's affiliation
        candidate_affiliation: Candidate's affiliation

    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    if not candidate_affiliation:
        return True, "No affiliation to validate"

    candidate_affiliation_lower = candidate_affiliation.lower()

    # Red flags in affiliations
    red_flags = [
        'microwave',
        'antenna',
        'electromagnetic',
        'medicine',
        'medical',
        'hospital',
        'pharmacy',
        'pharmaceutical',
        'agriculture',
        'agronomy',
        'cosmetic',
        'beauty',
        'skincare'
    ]

    for red_flag in red_flags:
        if red_flag in candidate_affiliation_lower:
            logger.warning(
                f"✗ AFFILIATION MISMATCH: Found '{red_flag}' in affiliation: "
                f"{candidate_affiliation}"
            )
            return False, f"Affiliation mismatch: '{red_flag}' found"

    return True, "Affiliation coherent"
