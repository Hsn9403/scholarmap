"""
CMS Open Payments API integration for detecting financial links between
healthcare professionals and pharmaceutical/medical device companies in the US.

This module provides evidence-based detection of financial relationships
through the U.S. federal Sunshine Act public database (CMS Open Payments).

Free public API — no authentication required.
"""

from src.open_payments.client import (
    OpenPaymentsClient,
    OpenPaymentsRecord,
    OpenPaymentsSearchResult,
)

__all__ = [
    "OpenPaymentsClient",
    "OpenPaymentsRecord",
    "OpenPaymentsSearchResult",
]
