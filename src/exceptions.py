#!/usr/bin/env python3
"""Custom exceptions for the project."""
from __future__ import annotations


class SciDiligenceError(Exception):
    """Base exception for all project errors."""
    pass


class APIError(SciDiligenceError):
    """Error related to API calls (SerpAPI)."""
    pass


class DataParsingError(SciDiligenceError):
    """Error while parsing API response data."""
    pass


class ConfigurationError(SciDiligenceError):
    """Error in project configuration (missing API keys, etc.)."""
    pass


class DataNotFoundError(SciDiligenceError):
    """Requested data not found (no scholar profile, no patents, etc.)."""
    pass
