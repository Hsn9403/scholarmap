#!/usr/bin/env python3
"""
Crossref API client for enriching author names.

This module provides a client for the Crossref REST API to fetch publication
metadata and enrich author names from "Initial + Lastname" format (e.g., "A. Nedelec")
to "Firstname + Lastname" format (e.g., "Alice Nedelec").

API Documentation: https://api.crossref.org/
Rate Limits: Polite pool with mailto parameter recommended (50 requests/sec)
"""
from __future__ import annotations

import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from src.logger import logger, log_api_call, log_error
from src.exceptions import APIError


class CrossrefClient:
    """
    Client for interacting with Crossref REST API.

    This client fetches publication metadata to enrich author names.
    By searching for publications with a specific title and comparing authors,
    we can resolve "A. Nedelec" to "Alice Nedelec".

    The API is free and doesn't require authentication, but using a mailto
    parameter places you in the "polite pool" with better rate limits.

    Attributes:
        base_url: Base URL for Crossref REST API.
        session: Requests session for connection pooling.
        mailto: Email for polite pool access (optional but recommended).

    Example:
        >>> client = CrossrefClient(mailto="research@example.com")
        >>> authors = client.get_paper_authors("Fluorescent multifunctional...")
        >>> print(f"Authors: {', '.join(authors)}")
    """

    BASE_URL = "https://api.crossref.org"

    def __init__(self, mailto: Optional[str] = None):
        """
        Initialize the Crossref client.

        Args:
            mailto: Email address for polite pool access (recommended).
                   Provides better rate limits (50 req/s vs 50 req/s burst).
        """
        self.base_url = self.BASE_URL
        self.mailto = mailto
        self.session = requests.Session()

        # Simple in-memory cache to avoid duplicate requests
        self._cache: Dict[str, Any] = {}

        # Set user agent (required for polite pool)
        user_agent = "Scholarmap/1.0 (Academic Research)"
        if mailto:
            user_agent += f"; mailto:{mailto}"
        self.session.headers["User-Agent"] = user_agent

        logger.debug(f"CrossrefClient initialized (mailto={mailto or 'not set'})")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to Crossref API.

        Args:
            endpoint: API endpoint (e.g., "/works").
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"

        # Add mailto to params if configured (for polite pool)
        if self.mailto:
            params = params or {}
            params["mailto"] = self.mailto

        try:
            log_api_call("crossref", {"endpoint": endpoint, "params": params})
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(
                    "Crossref API rate limit exceeded (429). "
                    "Consider using mailto parameter for polite pool. "
                    "Will continue without Crossref enrichment."
                )
                raise APIError(
                    "Crossref API rate limit exceeded. "
                    "Continuing without enrichment."
                ) from e
            log_error(e, f"Crossref API HTTP error: {e.response.status_code}")
            raise APIError(f"Crossref API request failed: {e}") from e
        except requests.RequestException as e:
            log_error(e, "Crossref API request failed")
            raise APIError(f"Failed to connect to Crossref API: {e}") from e
        except ValueError as e:
            log_error(e, "Invalid JSON response from Crossref")
            raise APIError("Invalid response from Crossref API") from e

    def search_work_by_title(
        self,
        title: str,
        rows: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a work by title and return metadata.

        Args:
            title: Publication title to search for.
            rows: Number of results to retrieve (default: 3).

        Returns:
            Best matching work metadata dict, or None if not found.

        Example:
            >>> work = client.search_work_by_title("Machine learning applications")
            >>> if work:
            ...     print(f"Found: {work['title'][0]}")
            ...     print(f"Authors: {len(work.get('author', []))}")
        """
        # Clean title for search
        title_clean = title.strip()
        if not title_clean:
            logger.warning("Empty title provided to search_work_by_title")
            return None

        # Check cache first
        cache_key = f"work:{title_clean.lower()}"
        if cache_key in self._cache:
            logger.debug(f"Using cached result for: {title_clean[:50]}...")
            return self._cache[cache_key]

        try:
            # Search using query.bibliographic (searches titles, authors, etc.)
            endpoint = "/works"
            params = {
                "query.bibliographic": title_clean,
                "rows": rows,
            }

            logger.debug(f"Searching Crossref for: {title_clean[:50]}...")
            result = self._make_request(endpoint, params)

            # Get works from response
            message = result.get("message", {})
            works = message.get("items", [])

            if not works:
                logger.warning(f"No results found on Crossref for: {title_clean[:50]}...")
                self._cache[cache_key] = None
                return None

            # Find best match by title similarity
            best_match = None
            best_score = 0.0

            for work in works:
                work_titles = work.get("title", [])
                if not work_titles:
                    continue

                work_title = work_titles[0].strip().lower()
                search_title = title_clean.lower()

                # Calculate similarity score
                score = self._calculate_title_similarity(work_title, search_title)

                if score > best_score:
                    best_score = score
                    best_match = work

            # Require at least 70% similarity
            if best_match and best_score >= 0.7:
                logger.info(
                    f"Found match on Crossref (score={best_score:.2f}): "
                    f"{best_match.get('title', [''])[0][:50]}..."
                )
                # Cache the result
                self._cache[cache_key] = best_match
                return best_match
            else:
                logger.warning(
                    f"No good match found on Crossref for: {title_clean[:50]}... "
                    f"(best score={best_score:.2f})"
                )
                # Cache negative result to avoid re-querying
                self._cache[cache_key] = None
                return None

        except APIError:
            raise
        except Exception as e:
            logger.warning(f"Error searching Crossref for '{title_clean[:50]}...': {e}")
            self._cache[cache_key] = None
            return None

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles.

        Args:
            title1: First title (normalized to lowercase).
            title2: Second title (normalized to lowercase).

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        # Exact match
        if title1 == title2:
            return 1.0

        # One contains the other
        if title1 in title2 or title2 in title1:
            # Calculate word overlap
            words1 = set(title1.split())
            words2 = set(title2.split())
            overlap = len(words1 & words2)
            total = len(words1 | words2)
            return overlap / total if total > 0 else 0.0

        # Calculate word overlap (Jaccard similarity)
        words1 = set(title1.split())
        words2 = set(title2.split())
        overlap = len(words1 & words2)
        total = len(words1 | words2)
        return overlap / total if total > 0 else 0.0

    def get_paper_authors(self, title: str) -> Optional[List[Dict[str, str]]]:
        """
        Get complete author list for a paper by title.

        Returns author information including first name, last name, and ORCID if available.

        Args:
            title: Publication title to search for.

        Returns:
            List of author dicts with keys: 'given' (first name), 'family' (last name),
            'ORCID' (optional), or None if not found.

        Example:
            >>> authors = client.get_paper_authors("Deep learning for biology")
            >>> if authors:
            ...     for author in authors:
            ...         print(f"{author.get('given', '')} {author.get('family', '')}")
        """
        try:
            work = self.search_work_by_title(title)
            if not work:
                return None

            authors_data = work.get("author", [])
            if not authors_data:
                return None

            return authors_data

        except APIError:
            # Rate limit or other API error - gracefully return None
            return None

    def get_paper_authors_full_names(self, title: str) -> Optional[List[str]]:
        """
        Get complete author names for a paper by title.

        This is a convenience method that returns full names as strings.

        Args:
            title: Publication title to search for.

        Returns:
            List of author names in "Firstname Lastname" format,
            or None if not found or rate limited.

        Example:
            >>> authors = client.get_paper_authors_full_names("Machine learning")
            >>> if authors:
            ...     print(f"Authors: {', '.join(authors)}")
        """
        authors_data = self.get_paper_authors(title)
        if not authors_data:
            return None

        # Build full names from given + family
        full_names = []
        for author in authors_data:
            given = author.get("given", "").strip()
            family = author.get("family", "").strip()

            if given and family:
                full_names.append(f"{given} {family}")
            elif family:
                # Only last name available
                full_names.append(family)

        return full_names if full_names else None

    def match_author_by_initial(
        self,
        initial_name: str,
        crossref_authors: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Match an author with initials to a full name from Crossref data.

        Args:
            initial_name: Name with initials (e.g., "A. Nedelec", "A Nedelec").
            crossref_authors: List of author dicts from Crossref API.

        Returns:
            Full name if match found (e.g., "Alice Nedelec"), or None.

        Example:
            >>> authors = [{"given": "Alice", "family": "Nedelec"}]
            >>> full_name = client.match_author_by_initial("A. Nedelec", authors)
            >>> print(full_name)  # "Alice Nedelec"
        """
        # Parse initial name
        parts = initial_name.replace(".", "").strip().split()
        if len(parts) < 2:
            return None

        # Extract initial(s) and last name
        initials = []
        for part in parts[:-1]:
            if part:
                initials.append(part[0].lower())

        lastname = parts[-1].lower()

        # Normalize for accent-insensitive comparison
        def normalize(s: str) -> str:
            """Remove accents for comparison."""
            nfd = unicodedata.normalize('NFD', s)
            return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')

        lastname_normalized = normalize(lastname)

        # Search in Crossref authors
        for author in crossref_authors:
            given = author.get("given", "").strip()
            family = author.get("family", "").strip()

            if not given or not family:
                continue

            # Check if last name matches (accent-insensitive)
            family_normalized = normalize(family.lower())
            if family_normalized != lastname_normalized:
                continue

            # Check if initials match
            given_initial = given[0].lower() if given else ""
            if given_initial in initials:
                # Found a match!
                full_name = f"{given} {family}"
                logger.info(
                    f"✨ Matched '{initial_name}' → '{full_name}' "
                    f"(initial {given_initial.upper()} matches)"
                )
                return full_name

        return None
