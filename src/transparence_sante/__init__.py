"""
Transparence Santé API integration for detecting financial links between
healthcare professionals and pharmaceutical/medical device companies.

This module provides evidence-based detection of financial relationships
through the French public database of conflicts of interest.
"""

from src.transparence_sante.client import (
    TransparenceSanteClient,
    FinancialDeclaration,
    TransparenceSanteSearchResult,
)

__all__ = [
    "TransparenceSanteClient",
    "FinancialDeclaration",
    "TransparenceSanteSearchResult",
]
