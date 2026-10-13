"""
ROR (Research Organization Registry) API client.

ROR provides authoritative data about research organizations including
their type (company, education, healthcare, nonprofit, government, etc.).

API Docs: https://ror.readme.io/docs/rest-api
Rate limit: Reasonable use, no hard limit
"""
import time
from typing import Optional, Dict, Any, List
import requests

from src.logger import logger
from src.exceptions import APIError

from .cache import SimpleCache


class RORClient:
    """
    Client for ROR API.

    ROR is used to:
    1. Normalize organization names
    2. Determine organization type (company vs academic vs government)
    3. Get additional metadata (country, aliases, etc.)
    """

    BASE_URL = "https://api.ror.org"

    # Organization types that indicate CORPORATE entities
    CORPORATE_TYPES = {
        "Company",
        "Company (Private)",
        "Company (Public)"
    }

    # Organization types that indicate NON-CORPORATE entities
    NON_CORPORATE_TYPES = {
        "Education",
        "Healthcare",
        "Nonprofit",
        "Government",
        "Facility",
        "Archive",
        "Other"
    }

    def __init__(self, use_cache: bool = True):
        """
        Initialize ROR client.

        Args:
            use_cache: Whether to use caching.
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Scholarmap/1.0",
            "Accept": "application/json"
        })

        self.cache = SimpleCache(cache_dir=".cache/ror") if use_cache else None
        self._last_request_time = 0
        self._min_interval = 0.5  # Be polite

        logger.debug("RORClient initialized")

    def _extract_display_name(self, org: Dict[str, Any]) -> str:
        """
        Extract display name from ROR organization data.

        ROR API v2 uses "names" array instead of "name" string.

        Args:
            org: ROR organization dict.

        Returns:
            Display name string.
        """
        names = org.get("names", [])

        if not names:
            return org.get("name", "Unknown")  # Fallback to old format

        # Find name with type "ror_display" or "label"
        for name_obj in names:
            if "ror_display" in name_obj.get("types", []):
                return name_obj.get("value", "Unknown")

        # Fallback to first name
        return names[0].get("value", "Unknown")

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make API request with rate limiting and caching.

        Args:
            endpoint: API endpoint.
            params: Query parameters.

        Returns:
            JSON response dict.
        """
        url = f"{self.BASE_URL}{endpoint}"
        params = params or {}

        # Check cache
        if self.cache:
            cached = self.cache.get("ror", {"endpoint": endpoint, "params": params})
            if cached:
                return cached

        # Rate limit
        self._rate_limit()

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Cache response
            if self.cache:
                self.cache.set("ror", {"endpoint": endpoint, "params": params}, data)

            return data

        except requests.HTTPError as e:
            raise APIError(f"ROR API error: {e}") from e
        except requests.RequestException as e:
            raise APIError(f"ROR request failed: {e}") from e

    def search_organization(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search for organization by name.

        Args:
            query: Organization name to search.

        Returns:
            Best matching organization dict or None.
        """
        logger.info(f"Searching ROR for: {query}")

        params = {"query": query}

        try:
            data = self._make_request("/organizations", params)
            items = data.get("items", [])

            if not items:
                logger.info(f"No ROR match found for: {query}")
                return None

            # Return best match (first result) IF it's relevant
            org = items[0]
            org_name = self._extract_display_name(org)

            # Validate that the result is relevant (simple string similarity check)
            if not self._is_relevant_match(query, org_name):
                logger.warning(f"ROR match '{org_name}' is not relevant for '{query}'")
                return None

            logger.info(f"Found ROR: {org_name} (ID: {org['id']})")
            return org

        except APIError as e:
            logger.error(f"Error searching ROR: {e}")
            return None

    def _is_relevant_match(self, query: str, result_name: str) -> bool:
        """
        Check if ROR result is relevant to the query.

        Args:
            query: Original query string.
            result_name: Name from ROR result.

        Returns:
            True if relevant, False otherwise.
        """
        query_lower = query.lower()
        result_lower = result_name.lower()

        # Extract key words from query (remove common suffixes)
        query_clean = query_lower
        for suffix in [" inc", " ltd", " llc", " ag", " sa", " gmbh", " corp"]:
            query_clean = query_clean.replace(suffix, "")

        # Check if main terms are present in result
        # Split into words and check if at least 50% of significant words match
        query_words = [w for w in query_clean.split() if len(w) > 2]  # Skip short words
        if not query_words:
            return True  # Fallback: accept if no significant words

        matches = sum(1 for word in query_words if word in result_lower)
        match_ratio = matches / len(query_words)

        return match_ratio >= 0.5  # At least 50% of words match

    def get_organization(self, ror_id: str) -> Optional[Dict[str, Any]]:
        """
        Get organization by ROR ID.

        Args:
            ror_id: ROR ID (e.g., "https://ror.org/abc123" or "abc123").

        Returns:
            Organization dict or None.
        """
        # Extract ID if full URL provided
        if "ror.org/" in ror_id:
            ror_id = ror_id.split("ror.org/")[-1]

        try:
            return self._make_request(f"/organizations/{ror_id}")
        except APIError as e:
            logger.error(f"Error fetching ROR {ror_id}: {e}")
            return None

    def is_corporate(self, org_data: Dict[str, Any]) -> bool:
        """
        Determine if organization is a corporate entity.

        Args:
            org_data: ROR organization dict.

        Returns:
            True if corporate, False otherwise.
        """
        org_types = org_data.get("types", [])

        # Check for corporate types
        for org_type in org_types:
            if org_type in self.CORPORATE_TYPES:
                return True

        return False

    def classify_organization(
        self,
        name: str,
        ror_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify an organization as corporate or not.

        Args:
            name: Organization name.
            ror_id: Optional ROR ID if known.

        Returns:
            Classification dict:
            {
                "name": str,
                "ror_id": str | None,
                "is_corporate": bool,
                "confidence": float,  # 0-1
                "types": List[str],
                "country": str | None,
                "source": str  # "ror" or "heuristic"
            }
        """
        # Try ROR first
        if ror_id:
            org = self.get_organization(ror_id)
        else:
            org = self.search_organization(name)

        if org:
            is_corp = self.is_corporate(org)
            org_name = self._extract_display_name(org)

            # Extract country (ROR v2 uses "locations" array)
            country_code = None
            locations = org.get("locations", [])
            if locations and locations[0].get("geonames_details"):
                country_code = locations[0]["geonames_details"].get("country_code")

            return {
                "name": org_name,
                "normalized_name": org_name,
                "ror_id": org.get("id"),
                "is_corporate": is_corp,
                "confidence": 0.95,  # High confidence with ROR
                "types": org.get("types", []),
                "country": country_code,
                "source": "ror"
            }

        # Fallback to heuristic
        logger.warning(f"ROR not found for '{name}', using heuristic")
        return self._classify_by_heuristic(name)

    def _classify_by_heuristic(self, name: str) -> Dict[str, Any]:
        """
        Classify organization using name-based heuristics.

        This is a fallback when ROR doesn't have the organization.

        Args:
            name: Organization name.

        Returns:
            Classification dict (same structure as classify_organization).
        """
        name_lower = name.lower()

        # Keywords indicating NON-CORPORATE
        non_corporate_keywords = [
            "university", "université", "universität", "universidad", "universita",
            "college", "institute", "institut", "hospital", "clinic",
            "medical center", "school", "academy", "laboratoire",
            "research center", "centre", "foundation", "ministry",
            "national", "government", "public health", "department"
        ]

        for keyword in non_corporate_keywords:
            if keyword in name_lower:
                return {
                    "name": name,
                    "normalized_name": name,
                    "ror_id": None,
                    "is_corporate": False,
                    "confidence": 0.7,  # Medium confidence
                    "types": ["heuristic:academic"],
                    "country": None,
                    "source": "heuristic"
                }

        # Keywords indicating CORPORATE
        corporate_keywords = [
            "inc", "incorporated", "corp", "corporation",
            "ltd", "limited", "llc", "gmbh", "ag", "sa", "sas",
            "plc", "group", "company", "industries",
            "technologies", "systems", "solutions"
        ]

        for keyword in corporate_keywords:
            # Match whole words for corporate keywords
            if f" {keyword}" in name_lower or name_lower.endswith(keyword):
                return {
                    "name": name,
                    "normalized_name": name,
                    "ror_id": None,
                    "is_corporate": True,
                    "confidence": 0.8,  # Good confidence
                    "types": ["heuristic:corporate"],
                    "country": None,
                    "source": "heuristic"
                }

        # Ambiguous - mark as non-corporate with low confidence
        logger.warning(f"Ambiguous organization: {name}")
        return {
            "name": name,
            "normalized_name": name,
            "ror_id": None,
            "is_corporate": False,
            "confidence": 0.3,  # Low confidence - AMBIGUOUS
            "types": ["heuristic:unknown"],
            "country": None,
            "source": "heuristic"
        }

    def bulk_classify(
        self,
        organizations: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Classify multiple organizations.

        Args:
            organizations: List of dicts with "name" and optional "ror" keys.

        Returns:
            List of classification dicts.
        """
        results = []

        for org in organizations:
            name = org.get("name")
            ror_id = org.get("ror")

            if not name:
                continue

            classification = self.classify_organization(name, ror_id)
            results.append(classification)

        logger.info(
            f"Classified {len(results)} organizations "
            f"({sum(1 for r in results if r['is_corporate'])} corporate)"
        )

        return results
