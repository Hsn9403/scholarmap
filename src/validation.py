#!/usr/bin/env python3
"""
Input validation module for security and data integrity.

Provides validation functions to prevent injection attacks and ensure
data integrity when processing external inputs.
"""
from __future__ import annotations
import re
from typing import Optional
from urllib.parse import urlparse

from src.exceptions import DataParsingError


# Validation patterns
_PATENT_ID_PATTERN = re.compile(r'^[A-Z]{2}[\dA-Z]+$')
_AUTHOR_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')
_SAFE_NAME_PATTERN = re.compile(r'^[A-Za-zÀ-ÿ\s\'\-\.]+$')


def validate_patent_id(patent_id: str, allow_empty: bool = False) -> str:
    """
    Validate and normalize a patent ID.

    Args:
        patent_id: Patent ID to validate (e.g., "US10000000" or "patent/US10000000/en").
        allow_empty: If True, empty string is valid and returned as-is.

    Returns:
        Normalized patent ID (just the document number like "US10000000").

    Raises:
        DataParsingError: If patent_id is invalid.

    Example:
        >>> validate_patent_id("US10000000")
        'US10000000'
        >>> validate_patent_id("patent/US10000000/en")
        'US10000000'
        >>> validate_patent_id("'; DROP TABLE patents;--")
        DataParsingError: Invalid patent ID format
    """
    if not patent_id or not patent_id.strip():
        if allow_empty:
            return ""
        raise DataParsingError("Patent ID cannot be empty")

    patent_id = patent_id.strip()

    # Extract from URL format
    if patent_id.startswith("patent/"):
        match = re.search(r"patent/([^/]+)/", patent_id)
        if match:
            patent_id = match.group(1)

    # Validate format (e.g., US10000000, EP1234567, WO2020123456)
    if not _PATENT_ID_PATTERN.match(patent_id):
        raise DataParsingError(
            f"Invalid patent ID format: {patent_id[:50]}. "
            "Expected format: US10000000, EP1234567, etc."
        )

    return patent_id


def validate_author_id(author_id: str) -> str:
    """
    Validate a Google Scholar author ID.

    Args:
        author_id: Author ID to validate (e.g., "xJaxiEEAAAAJ").

    Returns:
        Validated author ID.

    Raises:
        DataParsingError: If author_id is invalid.

    Example:
        >>> validate_author_id("xJaxiEEAAAAJ")
        'xJaxiEEAAAAJ'
        >>> validate_author_id("'; DROP TABLE authors;--")
        DataParsingError: Invalid author ID format
    """
    if not author_id or not author_id.strip():
        raise DataParsingError("Author ID cannot be empty")

    author_id = author_id.strip()

    # Author IDs are alphanumeric with dashes and underscores
    if not _AUTHOR_ID_PATTERN.match(author_id) or len(author_id) > 50:
        raise DataParsingError(
            f"Invalid author ID format: {author_id[:50]}. "
            "Expected alphanumeric characters, dashes, and underscores only."
        )

    return author_id


def validate_researcher_name(name: str) -> str:
    """
    Validate a researcher name input.

    Args:
        name: Researcher name to validate.

    Returns:
        Validated and normalized name (trimmed, single spaces).

    Raises:
        DataParsingError: If name is invalid or potentially malicious.

    Example:
        >>> validate_researcher_name("Marie Curie")
        'Marie Curie'
        >>> validate_researcher_name("Jean-Paul O'Connor")
        "Jean-Paul O'Connor"
        >>> validate_researcher_name("<script>alert('xss')</script>")
        DataParsingError: Invalid name format
    """
    if not name or not name.strip():
        raise DataParsingError("Researcher name cannot be empty")

    name = name.strip()

    # Check length (reasonable limit)
    if len(name) < 2 or len(name) > 100:
        raise DataParsingError(
            f"Researcher name must be between 2 and 100 characters (got {len(name)})"
        )

    # Check for safe characters (letters, spaces, hyphens, apostrophes, dots, accents)
    if not _SAFE_NAME_PATTERN.match(name):
        raise DataParsingError(
            f"Invalid name format: {name[:50]}. "
            "Name must contain only letters, spaces, hyphens, apostrophes, and dots."
        )

    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def validate_url(url: str, allowed_domains: Optional[list[str]] = None) -> str:
    """
    Validate a URL for security.

    Args:
        url: URL to validate.
        allowed_domains: Optional list of allowed domains (e.g., ["patents.google.com"]).

    Returns:
        Validated URL.

    Raises:
        DataParsingError: If URL is invalid or from disallowed domain.

    Example:
        >>> validate_url("https://patents.google.com/patent/US10000000/en")
        'https://patents.google.com/patent/US10000000/en'
        >>> validate_url("javascript:alert('xss')")
        DataParsingError: Invalid URL scheme
    """
    if not url or not url.strip():
        raise DataParsingError("URL cannot be empty")

    url = url.strip()

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise DataParsingError(f"Invalid URL format: {e}")

    # Check scheme (only http/https)
    if parsed.scheme not in ('http', 'https', ''):
        raise DataParsingError(
            f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."
        )

    # Check domain if restrictions provided
    if allowed_domains and parsed.netloc:
        if not any(parsed.netloc.endswith(domain) for domain in allowed_domains):
            raise DataParsingError(
                f"URL domain {parsed.netloc} not in allowed list: {allowed_domains}"
            )

    return url


def sanitize_api_param(value: str, max_length: int = 500) -> str:
    """
    Sanitize a string parameter for API calls.

    Removes potentially dangerous characters while preserving useful content.

    Args:
        value: Parameter value to sanitize.
        max_length: Maximum allowed length.

    Returns:
        Sanitized parameter value.

    Example:
        >>> sanitize_api_param("machine learning")
        'machine learning'
        >>> sanitize_api_param("test\x00value")
        'testvalue'
    """
    if not value:
        return ""

    # Remove null bytes and control characters
    value = re.sub(r'[\x00-\x1f\x7f]', '', value)

    # Truncate to max length
    value = value[:max_length]

    return value.strip()


def validate_integer(value: any, min_val: int = 1, max_val: int = 1000, param_name: str = "value") -> int:
    """
    Validate an integer parameter.

    Args:
        value: Value to validate (can be int, str, or other).
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.
        param_name: Parameter name for error messages.

    Returns:
        Validated integer.

    Raises:
        DataParsingError: If value is not a valid integer in range.

    Example:
        >>> validate_integer("10", min_val=1, max_val=100)
        10
        >>> validate_integer("9999", min_val=1, max_val=100)
        DataParsingError: value must be between 1 and 100
    """
    try:
        int_val = int(value)
    except (ValueError, TypeError):
        raise DataParsingError(f"{param_name} must be a valid integer")

    if int_val < min_val or int_val > max_val:
        raise DataParsingError(
            f"{param_name} must be between {min_val} and {max_val} (got {int_val})"
        )

    return int_val
