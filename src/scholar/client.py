#!/usr/bin/env python3
"""
Google Scholar client for researcher profile retrieval.

This module provides the core ScholarClient class for interacting
with Google Scholar via SerpAPI.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from src.api import SerpAPIClient, SemanticScholarClient
from src.models import ScholarCandidate, ScholarData, ScholarPublication, CoAuthor
from src.helpers import _safe_int
from src.logger import logger
from src.validation import validate_author_id, validate_researcher_name, validate_integer


class ScholarClient:
    """
    Client for interacting with Google Scholar via SerpAPI.

    This class provides methods to search for researcher profiles
    and fetch detailed author data.

    Attributes:
        api_client (SerpAPIClient): The underlying SerpAPI client.
        hl (str): Default language code for searches.

    Example:
        >>> client = ScholarClient()
        >>> candidates = client.find_candidates("John Smith")
        >>> data = client.fetch_author_data("xJaxiEEAAAAJ")
        >>> print(f"Citations: {data.citations_total}")
    """

    def __init__(
        self,
        api_client: Optional[SerpAPIClient] = None,
        api_key: Optional[str] = None,
        hl: str = "fr",
        use_semantic_scholar: bool = True
    ):
        """
        Initialize the Scholar client.

        Args:
            api_client: An existing SerpAPIClient instance.
            api_key: SerpAPI key (only used if api_client not provided).
            hl: Default language code for searches (default: "fr").
            use_semantic_scholar: Whether to use Semantic Scholar API as fallback
                                 for complete author lists (default: True, no API key needed).
        """
        if api_client:
            self.api_client = api_client
        else:
            self.api_client = SerpAPIClient(api_key=api_key)

        self.hl = hl

        # Initialize Semantic Scholar client (no API key required)
        self.s2_client = SemanticScholarClient() if use_semantic_scholar else None

        logger.debug(
            f"ScholarClient initialized (hl={hl}, semantic_scholar={'enabled' if use_semantic_scholar else 'disabled'})"
        )

    def find_candidates(
        self,
        name: str,
        num: int = 10,
        hl: Optional[str] = None
    ) -> List[ScholarCandidate]:
        """
        Find Google Scholar profile candidates by researcher name.

        Searches Google for Scholar profile pages matching the given name
        and extracts candidate author IDs.

        Args:
            name: Researcher name to search for.
            num: Maximum number of Google results to fetch (default: 10).
            hl: Language code (uses instance default if not specified).

        Returns:
            List of ScholarCandidate objects.

        Example:
            >>> candidates = client.find_candidates("Marie Curie")
            >>> for c in candidates:
            ...     print(f"{c.author_id}: {c.title}")
        """
        # Validate inputs
        name = validate_researcher_name(name)
        num = validate_integer(num, min_val=1, max_val=100, param_name="num")

        hl = hl or self.hl

        params = {
            "engine": "google",
            "q": f'"{name}" site:scholar.google.com/citations',
            "hl": hl,
            "num": num,
            "no_cache": "false",
        }

        res = self.api_client.search(params)
        organic = res.get("organic_results", []) or []

        candidates: List[ScholarCandidate] = []
        seen: set = set()

        for r in organic:
            link = (r.get("link") or "").strip()
            if "scholar.google.com/citations" not in link or "user=" not in link:
                continue

            qs = parse_qs(urlparse(link).query)
            user = (qs.get("user") or [None])[0]
            if not user or user in seen:
                continue

            seen.add(user)
            candidates.append(ScholarCandidate(
                author_id=user,
                title=(r.get("title") or "").strip(),
                link=link,
                snippet=(r.get("snippet") or "").strip(),
            ))

        # Fallback regex if organic_results is malformed
        if not candidates:
            blob = str(res)
            ids = re.findall(r"scholar\.google\.com/citations\?user=([A-Za-z0-9_-]+)", blob)
            for user in ids:
                if user not in seen:
                    seen.add(user)
                    candidates.append(ScholarCandidate(
                        author_id=user,
                        title="",
                        link=f"https://scholar.google.com/citations?user={user}",
                        snippet=""
                    ))

        logger.debug(f"Found {len(candidates)} Scholar candidates for '{name}'")
        return candidates

    def fetch_author_data(
        self,
        author_id: str,
        hl: Optional[str] = None,
        num_articles: int = 100
    ) -> ScholarData:
        """
        Fetch complete Google Scholar author data.

        Retrieves author profile information including name, affiliation,
        citation metrics, and top publications.

        Args:
            author_id: Google Scholar author ID (e.g., "xJaxiEEAAAAJ").
            hl: Language code (uses instance default if not specified).
            num_articles: Number of articles to fetch (default: 100).

        Returns:
            ScholarData object with author information.

        Example:
            >>> data = client.fetch_author_data("xJaxiEEAAAAJ")
            >>> print(f"Name: {data.name}")
            >>> print(f"H-index: {data.h_index}")
        """
        # Validate inputs
        author_id = validate_author_id(author_id)
        num_articles = validate_integer(num_articles, min_val=1, max_val=100, param_name="num_articles")

        hl = hl or self.hl

        params = {
            "engine": "google_scholar_author",
            "author_id": author_id,
            "hl": hl,
            "no_cache": "false",
            "num": min(num_articles, 100),
            "start": 0,
        }
        res = self.api_client.search(params)

        author_block = res.get("author") or {}
        name = author_block.get("name") or ""
        affiliation = author_block.get("affiliations") or ""

        citations_total = self._extract_metric(res, "citations")
        h_index = (
            self._extract_metric(res, "h_index") or
            self._extract_metric(res, "indice_h")
        )

        articles = res.get("articles") or []

        # Get total publications count
        publications_total = _safe_int(res.get("articles_total"))
        if publications_total is None:
            if len(articles) >= 100:
                publications_total = ">=100"
            else:
                publications_total = len(articles)

        # Extract all publications with authors
        top_pubs: List[ScholarPublication] = []
        seen_titles: Dict[str, ScholarPublication] = {}  # Deduplicate by title

        for a in articles:
            title = a.get("title") or ""
            if not title:
                continue

            link = a.get("link") or ""
            year = a.get("year")
            cb = a.get("cited_by")
            cited_by = (
                _safe_int(cb.get("value") or cb.get("total"))
                if isinstance(cb, dict) else _safe_int(cb)
            )
            # Parse authors string into list
            authors_str = a.get("authors") or ""
            authors_list = self._parse_authors(authors_str) if authors_str else None

            # Extract publication source (journal)
            source = a.get("publication") or ""

            pub = ScholarPublication(
                title=title,
                link=link,
                cited_by=cited_by,
                authors=authors_list,
                year=year,
                source=source
            )

            # Deduplicate: if we've seen this title, keep the one with more data
            title_normalized = title.strip().lower()
            if title_normalized in seen_titles:
                existing = seen_titles[title_normalized]
                # Score publications by data completeness
                def score_pub(p):
                    score = 0
                    if p.year and str(p.year).strip():
                        score += 10
                    if p.cited_by is not None:
                        score += 10
                    if p.authors and len(p.authors) > 0:
                        score += len(p.authors)
                    return score

                # Keep the better one
                if score_pub(pub) > score_pub(existing):
                    seen_titles[title_normalized] = pub
                    logger.debug(f"Replaced duplicate publication '{title[:50]}...' with better version")
            else:
                seen_titles[title_normalized] = pub

        # Convert to list
        top_pubs = list(seen_titles.values())

        # PRIORITY 1: Extract co-authors from Scholar profile (most reliable!)
        # These are the co-authors suggested by Google Scholar with their IDs
        coauthors_from_profile = self._extract_coauthors_from_profile(res)

        # ALWAYS aggregate co-authors from publications to get stats and complete list
        # Also get abstracts and complete author lists via HTML scraping
        coauthors_from_pubs, abstracts_map, authors_map = self._aggregate_coauthors(articles, name)

        # BEST STRATEGY: Merge both sources!
        # - Profile co-authors have: full names + Scholar IDs (for disambiguation)
        # - Publication co-authors have: shared_pubs_count + example_titles (for validation)
        if coauthors_from_profile:
            # Enrich profile co-authors with publication statistics
            coauthors = self._merge_coauthor_sources(coauthors_from_profile, coauthors_from_pubs)
            logger.info(
                f"✓ Merged {len(coauthors)} co-authors "
                f"({len(coauthors_from_profile)} from profile + {len(coauthors_from_pubs)} from pubs)"
            )
        else:
            # Fallback to publication-only aggregation
            coauthors = coauthors_from_pubs
            logger.warning(
                f"No co-authors from Scholar profile, using {len(coauthors)} "
                f"co-authors aggregated from publications (no Scholar IDs)"
            )

        # Enrich publications with abstracts and complete author lists from HTML scraping
        for pub in top_pubs:
            title_normalized = pub.title.strip().lower()
            if title_normalized in abstracts_map:
                pub.abstract = abstracts_map[title_normalized]
            if title_normalized in authors_map:
                pub.authors = authors_map[title_normalized]

        logger.debug(f"Fetched data for author {author_id}: {name} ({len(coauthors)} co-authors)")

        return ScholarData(
            author_id=author_id,
            name=name,
            affiliation=affiliation,
            citations_total=citations_total,
            h_index=h_index,
            publications_total=publications_total,
            top_publications=top_pubs,
            coauthors=coauthors,
        )

    def resolve_author_id(
        self,
        researcher_name: str,
        hl: Optional[str] = None,
        max_candidates: int = 8,
        interactive: bool = True
    ) -> Optional[str]:
        """
        Resolve a researcher name to a single Google Scholar author ID.

        Handles disambiguation when multiple profiles match.

        Args:
            researcher_name: Name of the researcher to search.
            hl: Language code (uses instance default if not specified).
            max_candidates: Maximum candidates to consider (default: 8).
            interactive: If True, prompt user for selection.

        Returns:
            The resolved author_id, None if not found, or "__QUIT__" if cancelled.

        Example:
            >>> author_id = client.resolve_author_id("John Smith")
        """
        # Import here to avoid circular imports
        from .resolver import ScholarResolver

        resolver = ScholarResolver(self)
        return resolver.resolve(
            researcher_name,
            hl=hl,
            max_candidates=max_candidates,
            interactive=interactive
        )

    def _extract_metric(self, author_json: dict, metric_key: str) -> Optional[int]:
        """
        Extract a metric from the cited_by table.

        Args:
            author_json: Raw API response dict.
            metric_key: Key to extract ("h_index", "citations", "i10_index").

        Returns:
            The metric value as int, or None if not found.
        """
        cited_by = author_json.get("cited_by") or {}
        table = cited_by.get("table") or []

        target = metric_key.lower().replace("-", "_").strip()
        aliases = {target}
        if target == "h_index":
            aliases |= {"hindex", "h-index"}
        if target == "i10_index":
            aliases |= {"i10index", "i10-index"}

        for row in table:
            if not isinstance(row, dict):
                continue

            for k, v in row.items():
                nk = str(k).lower().replace("-", "_").strip()
                if nk not in aliases:
                    continue

                if isinstance(v, dict):
                    val = v.get("all")
                else:
                    val = v

                if isinstance(val, (int, float)):
                    return int(val)
                if isinstance(val, str):
                    val2 = val.strip()
                    if val2.isdigit():
                        return int(val2)
                    try:
                        return int(float(val2))
                    except Exception:
                        return None

        return None

    def _parse_authors(self, authors_str: str | List[str]) -> List[str]:
        """
        Parse authors string into a list of author names.

        Args:
            authors_str: Comma-separated author names (e.g., "J Smith, A Doe, ...") or already a list.

        Returns:
            List of author names, cleaned and trimmed.
        """
        if not authors_str:
            return []

        # If already a list, process it directly
        if isinstance(authors_str, list):
            authors = []
            for name in authors_str:
                if not isinstance(name, str):
                    continue
                name = name.strip()
                # Remove trailing "..." which indicates more authors
                if name == "...":
                    continue
                if name.endswith("..."):
                    name = name[:-3].strip()
                if name:
                    authors.append(name)
            return authors

        # Split by comma and clean each name
        authors = []
        for name in authors_str.split(","):
            name = name.strip()
            # Remove trailing "..." which indicates more authors
            if name == "...":
                continue
            if name.endswith("..."):
                name = name[:-3].strip()
            if name:
                authors.append(name)

        return authors

    def _fetch_authors_via_serpapi(self, title: str) -> Optional[List[str]]:
        """
        Fetch complete author list for a publication using SerpAPI google_scholar.

        This is used when SerpAPI google_scholar_author returns truncated authors ("...").

        Args:
            title: Publication title to search for.

        Returns:
            List of author names, or None if not found.

        Example:
            >>> authors = client._fetch_authors_via_serpapi("Effect of viscosity on microswimmers")
            >>> print(f"Found {len(authors)} authors")
        """
        try:
            params = {
                "engine": "google_scholar",
                "q": title,
                "num": 1,
                "hl": self.hl,
            }

            logger.debug(f"Fetching authors via SerpAPI for: {title[:50]}...")
            res = self.api_client.search(params)

            organic = res.get("organic_results", [])
            if not organic:
                logger.warning(f"No results found via SerpAPI for: {title[:50]}...")
                return None

            # Take the first result (should be the exact publication)
            first_result = organic[0]

            # Get publication info which contains authors
            pub_info = first_result.get("publication_info", {})
            authors_str = pub_info.get("authors", "")

            if not authors_str:
                logger.warning(f"No authors found in SerpAPI result for: {title[:50]}...")
                return None

            # Parse authors
            authors = self._parse_authors(authors_str)
            logger.info(f"Retrieved {len(authors)} authors via SerpAPI for: {title[:50]}...")

            return authors

        except Exception as e:
            logger.warning(f"Error fetching authors via SerpAPI for '{title[:50]}...': {e}")
            return None

    def _fetch_citation_details_from_html(self, citation_url: str, profile_owner_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch citation details (authors, abstract) from a Google Scholar citation page.

        This function scrapes the HTML of a citation page to get the full
        author list and abstract when SerpAPI doesn't provide them.

        Args:
            citation_url: URL to the citation page (from article['link']).
            profile_owner_name: Name of the profile owner to detect corrupted HTML.

        Returns:
            Dict with keys: 'authors' (list), 'abstract' (str), or None if fetch/parse fails.

        Example:
            >>> url = "https://scholar.google.com/citations?view_op=view_citation&..."
            >>> details = client._fetch_citation_details_from_html(url, "Alice Nedelec")
            >>> print(f"Found {len(details['authors'])} authors")
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            logger.debug(f"Fetching citation details from: {citation_url}")

            response = requests.get(citation_url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            result = {'authors': None, 'abstract': None}

            # Find the "Authors"/"Auteurs" field
            # The HTML structure is: <div class="gsc_oci_field">Authors</div>
            #                         <div class="gsc_oci_value">Author1, Author2, ...</div>
            authors_field = soup.find('div', class_='gsc_oci_field',
                                     string=lambda t: t and ('Authors' in t or 'Auteurs' in t))

            if authors_field:
                authors_value = authors_field.find_next_sibling('div', class_='gsc_oci_value')
                if authors_value:
                    authors_text = authors_value.get_text(strip=True)
                    authors_list = [a.strip() for a in authors_text.split(',') if a.strip()]

                    # Validate: check for corrupted HTML
                    # If any "author" contains multiple full names without commas, it's corrupted
                    # E.g., "Priyanka Sharan Alice Nedelec Sasha Cai" (3 names in one)
                    owner_normalized = self._normalize_name(profile_owner_name)

                    for author in authors_list:
                        # Count how many times the profile owner appears in this "author"
                        # If the owner's name appears in what should be a single author name,
                        # the HTML is likely corrupted
                        author_normalized = self._normalize_name(author)

                        # Check if this "author" contains multiple first names (likely corrupted)
                        # Heuristic: if there are 3+ capitalized words and the owner's name is in it
                        if len(author.split()) >= 3:
                            # Check if owner's last name is in this author string
                            owner_parts = owner_normalized.split()
                            author_parts = author_normalized.split()

                            if len(owner_parts) >= 2 and owner_parts[-1] in author_parts:
                                # This might be corrupted - multiple names concatenated
                                logger.warning(f"Detected potentially corrupted HTML: '{author}' contains owner name")
                                return None

                    result['authors'] = authors_list
                    logger.debug(f"Extracted {len(authors_list)} authors from HTML")

            # Extract abstract/description
            # Look for div with id "gsc_oci_descr" which contains the abstract
            abstract_div = soup.find('div', id='gsc_oci_descr')
            if abstract_div:
                abstract_text = abstract_div.get_text(strip=True)
                if abstract_text:
                    result['abstract'] = abstract_text
                    logger.debug(f"Extracted abstract ({len(abstract_text)} chars)")

            # Return result if we got at least one piece of data
            if result['authors'] or result['abstract']:
                return result

            logger.warning(f"Could not find authors or abstract in HTML for {citation_url}")
            return None

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch citation page {citation_url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error parsing citation page {citation_url}: {e}")
            return None

    def _extract_coauthors_from_profile(self, author_response: dict) -> List[CoAuthor]:
        """
        Extract co-authors from Scholar profile (most reliable source!).

        Google Scholar provides a "co_authors" field in the profile with:
        - Full names (not abbreviated)
        - Scholar IDs (unique!)
        - Affiliations

        This is MORE RELIABLE than aggregating from publications.

        Args:
            author_response: Full SerpAPI response for google_scholar_author

        Returns:
            List of CoAuthor objects with scholar_id filled
        """
        co_authors_data = author_response.get("co_authors", [])

        if not co_authors_data:
            logger.debug("No co_authors field in Scholar profile response")
            return []

        coauthors = []
        for co_auth in co_authors_data:
            name = co_auth.get("name", "").strip()
            scholar_id = co_auth.get("author_id", "").strip()
            affiliation = co_auth.get("affiliations", "").strip()
            scholar_url = co_auth.get("link", "")

            if not name:
                continue

            coauthors.append(CoAuthor(
                name=name,  # Full name like "Michel Bergmann", not "M Bergmann"!
                shared_pubs_count=0,  # Not available in profile data
                scholar_id=scholar_id,  # UNIQUE ID!
                scholar_url=scholar_url,
                # Note: We don't have shared_pubs_count or example_titles from profile,
                # but having the scholar_id is more important for disambiguation
            ))

        logger.info(
            f"Extracted {len(coauthors)} co-authors from Scholar profile "
            f"({sum(1 for c in coauthors if c.scholar_id)} with scholar_id)"
        )

        return coauthors

    def _aggregate_coauthors(
        self,
        articles: List[Dict[str, Any]],
        profile_owner_name: str
    ) -> tuple[List[CoAuthor], Dict[str, str], Dict[str, List[str]]]:
        """
        Aggregate co-authors from all publications and collect abstracts.

        Excludes the profile owner from the co-author list.
        Counts shared publications and tracks collaboration years.
        Also scrapes abstracts and complete author lists from citation pages.

        Args:
            articles: List of article dicts from SerpAPI.
            profile_owner_name: Name of the profile owner to exclude.

        Returns:
            Tuple of (list of CoAuthor objects, dict mapping title to abstract, dict mapping title to full authors list).
        """
        # Normalize the profile owner name for matching
        owner_normalized = self._normalize_name(profile_owner_name)

        # Track co-authors: name -> {"count": int, "years": list, "titles": list}
        coauthor_stats: Dict[str, Dict] = {}

        # Track abstracts: normalized_title -> abstract
        abstracts_map: Dict[str, str] = {}

        # Track full author lists: normalized_title -> full_authors_list
        authors_map: Dict[str, List[str]] = {}

        for article in articles:
            authors_str = article.get("authors") or ""
            year = article.get("year")
            title = article.get("title") or ""
            title_normalized = title.strip().lower()

            # Check if authors are truncated (contain "..." or "…")
            is_truncated = "..." in authors_str or "…" in authors_str

            if is_truncated:
                # Try multiple strategies to get complete author list
                full_authors = None
                s2_paper = None  # Cache Semantic Scholar paper data

                # Strategy 1: Try SerpAPI google_scholar
                full_authors = self._fetch_authors_via_serpapi(title)

                # Strategy 2: If SerpAPI failed and Semantic Scholar is enabled, try it
                if not full_authors and self.s2_client:
                    try:
                        logger.info(f"Trying Semantic Scholar for complete metadata: {title[:50]}...")
                        # Fetch complete paper metadata (authors + abstract in one call)
                        s2_paper = self.s2_client.search_paper_by_title(title)
                        if s2_paper:
                            # Extract authors
                            authors_data = s2_paper.get("authors", [])
                            if authors_data:
                                full_authors = [
                                    author.get("name", "").strip()
                                    for author in authors_data
                                    if author.get("name")
                                ]
                            # Also extract abstract (same request, no extra API call)
                            abstract = s2_paper.get("abstract")
                            if abstract and title_normalized not in abstracts_map:
                                abstracts_map[title_normalized] = abstract
                                logger.debug(f"Retrieved abstract from Semantic Scholar for: {title[:50]}...")
                    except Exception as e:
                        # Semantic Scholar is optional - if it fails (rate limit, etc.), just continue
                        logger.warning(f"Semantic Scholar failed for '{title[:50]}...': {e}")
                        logger.info("Continuing without Semantic Scholar (using SerpAPI data)")

                if full_authors:
                    authors = full_authors
                    logger.info(f"Retrieved {len(full_authors)} complete authors for: {title[:50]}...")
                else:
                    # Fallback to truncated list
                    authors = self._parse_authors(authors_str)
                    logger.warning(f"Could not fetch full authors (tried SerpAPI + Semantic Scholar), using truncated list for: {title[:50]}...")
            else:
                authors = self._parse_authors(authors_str)

            # Store complete author list for this publication
            if authors:
                authors_map[title_normalized] = authors

            for author in authors:
                author_normalized = self._normalize_name(author)

                # Skip if this is the profile owner (fuzzy match)
                if self._is_same_person(author_normalized, owner_normalized):
                    continue

                # Use original name as key (first occurrence)
                # Track stats
                if author not in coauthor_stats:
                    coauthor_stats[author] = {
                        "count": 0,
                        "years": [],
                        "titles": []
                    }

                coauthor_stats[author]["count"] += 1
                if year:
                    coauthor_stats[author]["years"].append(year)
                if title and len(coauthor_stats[author]["titles"]) < 3:
                    coauthor_stats[author]["titles"].append(title)

        # Convert to CoAuthor objects
        coauthors = []
        for name, stats in coauthor_stats.items():
            years = stats["years"]
            last_year = max(years) if years else None

            coauthors.append(CoAuthor(
                name=name,
                shared_pubs_count=stats["count"],
                last_shared_year=last_year,
                example_titles=stats["titles"] if stats["titles"] else None
            ))

        # Sort by shared_pubs_count descending
        coauthors.sort(key=lambda c: c.shared_pubs_count, reverse=True)

        return coauthors, abstracts_map, authors_map

    def _normalize_name(self, name: str) -> str:
        """
        Normalize a name for comparison.

        Converts to lowercase, removes accents, and keeps only alphanumeric + spaces.
        """
        import unicodedata
        # NFD decomposition + remove combining characters (accents)
        normalized = unicodedata.normalize("NFD", name.lower())
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        # Replace hyphens and dashes with spaces BEFORE removing non-alphanumeric
        # This handles "Garcia‐Zintzun" → "Garcia Zintzun" (not "GarciaZintzun")
        normalized = re.sub(r"[-‐–—]", " ", normalized)
        # Keep only alphanumeric and spaces
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _merge_coauthor_sources(
        self,
        coauthors_from_profile: List[CoAuthor],
        coauthors_from_pubs: List[CoAuthor]
    ) -> List[CoAuthor]:
        """
        Merge co-authors from profile (with IDs) and publications (with stats).

        Strategy:
        1. For each profile co-author, find matching publication co-author by name
        2. Enrich profile co-author with publication stats (shared_pubs_count, example_titles)
        3. Add publication co-authors that don't match any profile co-author

        This gives us:
        - Full names + Scholar IDs (from profile) for disambiguation
        - Shared publications count + example titles (from publications) for validation

        Args:
            coauthors_from_profile: Co-authors from Scholar profile (with IDs, but no stats)
            coauthors_from_pubs: Co-authors from publications (with stats, but often abbreviated names)

        Returns:
            Merged list of enriched CoAuthor objects
        """
        # Build lookup dict for publication co-authors by normalized name
        pubs_lookup = {}
        for pub_coauthor in coauthors_from_pubs:
            normalized = self._normalize_name(pub_coauthor.name)
            pubs_lookup[normalized] = pub_coauthor

        # Enrich profile co-authors with publication stats
        enriched = []
        matched_pubs = set()

        for profile_coauthor in coauthors_from_profile:
            profile_normalized = self._normalize_name(profile_coauthor.name)

            # Try to find matching publication co-author
            matched_pub_coauthor = None

            # Strategy 1: Exact normalized match
            if profile_normalized in pubs_lookup:
                matched_pub_coauthor = pubs_lookup[profile_normalized]
                matched_pubs.add(profile_normalized)
            else:
                # Strategy 2: Fuzzy match (e.g., "Michel Bergmann" matches "M Bergmann")
                for pub_normalized, pub_coauthor in pubs_lookup.items():
                    if self._is_same_person(profile_normalized, pub_normalized):
                        matched_pub_coauthor = pub_coauthor
                        matched_pubs.add(pub_normalized)
                        logger.debug(
                            f"Fuzzy matched: '{profile_coauthor.name}' ≈ '{pub_coauthor.name}' "
                            f"({pub_coauthor.shared_pubs_count} pubs)"
                        )
                        break

            # Create enriched co-author
            if matched_pub_coauthor:
                # Profile name + ID + publication stats = best of both worlds!
                enriched.append(CoAuthor(
                    name=profile_coauthor.name,  # Full name from profile
                    scholar_id=profile_coauthor.scholar_id,  # ID from profile
                    scholar_url=profile_coauthor.scholar_url,
                    shared_pubs_count=matched_pub_coauthor.shared_pubs_count,  # Stats from pubs
                    last_shared_year=matched_pub_coauthor.last_shared_year,
                    example_titles=matched_pub_coauthor.example_titles
                ))
            else:
                # No match in publications - keep profile co-author as-is
                # (This can happen if Scholar suggests co-authors we haven't seen in top 100 pubs)
                logger.debug(
                    f"Profile co-author '{profile_coauthor.name}' not found in publications "
                    f"(may be from older/unpublished work)"
                )
                enriched.append(profile_coauthor)

        # Add publication co-authors that weren't matched
        # (These have stats but no Scholar ID)
        for pub_normalized, pub_coauthor in pubs_lookup.items():
            if pub_normalized not in matched_pubs:
                logger.debug(
                    f"Publication co-author '{pub_coauthor.name}' not in Scholar profile "
                    f"({pub_coauthor.shared_pubs_count} pubs, but no Scholar ID)"
                )
                enriched.append(pub_coauthor)

        # Sort by shared_pubs_count (most frequent collaborators first)
        enriched.sort(key=lambda c: c.shared_pubs_count or 0, reverse=True)

        logger.info(
            f"Merged co-authors: {len(enriched)} total "
            f"({len(coauthors_from_profile)} from profile, "
            f"{len(coauthors_from_pubs)} from publications, "
            f"{len(matched_pubs)} matched)"
        )

        return enriched

    def _is_same_person(self, name1: str, name2: str) -> bool:
        """
        Check if two normalized names likely refer to the same person.

        Handles:
        - Abbreviated first names (e.g., "a nedelec" matches "alice nedelec")
        - Compound last names (e.g., "a nedelec mercier" matches "alice nedelec")
        - Initial variations (e.g., "ai garcia zintzun" matches "aidee garcia zintzun")

        Args:
            name1: First normalized name.
            name2: Second normalized name.

        Returns:
            True if names likely match, False otherwise.
        """
        if name1 == name2:
            return True

        parts1 = name1.split()
        parts2 = name2.split()

        if not parts1 or not parts2:
            return False

        # Check if last names match (exact or compound)
        # "nedelec" matches "nedelec" and "nedelec mercier" matches "nedelec"
        last1 = parts1[-1]
        last2 = parts2[-1]

        # Exact match on last name
        if last1 == last2:
            # Now check first names
            if len(parts1) > 1 and len(parts2) > 1:
                first1 = parts1[0]
                first2 = parts2[0]

                # One is initial, other is full name
                if len(first1) == 1 and first2.startswith(first1):
                    return True
                if len(first2) == 1 and first1.startswith(first2):
                    return True
                if first1 == first2:
                    return True

        # Check for compound last names
        # "a nedelec mercier" should match "alice nedelec"
        # "ai garcia zintzun" should match "aidee garcia zintzun"
        if len(parts1) >= 2 and len(parts2) >= 2:
            # Check if one name is a subset of the other
            # E.g., "alice nedelec" vs "a nedelec mercier"
            #   parts1 = ["alice", "nedelec"]
            #   parts2 = ["a", "nedelec", "mercier"]

            # Get first names
            first1 = parts1[0]
            first2 = parts2[0]

            # Check if first names match (or are initials)
            first_match = (
                first1 == first2 or
                (len(first1) == 1 and first2.startswith(first1)) or
                (len(first2) == 1 and first1.startswith(first2))
            )

            if first_match:
                # Check if any last name part matches
                # Get all name parts except first (potential last names)
                last_parts1 = set(parts1[1:])
                last_parts2 = set(parts2[1:])

                # If they share at least one last name component, it's likely the same person
                if last_parts1 & last_parts2:  # Intersection
                    return True

        # Check for compound initials matching full name
        # E.g., "AN Mercier" where "AN" = "A"udrey "N"samela
        # or "MV Salvetti" = "M"aria "V"ittoria Salvetti
        if len(parts1) == 2 and len(parts2) >= 2:
            # Check if parts1[0] is double initials
            if len(parts1[0]) >= 2 and parts1[0].isalpha():
                # E.g., "mv" from "MV Salvetti"
                initials = parts1[0]  # "mv"

                # Check if initials match first name(s)
                # For "maria vittoria salvetti" vs "mv salvetti"
                if len(parts2) >= 2:
                    # Check if first N-1 parts match the N initials
                    # E.g., "maria vittoria" should match "mv"
                    if len(parts2) - 1 >= len(initials):  # -1 for last name
                        # Get first names only (exclude last name)
                        first_names = parts2[:-1]

                        # Check if initials match first letters of first names
                        if len(first_names) == len(initials):
                            if all(
                                fname.startswith(init)
                                for fname, init in zip(first_names, initials)
                            ):
                                # Also check last name matches
                                if parts1[-1] == parts2[-1]:
                                    return True

        # Same check but reversed
        if len(parts2) == 2 and len(parts1) >= 2:
            if len(parts2[0]) >= 2 and parts2[0].isalpha():
                initials = parts2[0]

                if len(parts1) >= 2:
                    if len(parts1) - 1 >= len(initials):
                        first_names = parts1[:-1]

                        if len(first_names) == len(initials):
                            if all(
                                fname.startswith(init)
                                for fname, init in zip(first_names, initials)
                            ):
                                if parts2[-1] == parts1[-1]:
                                    return True

        return False
