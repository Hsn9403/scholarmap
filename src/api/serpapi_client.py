#!/usr/bin/env python3
"""
SerpAPI client for Google Scholar and Google Patents searches.

This module provides a unified interface to interact with SerpAPI,
handling API key management, request execution, error handling,
and cassette recording/playback for offline mode.

Cassette Modes:
    - "record" (default): Make real API calls AND save responses to cache
    - "offline": Only use cached responses (no API calls)
    - "disabled": No caching, always make real API calls

Set mode via environment variable CASSETTE_MODE or constructor parameter.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from serpapi import GoogleSearch

from src.logger import logger, log_api_call, log_error
from src.exceptions import ConfigurationError, APIError
from .cassette import CassetteManager, get_cassette_mode


class SerpAPIClient:
    """
    Client for interacting with SerpAPI (Google Scholar, Google Patents).

    This class centralizes all SerpAPI calls, providing:
    - API key management (from constructor or environment variable)
    - Logging of all API calls for debugging
    - Consistent error handling
    - Cassette recording/playback for offline mode

    Attributes:
        api_key (str): The SerpAPI API key used for authentication.
        cassette (CassetteManager): Manager for recording/playing API responses.

    Example:
        >>> # Online mode (default): makes real calls + saves to cache
        >>> client = SerpAPIClient()
        >>> results = client.search({"engine": "google_scholar", "q": "ML"})

        >>> # Offline mode: uses cached responses only
        >>> client = SerpAPIClient(cassette_mode="offline")
        >>> results = client.search({"engine": "google_scholar", "q": "ML"})
    """

    # Requêtes réellement envoyées (hors cache) : c'est ce que décompte le quota SerpAPI
    real_calls = 0

    # Environment variable names to check for API key (in order of priority)
    _ENV_KEYS = ("SERPAPI_KEY", "SERPAPI_API_KEY", "SERPAPI")

    def __init__(
        self,
        api_key: Optional[str] = None,
        cassette_mode: Optional[str] = None
    ):
        """
        Initialize the SerpAPI client.

        Args:
            api_key: SerpAPI API key. If not provided, will be read from
                     environment variables (SERPAPI_KEY, SERPAPI_API_KEY, or SERPAPI).
                     Not required in offline mode.
            cassette_mode: Cassette mode ("record", "offline", "disabled").
                          If not provided, reads from CASSETTE_MODE env var.
                          Default: "record"

        Raises:
            ConfigurationError: If no API key is found and not in offline mode.
        """
        # Initialize cassette first (might be offline mode)
        mode = cassette_mode or get_cassette_mode()
        self.cassette = CassetteManager(mode=mode)

        # Get API key (not required in offline mode)
        if mode == CassetteManager.MODE_OFFLINE:
            # In offline mode, API key is optional
            self.api_key = api_key or self._get_key_from_env_optional()
        else:
            # In other modes, API key is required
            self.api_key = api_key or self._get_key_from_env()

        logger.debug(f"SerpAPIClient initialized (cassette_mode={mode})")

    def _get_key_from_env(self) -> str:
        """
        Retrieve API key from environment variables.

        Returns:
            The API key found in environment variables.

        Raises:
            ConfigurationError: If no API key is found in any expected env var.
        """
        for env_name in self._ENV_KEYS:
            key = os.getenv(env_name)
            if key:
                logger.debug(f"API key loaded from {env_name}")
                return key

        raise ConfigurationError(
            "SERPAPI_KEY manquant.\n"
            "➡️ Fais (Mac/Linux): export SERPAPI_KEY='ta_cle'\n"
            "Puis relance le script."
        )

    def _get_key_from_env_optional(self) -> Optional[str]:
        """Get API key from env, returning None if not found (for offline mode)."""
        for env_name in self._ENV_KEYS:
            key = os.getenv(env_name)
            if key:
                return key
        return None

    def search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a SerpAPI search and return results as a dictionary.

        In record mode: makes real API call and saves response to cache.
        In offline mode: returns cached response (raises APIError if not found).
        In disabled mode: makes real API call without caching.

        Args:
            params: Search parameters dict. Must include 'engine' key.
                    The 'api_key' will be added automatically.

        Returns:
            Dictionary containing the search results.

        Raises:
            APIError: If the API call fails or no cache found in offline mode.

        Example:
            >>> results = client.search({
            ...     "engine": "google_scholar",
            ...     "q": "machine learning",
            ...     "num": 10
            ... })
        """
        engine = params.get("engine", "unknown")

        # Step 1: Check cache first
        cached = self.cassette.get(params)
        if cached is not None:
            logger.info(f"[CASSETTE] Using cached response for {engine}")
            return cached

        # Step 2: In offline mode without cache, raise error
        if self.cassette.mode == CassetteManager.MODE_OFFLINE:
            raise APIError(
                f"No cassette found for {engine} request in offline mode. "
                f"Run in 'record' mode first to cache this request."
            )

        # Step 3: Make real API call
        params_with_key = {**params, "api_key": self.api_key}

        try:
            log_api_call(engine, {"q": params.get("q", params.get("patent_id", ""))})
            search = GoogleSearch(params_with_key)
            search.timeout = 20  # override lib default (60000s = no timeout)
            result = search.get_dict()
            SerpAPIClient.real_calls += 1

            if result.get("error"):
                raise APIError(f"SerpAPI error: {result['error']}")

            # Step 4: Save to cache (if in record mode)
            self.cassette.save(params, result)

            return result

        except APIError:
            raise
        except Exception as e:
            log_error(e, "SerpAPI search failed")
            raise APIError(f"Failed to execute SerpAPI search: {e}") from e

    def search_html(self, params: Dict[str, Any]) -> str:
        """
        Execute a SerpAPI search and return raw HTML results.

        Note: HTML responses are cached with a "_html" suffix in the key.

        Args:
            params: Search parameters dict. Must include 'engine' key.
                    The 'api_key' will be added automatically.

        Returns:
            Raw HTML string from the search results.

        Raises:
            APIError: If the API call fails.

        Example:
            >>> html = client.search_html({
            ...     "engine": "google_patents",
            ...     "patent_id": "patent/US1234567/en"
            ... })
        """
        # Add marker to distinguish HTML requests in cache
        params_for_cache = {**params, "_type": "html"}
        engine = params.get("engine", "unknown")

        # Check cache
        cached = self.cassette.get(params_for_cache)
        if cached is not None:
            logger.info(f"[CASSETTE] Using cached HTML response for {engine}")
            # Cached HTML is stored as {"html": "..."} dict
            return cached.get("html", "") if isinstance(cached, dict) else cached

        # Offline mode without cache
        if self.cassette.mode == CassetteManager.MODE_OFFLINE:
            raise APIError(
                f"No cassette found for {engine} HTML request in offline mode."
            )

        # Make real API call
        params_with_key = {**params, "api_key": self.api_key}

        try:
            log_api_call(engine, {"q": params.get("q", "")})
            search = GoogleSearch(params_with_key)
            html = search.get_html()
            SerpAPIClient.real_calls += 1

            # Save to cache (wrap in dict for consistency)
            self.cassette.save(params_for_cache, {"html": html})

            return html

        except Exception as e:
            log_error(e, "SerpAPI HTML search failed")
            raise APIError(f"Failed to execute SerpAPI HTML search: {e}") from e

    # -------------------------------------------------------------------------
    # Convenience methods for common search types
    # -------------------------------------------------------------------------

    def search_scholar(
        self,
        query: str,
        num: int = 10,
        hl: str = "en",
        **extra_params
    ) -> Dict[str, Any]:
        """
        Search Google Scholar for publications.

        Args:
            query: Search query string.
            num: Number of results to return (default: 10).
            hl: Language code (default: "en").
            **extra_params: Additional parameters to pass to SerpAPI.

        Returns:
            Dictionary containing search results with 'organic_results' key.

        Example:
            >>> results = client.search_scholar("deep learning transformers", num=20)
            >>> for paper in results.get("organic_results", []):
            ...     print(paper["title"])
        """
        params = {
            "engine": "google_scholar",
            "q": query,
            "num": num,
            "hl": hl,
            **extra_params
        }
        return self.search(params)

    def search_scholar_author(
        self,
        author_id: str,
        hl: str = "en",
        **extra_params
    ) -> Dict[str, Any]:
        """
        Fetch Google Scholar author profile by author ID.

        Args:
            author_id: Google Scholar author ID (e.g., "xJaxiEEAAAAJ").
            hl: Language code (default: "en").
            **extra_params: Additional parameters to pass to SerpAPI.

        Returns:
            Dictionary containing author profile data with keys:
            - 'author': dict with name, affiliations, etc.
            - 'articles': list of publications
            - 'cited_by': citation metrics

        Example:
            >>> author = client.search_scholar_author("xJaxiEEAAAAJ")
            >>> print(author["author"]["name"])
        """
        params = {
            "engine": "google_scholar_author",
            "author_id": author_id,
            "hl": hl,
            **extra_params
        }
        return self.search(params)

    def search_patents(
        self,
        query: str,
        num: int = 10,
        **extra_params
    ) -> Dict[str, Any]:
        """
        Search Google Patents.

        Args:
            query: Search query (can include inventor:, assignee:, etc.).
            num: Number of results to return (default: 10).
            **extra_params: Additional parameters to pass to SerpAPI.

        Returns:
            Dictionary containing patent search results with 'organic_results' key.

        Example:
            >>> results = client.search_patents("inventor:John Smith", num=20)
            >>> for patent in results.get("organic_results", []):
            ...     print(patent["title"])
        """
        params = {
            "engine": "google_patents",
            "q": query,
            "num": num,
            **extra_params
        }
        return self.search(params)

    def get_patent_details(
        self,
        patent_id: str,
        hl: str = "en",
        **extra_params
    ) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific patent.

        Args:
            patent_id: Patent ID in format "patent/US1234567/en" or just "US1234567".
            hl: Language code (default: "en").
            **extra_params: Additional parameters to pass to SerpAPI.

        Returns:
            Dictionary containing detailed patent information:
            - 'title': Patent title
            - 'inventors': List of inventors
            - 'assignee': Current assignee
            - 'claims': Patent claims
            - 'cited_by': Patents citing this one
            - etc.

        Example:
            >>> details = client.get_patent_details("patent/US10000000/en")
            >>> print(details.get("title"))
            >>> print(details.get("inventors"))
        """
        # Normalize patent_id format
        if not patent_id.startswith("patent/"):
            patent_id = f"patent/{patent_id}/en"

        params = {
            "engine": "google_patents_details",
            "patent_id": patent_id,
            "hl": hl,
            "no_cache": "false",
            **extra_params
        }
        return self.search(params)


# ---------------------------------------------------------------------------
# Backward compatibility: module-level functions
# These wrap the class methods for code that still uses the old API
# ---------------------------------------------------------------------------

_default_client: Optional[SerpAPIClient] = None


def _get_client() -> SerpAPIClient:
    """Get or create the default client instance."""
    global _default_client
    if _default_client is None:
        _default_client = SerpAPIClient()
    return _default_client


def get_serpapi_key() -> str:
    """
    Get SerpAPI key from environment variables.

    Returns:
        API key string.

    Raises:
        ConfigurationError: If no API key is found.

    Note:
        Deprecated: Use SerpAPIClient instead.
    """
    return _get_client().api_key


def serp_search(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SerpAPI search and return JSON results.

    Args:
        params: SerpAPI parameters (must include api_key).

    Returns:
        Dictionary with search results.

    Raises:
        APIError: If the API call fails.

    Note:
        Deprecated: Use SerpAPIClient.search() instead.
    """
    # If api_key is in params, use it directly (old behavior)
    if "api_key" in params:
        client = SerpAPIClient(api_key=params["api_key"])
        params_without_key = {k: v for k, v in params.items() if k != "api_key"}
        return client.search(params_without_key)
    return _get_client().search(params)


def serp_search_html(params: Dict[str, Any]) -> str:
    """
    Execute a SerpAPI search and return HTML results.

    Args:
        params: SerpAPI parameters (must include api_key).

    Returns:
        HTML string.

    Raises:
        APIError: If the API call fails.

    Note:
        Deprecated: Use SerpAPIClient.search_html() instead.
    """
    if "api_key" in params:
        client = SerpAPIClient(api_key=params["api_key"])
        params_without_key = {k: v for k, v in params.items() if k != "api_key"}
        return client.search_html(params_without_key)
    return _get_client().search_html(params)
