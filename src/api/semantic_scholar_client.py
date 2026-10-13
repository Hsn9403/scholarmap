#!/usr/bin/env python3
"""
Semantic Scholar API client for fetching publication metadata.

This module provides a client for the Semantic Scholar Academic Graph API,
which returns complete author lists and abstracts without truncation.

API Documentation: https://api.semanticscholar.org/
Rate Limits: 100 requests per 5 minutes (no API key required)
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from src.logger import logger, log_api_call, log_error
from src.exceptions import APIError


class SemanticScholarClient:
    """
    Client for interacting with Semantic Scholar API.

    This client fetches publication metadata including:
    - Complete author lists (no truncation with "...")
    - Abstracts
    - Citation counts
    - Publication year
    - Journal/venue information

    No API key required for basic usage.

    Attributes:
        base_url: Base URL for Semantic Scholar API.
        session: Requests session for connection pooling.
        last_request_time: Timestamp of last request for rate limiting.
        min_request_interval: Minimum seconds between requests (0.6s = ~100 req/min).

    Example:
        >>> client = SemanticScholarClient()
        >>> paper = client.search_paper_by_title("Fluorescent multifunctional...")
        >>> print(f"Authors: {len(paper['authors'])}")
        >>> print(f"Abstract: {paper['abstract'][:100]}...")
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Semantic Scholar client.

        Args:
            api_key: Optional API key for higher rate limits (not required).
        """
        self.base_url = self.BASE_URL
        self.api_key = api_key
        self.session = requests.Session()

        # Simple in-memory cache to avoid duplicate requests
        self._cache: Dict[str, Any] = {}

        # Set API key header if provided
        if api_key:
            self.session.headers["x-api-key"] = api_key

        # Set user agent
        self.session.headers["User-Agent"] = "Scholarmap/1.0 (Academic Research)"

        logger.debug("SemanticScholarClient initialized (no API key required)")

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to Semantic Scholar API.

        Args:
            endpoint: API endpoint (e.g., "/paper/search").
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"

        try:
            log_api_call("semantic_scholar", {"endpoint": endpoint, "params": params})
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limit - this is not fatal, just log a warning
                logger.warning(
                    "Semantic Scholar API rate limit exceeded (429). "
                    "Will continue without Semantic Scholar enrichment. "
                    "This is normal and not an error."
                )
                raise APIError(
                    "Semantic Scholar API rate limit exceeded. "
                    "Continuing without enrichment."
                ) from e
            log_error(e, f"Semantic Scholar API HTTP error: {e.response.status_code}")
            raise APIError(f"Semantic Scholar API request failed: {e}") from e
        except requests.RequestException as e:
            log_error(e, "Semantic Scholar API request failed")
            raise APIError(f"Failed to connect to Semantic Scholar API: {e}") from e
        except ValueError as e:
            log_error(e, "Invalid JSON response from Semantic Scholar")
            raise APIError("Invalid response from Semantic Scholar API") from e

    def search_paper_by_title(
        self,
        title: str,
        fields: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a paper by title and return metadata.

        Args:
            title: Publication title to search for.
            fields: List of fields to retrieve. Defaults to:
                   ["title", "authors", "abstract", "year", "citationCount", "venue", "url"]

        Returns:
            Paper metadata dict with complete author list, or None if not found.

        Example:
            >>> paper = client.search_paper_by_title("Effect of viscosity on microswimmers")
            >>> if paper:
            ...     print(f"Found {len(paper['authors'])} authors")
            ...     print(f"Abstract: {paper['abstract'][:100]}")
        """
        # Default fields to retrieve
        if fields is None:
            fields = [
                "title",
                "authors",  # Returns ALL authors (no truncation)
                "abstract",
                "year",
                "citationCount",
                "venue",
                "url",
                "externalIds"  # Contains DOI, ArXiv ID, etc.
            ]

        # Clean title for search
        title_clean = title.strip()
        if not title_clean:
            logger.warning("Empty title provided to search_paper_by_title")
            return None

        # Check cache first
        cache_key = f"paper:{title_clean.lower()}"
        if cache_key in self._cache:
            logger.debug(f"Using cached result for: {title_clean[:50]}...")
            return self._cache[cache_key]

        try:
            # Search for paper
            endpoint = "/paper/search"
            params = {
                "query": title_clean,
                "fields": ",".join(fields),
                "limit": 3  # Get top 3 results
            }

            logger.debug(f"Searching Semantic Scholar for: {title_clean[:50]}...")
            result = self._make_request(endpoint, params)

            # Get papers from response
            papers = result.get("data", [])
            if not papers:
                logger.warning(f"No results found on Semantic Scholar for: {title_clean[:50]}...")
                return None

            # Find best match by title similarity
            best_match = None
            best_score = 0.0

            for paper in papers:
                paper_title = (paper.get("title") or "").strip().lower()
                search_title = title_clean.lower()

                # Simple similarity: check if titles match closely
                # (exact match or one contains the other)
                if paper_title == search_title:
                    score = 1.0
                elif paper_title in search_title or search_title in paper_title:
                    # Partial match - calculate overlap
                    overlap = len(set(paper_title.split()) & set(search_title.split()))
                    total = len(set(paper_title.split()) | set(search_title.split()))
                    score = overlap / total if total > 0 else 0.0
                else:
                    score = 0.0

                if score > best_score:
                    best_score = score
                    best_match = paper

            # Require at least 70% similarity
            if best_match and best_score >= 0.7:
                logger.info(
                    f"Found match on Semantic Scholar (score={best_score:.2f}): "
                    f"{best_match.get('title', '')[:50]}..."
                )
                # Cache the result
                self._cache[cache_key] = best_match
                return best_match
            else:
                logger.warning(
                    f"No good match found on Semantic Scholar for: {title_clean[:50]}... "
                    f"(best score={best_score:.2f})"
                )
                # Cache negative result to avoid re-querying
                self._cache[cache_key] = None
                return None

        except APIError:
            raise
        except Exception as e:
            logger.warning(f"Error searching Semantic Scholar for '{title_clean[:50]}...': {e}")
            return None

    def get_paper_authors(self, title: str) -> Optional[List[str]]:
        """
        Get complete author list for a paper by title.

        This is a convenience method that extracts just the author names.

        Args:
            title: Publication title to search for.

        Returns:
            List of author names (complete, no truncation), or None if not found or rate limited.

        Example:
            >>> authors = client.get_paper_authors("Microfluidics for microswimmers")
            >>> if authors:
            ...     print(f"Found {len(authors)} authors: {', '.join(authors[:3])}, ...")
        """
        try:
            paper = self.search_paper_by_title(title)
            if not paper:
                return None

            authors_data = paper.get("authors", [])
            if not authors_data:
                return None

            # Extract author names
            authors = [
                author.get("name", "").strip()
                for author in authors_data
                if author.get("name")
            ]

            return authors if authors else None
        except APIError:
            # Rate limit or other API error - gracefully return None
            return None

    def get_paper_abstract(self, title: str) -> Optional[str]:
        """
        Get abstract for a paper by title.

        This is a convenience method that extracts just the abstract.

        Args:
            title: Publication title to search for.

        Returns:
            Abstract text, or None if not found or rate limited.

        Example:
            >>> abstract = client.get_paper_abstract("Effect of viscosity on microswimmers")
            >>> if abstract:
            ...     print(f"Abstract length: {len(abstract)} chars")
        """
        try:
            paper = self.search_paper_by_title(title)
            if not paper:
                return None

            return paper.get("abstract")
        except APIError:
            # Rate limit or other API error - gracefully return None
            return None
