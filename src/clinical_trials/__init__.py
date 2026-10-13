"""
ClinicalTrials.gov API integration for detecting researcher-corporate links.

This module provides strict, evidence-based detection of collaborations
between academic researchers and corporate entities through clinical trial
sponsorship and involvement.
"""

from src.clinical_trials.client import (
    ClinicalTrialsClient,
    CorporateLink,
    ClinicalTrialsSearchResult,
    search_clinical_trials_corporate
)

__all__ = [
    "ClinicalTrialsClient",
    "CorporateLink",
    "ClinicalTrialsSearchResult",
    "search_clinical_trials_corporate"
]
