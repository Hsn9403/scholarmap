"""
OpenAlex API client for retrieving author affiliations and publications.

API Docs: https://docs.openalex.org/
Rate limit: 100,000 requests/day (polite pool), 10 requests/second with email in User-Agent
"""
import re
import time
from typing import List, Dict, Any, Optional
import requests

from src.logger import logger
from src.exceptions import APIError

from .cache import SimpleCache


def _sanitize_search_value(value: str) -> str:
    """
    Make a string safe to use as a value in an OpenAlex `.search` filter.

    In the OpenAlex filter grammar, `,` separates filters and `:` separates
    key from value, so any punctuation in the value can produce a malformed
    filter and a 400 Bad Request. `.search` matching is tokenized full-text,
    so punctuation is ignored anyway — stripping it does not hurt recall.
    Accented letters are preserved (\\w is unicode-aware).
    """
    cleaned = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


class OpenAlexClient:
    """
    Client for OpenAlex API.

    OpenAlex is a free, open catalog of scholarly papers, authors, institutions,
    and more. Perfect for finding researcher affiliations.
    """

    BASE_URL = "https://api.openalex.org"

    def __init__(self, email: str = "research@sci-diligence.com", use_cache: bool = True):
        """
        Initialize OpenAlex client.

        Args:
            email: Email for polite pool (faster rate limits).
            use_cache: Whether to use caching.
        """
        self.email = email
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"Scholarmap/1.0 (mailto:{email})",
            "Accept": "application/json"
        })

        self.cache = SimpleCache(cache_dir=".cache/openalex") if use_cache else None
        self._last_request_time = 0
        self._min_interval = 0.1  # 10 requests/second max

        logger.debug(f"OpenAlexClient initialized (email: {email})")

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
            endpoint: API endpoint (e.g., "/authors/A1234567890").
            params: Query parameters.

        Returns:
            JSON response dict.
        """
        url = f"{self.BASE_URL}{endpoint}"
        params = params or {}

        # Check cache
        if self.cache:
            cached = self.cache.get("openalex", {"endpoint": endpoint, "params": params})
            if cached:
                return cached

        # Rate limit
        self._rate_limit()

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Cache response
            if self.cache:
                self.cache.set("openalex", {"endpoint": endpoint, "params": params}, data)

            return data

        except requests.Timeout as e:
            # OpenAlex timeout - service likely down or overloaded
            logger.warning(f"OpenAlex timeout (>10s): {endpoint}")
            raise APIError(f"OpenAlex is currently unavailable (timeout after 10s)") from e
        except requests.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning("OpenAlex rate limit hit, waiting 60s...")
                time.sleep(60)
                return self._make_request(endpoint, params)  # Retry
            raise APIError(f"OpenAlex API error: {e}") from e
        except requests.RequestException as e:
            raise APIError(f"OpenAlex request failed: {e}") from e

    def search_author(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Search for author by name.

        Args:
            name: Author name to search.

        Returns:
            Author data dict or None if not found.
        """
        logger.info(f"Searching OpenAlex for author: {name}")

        params = {
            "filter": f"display_name.search:{_sanitize_search_value(name)}",
            "per-page": 1
        }

        try:
            data = self._make_request("/authors", params)
            results = data.get("results", [])

            if not results:
                logger.info(f"No author found in OpenAlex: {name}")
                return None

            author = results[0]
            logger.info(f"Found author: {author['display_name']} (ID: {author['id']})")
            return author

        except APIError as e:
            # If it's a maintenance/timeout issue, propagate it so the user gets the right message
            if "unavailable" in str(e).lower() or "timeout" in str(e).lower():
                logger.error(f"OpenAlex service unavailable: {e}")
                raise
            # Otherwise it's a transient error - return None (not found)
            logger.warning(f"OpenAlex search failed (transient): {e}")
            return None

    def get_author(self, author_id: str) -> Optional[Dict[str, Any]]:
        """
        Get author by OpenAlex ID.

        Args:
            author_id: OpenAlex author ID (e.g., "A1234567890" or full URL).

        Returns:
            Author data dict or None.
        """
        # Extract ID if full URL provided
        if "openalex.org" in author_id:
            author_id = author_id.split("/")[-1]

        try:
            return self._make_request(f"/authors/{author_id}")
        except APIError as e:
            logger.error(f"Error fetching author {author_id}: {e}")
            return None

    def get_author_works(
        self,
        author_id: str,
        max_results: int = 50,
        years: Optional[tuple[int, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get publications (works) for an author.

        Uses cursor-based pagination to retrieve up to max_results works.
        Works are sorted by citation count descending so the most cited are
        always included even when max_results is smaller than works_count.

        Args:
            author_id: OpenAlex author ID (short "A123…" or full URL).
            max_results: Maximum number of works to return.
            years: Optional year range (from_year, to_year).

        Returns:
            List of work dicts (at most max_results).
        """
        if "openalex.org" in author_id:
            author_id = author_id.split("/")[-1]

        page_size = min(max_results, 200)  # OpenAlex hard cap: 200 per page

        filter_str = f"authorships.author.id:{author_id}"
        if years:
            filter_str += f",publication_year:{years[0]}-{years[1]}"

        params: Dict[str, Any] = {
            "filter": filter_str,
            "per-page": page_size,
            "sort": "cited_by_count:desc",
            "cursor": "*",  # Start cursor for first page
            "select": "id,title,publication_year,cited_by_count,authorships,primary_location",
        }

        all_works: List[Dict[str, Any]] = []

        try:
            while len(all_works) < max_results:
                data = self._make_request("/works", params)
                page = data.get("results", [])

                if not page:
                    break

                all_works.extend(page)

                # Stop if we've collected enough or there are no more pages
                meta = data.get("meta", {})
                next_cursor = meta.get("next_cursor")
                if not next_cursor or len(page) < page_size:
                    break

                params["cursor"] = next_cursor

            all_works = all_works[:max_results]
            logger.info(f"Found {len(all_works)} works for author {author_id}")
            return all_works

        except APIError as e:
            logger.error(f"Error fetching works: {e}")
            return []

    def extract_affiliations_from_works(
        self,
        works: List[Dict[str, Any]],
        author_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract all unique institutions from author's works.

        Args:
            works: List of work dicts from get_author_works().
            author_id: Optional author ID to filter authorships.

        Returns:
            List of institution dicts with metadata:
            [{
                "id": "I123456",
                "display_name": "MIT",
                "ror": "https://ror.org/...",
                "country_code": "US",
                "type": "education",
                "works_count": 5,
                "years": [2020, 2021, 2022]
            }]
        """
        institutions_map: Dict[str, Dict[str, Any]] = {}

        for work in works:
            year = work.get("publication_year")
            authorships = work.get("authorships", [])

            for authorship in authorships:
                # If author_id provided, filter to that author only
                if author_id:
                    auth_id = authorship.get("author", {}).get("id") or ""
                    if author_id not in auth_id:
                        continue

                # Extract institutions
                for inst in authorship.get("institutions", []):
                    inst_id = inst.get("id")
                    if not inst_id:
                        continue

                    if inst_id not in institutions_map:
                        institutions_map[inst_id] = {
                            "id": inst_id,
                            "display_name": inst.get("display_name"),
                            "ror": inst.get("ror"),
                            "country_code": inst.get("country_code"),
                            "type": inst.get("type"),
                            "works_count": 0,
                            "years": []
                        }

                    institutions_map[inst_id]["works_count"] += 1
                    if year and year not in institutions_map[inst_id]["years"]:
                        institutions_map[inst_id]["years"].append(year)

        # Sort by works_count
        institutions = sorted(
            institutions_map.values(),
            key=lambda x: x["works_count"],
            reverse=True
        )

        logger.info(f"Extracted {len(institutions)} unique institutions")
        return institutions

    def search_work_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Search for a work (publication) by title.

        Args:
            title: Publication title to search.

        Returns:
            Work dict with authorships or None if not found.
        """
        clean_title = _sanitize_search_value(title)
        if not clean_title:
            logger.debug(f"Title empty after sanitizing: {title[:60]}")
            return None

        params = {
            "filter": f"title.search:{clean_title}",
            "per-page": 1,
            "select": "id,title,authorships,publication_year"
        }

        try:
            data = self._make_request("/works", params)
            results = data.get("results", [])

            if not results:
                logger.debug(f"No work found in OpenAlex for title: {title[:60]}")
                return None

            work = results[0]
            logger.debug(f"Found work: {work.get('title', '')[:60]}")
            return work

        except APIError as e:
            logger.error(f"Error searching work by title: {e}")
            return None

    def get_author_affiliations(
        self,
        author_name: Optional[str] = None,
        author_id: Optional[str] = None,
        max_works: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all affiliations for an author (convenience method).

        Args:
            author_name: Author name to search.
            author_id: OpenAlex author ID (if known).
            max_works: Maximum works to analyze.

        Returns:
            List of institution dicts with metadata.
        """
        # Get author
        if author_id:
            author = self.get_author(author_id)
        elif author_name:
            author = self.search_author(author_name)
        else:
            raise ValueError("Must provide author_name or author_id")

        if not author:
            return []

        author_id = author["id"]

        # Get works
        works = self.get_author_works(author_id, max_results=max_works)

        if not works:
            return []

        # Extract affiliations
        return self.extract_affiliations_from_works(works, author_id)

    def get_author_institutions_by_count(self, openalex_id: str) -> List[Dict[str, Any]]:
        """
        Get institutions where an author has published, grouped by publication count.

        Uses OpenAlex's server-side group_by aggregation endpoint for efficiency.
        Returns institutions sorted by publication count (descending).

        Args:
            openalex_id: OpenAlex author ID (e.g., "A1234567890" or full URL).

        Returns:
            List of dicts with keys: key (institution ID), key_display_name, count.
            Already sorted by count descending.

        Example:
            >>> client.get_author_institutions_by_count("A5059888")
            [
                {"key": "I95457840", "key_display_name": "Stanford University", "count": 784},
                {"key": "I12345678", "key_display_name": "MIT", "count": 427},
                ...
            ]
        """
        # Normalize ID (strip URL if provided)
        author_id = openalex_id.split("/")[-1] if "/" in openalex_id else openalex_id

        logger.debug(f"Fetching institutions for author {author_id} via group_by")

        try:
            params = {
                "filter": f"author.id:{author_id}",
                "group_by": "authorships.institutions.id"
            }

            data = self._make_request("/works", params)
            grouped = data.get("group_by", [])

            logger.info(f"Found {len(grouped)} institutions for author {author_id}")
            return grouped

        except APIError as e:
            logger.warning(f"Failed to fetch institutions for {author_id}: {e}")
            return []
