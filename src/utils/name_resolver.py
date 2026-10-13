#!/usr/bin/env python3
"""
Name resolver for clinical trials searches.

Resolves abbreviated names (initials) to full names using multiple sources:
1. Google Scholar (if scholar_id available)
2. OpenAlex (free, no API key)
3. Semantic Scholar (free, no API key)
"""
from typing import Optional, List, Tuple
import re

from src.logger import logger


class NameResolver:
    """
    Resolves abbreviated names to full names using multiple sources.

    Strategy:
    1. If scholar_id provided → fetch from Google Scholar
    2. Otherwise → try OpenAlex (best for academic names)
    3. Fallback → try Semantic Scholar
    4. Last resort → return abbreviated name

    Example:
        >>> resolver = NameResolver()
        >>> full_name = resolver.resolve("M Berger", scholar_id="2yiMTDMAAAAJ")
        >>> print(full_name)  # "Michel Bergmann"
    """

    def __init__(self, use_db_only: bool = False, skip_scholar_search: bool = False):
        """
        Initialize the name resolver.

        Args:
            use_db_only: If True, only use database lookups (no API calls)
            skip_scholar_search: If True, skip the Google Scholar search strategy
                (which fetches full profiles for each candidate — very expensive).
                OpenAlex and Semantic Scholar (both free) are still used.
        """
        self._cache = {}  # Cache resolved names
        self._openalex_client = None
        self._scholar_client = None
        self._s2_client = None
        self._use_db_only = use_db_only
        self._skip_scholar_search = skip_scholar_search

    def _init_openalex(self):
        """Lazy init OpenAlex client."""
        if not self._openalex_client:
            from src.pathfinding.openalex_client import OpenAlexClient
            self._openalex_client = OpenAlexClient()

    def _init_scholar(self):
        """Lazy init Scholar client."""
        if not self._scholar_client:
            from src.scholar.client import ScholarClient
            self._scholar_client = ScholarClient()

    def _init_semantic_scholar(self):
        """Lazy init Semantic Scholar client."""
        if not self._s2_client:
            from src.api.semantic_scholar_client import SemanticScholarClient
            self._s2_client = SemanticScholarClient()

    def is_abbreviated(self, name: str) -> bool:
        """
        Check if name looks abbreviated (initials only).

        Examples:
            "M Berger" → True
            "CH Bruneau" → True
            "Michel Bergmann" → False
            "Maria Vittoria Salvetti" → False

        Args:
            name: Name to check.

        Returns:
            True if name appears to be abbreviated.
        """
        # Pattern: 1-3 capital letters, optional space/dot, then surname
        # E.g., "M Berger", "CH Bruneau", "A. Smith"
        pattern = r'^[A-Z]{1,3}[\s\.\-]*\s+[A-Z][a-z]+'
        return bool(re.match(pattern, name.strip()))

    def resolve_via_scholar(
        self,
        abbreviated_name: str,
        scholar_id: str
    ) -> Optional[str]:
        """
        Resolve name using Google Scholar ID.

        Args:
            abbreviated_name: Abbreviated name.
            scholar_id: Google Scholar ID.

        Returns:
            Full name or None if resolution fails.
        """
        try:
            self._init_scholar()
            logger.debug(f"Trying Google Scholar for '{abbreviated_name}' (ID: {scholar_id})")

            author_data = self._scholar_client.fetch_author_data(scholar_id, num_articles=1)
            full_name = author_data.name

            logger.info(f"✓ Resolved via Scholar: '{abbreviated_name}' → '{full_name}'")
            return full_name

        except Exception as e:
            logger.debug(f"Scholar resolution failed for '{abbreviated_name}': {e}")
            return None

    def resolve_via_scholar_search(
        self,
        abbreviated_name: str,
        context_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve name by searching Google Scholar profiles (without scholar_id).

        Searches for Scholar profiles matching the abbreviated name,
        then validates by checking shared publications with context researcher.

        Args:
            abbreviated_name: Abbreviated name (e.g., "M Boucher").
            context_name: Optional name of collaborator for validation.

        Returns:
            Full name or None if not found/validated.
        """
        try:
            print(f"[DEBUG] resolve_via_scholar_search called for: {abbreviated_name}")  # FORCED DEBUG
            self._init_scholar()
            print(f"[DEBUG] Scholar client initialized")  # FORCED DEBUG
            logger.debug(f"Searching Google Scholar profiles for '{abbreviated_name}'")

            # Search for profiles
            candidates = self._scholar_client.find_candidates(abbreviated_name, num=5)

            if not candidates:
                logger.debug(f"No Scholar profiles found for '{abbreviated_name}'")
                return None

            # Try each candidate
            for candidate in candidates:
                try:
                    # Get full profile
                    author_data = self._scholar_client.fetch_author_data(
                        candidate.author_id,
                        num_articles=20
                    )

                    full_name = author_data.name

                    # If context provided, validate via shared publications
                    if context_name:
                        # Check if they have publications together
                        has_shared_pubs = False
                        for pub in author_data.top_publications:
                            if pub.authors and context_name in pub.authors:
                                has_shared_pubs = True
                                break

                        if not has_shared_pubs:
                            logger.debug(
                                f"Scholar candidate '{full_name}' has NO shared pubs with '{context_name}'"
                            )
                            continue

                        logger.info(
                            f"✓ Resolved via Scholar search: '{abbreviated_name}' → '{full_name}' "
                            f"(validated with shared publications)"
                        )
                        return full_name
                    else:
                        # No validation needed, return first match
                        logger.info(f"✓ Resolved via Scholar search: '{abbreviated_name}' → '{full_name}'")
                        return full_name

                except Exception as e:
                    logger.debug(f"Error checking Scholar candidate {candidate.author_id}: {e}")
                    continue

            logger.debug(f"No valid Scholar profile found for '{abbreviated_name}'")
            return None

        except Exception as e:
            print(f"[ERROR] Scholar search exception: {e}")  # FORCED ERROR
            logger.debug(f"Scholar search resolution failed for '{abbreviated_name}': {e}")
            return None

    def _validate_coauthor_via_publications(
        self,
        candidate_name: str,
        candidate_id: str,
        context_name: str
    ) -> bool:
        """
        Validate that a candidate author has published with the context researcher.

        Args:
            candidate_name: Full name of candidate (e.g., "Michel Boucher").
            candidate_id: OpenAlex ID of candidate.
            context_name: Name of main researcher to validate against.

        Returns:
            True if they have publications together, False otherwise.
        """
        try:
            # Get candidate's works
            works = self._openalex_client.get_author_works(candidate_id, max_results=50)

            # Check if any work includes the context researcher
            for work in works:
                authorships = work.get("authorships", [])
                for authorship in authorships:
                    author_name = authorship.get("author", {}).get("display_name", "")
                    raw_name = authorship.get("raw_author_name", "")

                    # Check if this authorship matches the context researcher
                    if (context_name.lower() in author_name.lower() or
                        context_name.lower() in raw_name.lower()):
                        logger.debug(
                            f"✓ Validated: '{candidate_name}' has publications with '{context_name}'"
                        )
                        return True

            logger.debug(
                f"✗ Validation failed: '{candidate_name}' has NO publications with '{context_name}'"
            )
            return False

        except Exception as e:
            logger.debug(f"Validation error: {e}")
            return False

    def resolve_via_openalex(
        self,
        abbreviated_name: str,
        context_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve name using OpenAlex (free, no API key).

        IMPORTANT: If context_name is provided, validates that the resolved
        author has actually published with the context researcher.

        Args:
            abbreviated_name: Abbreviated name (e.g., "M Berger").
            context_name: Optional name of collaborator for validation.

        Returns:
            Full name or None if not found/validated.
        """
        try:
            self._init_openalex()
            logger.debug(f"Trying OpenAlex for '{abbreviated_name}'")

            # Search OpenAlex
            author = self._openalex_client.search_author(abbreviated_name)

            if not author:
                return None

            full_name = author.get("display_name")
            author_id = author.get("id")

            # VALIDATION: If context provided, verify they published together
            if context_name and author_id:
                is_valid = self._validate_coauthor_via_publications(
                    full_name,
                    author_id,
                    context_name
                )
                if not is_valid:
                    logger.warning(
                        f"⚠️  OpenAlex found '{full_name}' but NO shared publications with '{context_name}' "
                        f"- skipping (likely wrong person)"
                    )
                    return None

            # Check if the "resolved" name is actually still abbreviated
            if full_name and self.is_abbreviated(full_name):
                logger.debug(f"OpenAlex returned abbreviated name: '{full_name}', searching in works")

                # Strategy: Get author's works and extract full name from raw_author_name
                if author_id:
                    works = self._openalex_client.get_author_works(author_id, max_results=20)

                    # Look for full name in authorships
                    for work in works:
                        authorships = work.get("authorships", [])
                        for authorship in authorships:
                            auth = authorship.get("author", {})
                            if author_id in auth.get("id", ""):
                                # Check raw_author_name (often more complete)
                                raw_name = authorship.get("raw_author_name", "")
                                if raw_name and not self.is_abbreviated(raw_name):
                                    logger.info(f"✓ Resolved via OpenAlex works: '{abbreviated_name}' → '{raw_name}'")
                                    return raw_name

                # If still abbreviated after deeper search, return None
                logger.debug(f"Could not find full name in OpenAlex works for '{abbreviated_name}'")
                return None

            if full_name:
                logger.info(f"✓ Resolved via OpenAlex: '{abbreviated_name}' → '{full_name}'")
                return full_name

            return None

        except Exception as e:
            logger.debug(f"OpenAlex resolution failed for '{abbreviated_name}': {e}")
            return None

    def resolve_via_semantic_scholar(
        self,
        abbreviated_name: str
    ) -> Optional[str]:
        """
        Resolve name using Semantic Scholar (free, no API key).

        Args:
            abbreviated_name: Abbreviated name.

        Returns:
            Full name or None if not found.
        """
        try:
            self._init_semantic_scholar()
            logger.debug(f"Trying Semantic Scholar for '{abbreviated_name}'")

            # Search for author
            results = self._s2_client.search_author(abbreviated_name)

            if not results or len(results) == 0:
                return None

            # Take first result (most relevant)
            author = results[0]
            full_name = author.get("name")

            if full_name:
                logger.info(f"✓ Resolved via Semantic Scholar: '{abbreviated_name}' → '{full_name}'")
                return full_name

            return None

        except Exception as e:
            logger.debug(f"Semantic Scholar resolution failed for '{abbreviated_name}': {e}")
            return None

    def resolve_via_database(
        self,
        abbreviated_name: str,
        scholar_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve name by searching in the database for existing scientists.

        Args:
            abbreviated_name: Name to resolve (e.g., "M Berger").
            scholar_id: Optional Google Scholar ID for exact matching.

        Returns:
            Full name if found in database, None otherwise.
        """
        try:
            from src.database.database import SessionLocal
            from src.database.models import Scientist
            from src.helpers import slug

            db = SessionLocal()
            try:
                # Strategy 1: If scholar_id provided, search by Scholar ID (most reliable)
                if scholar_id:
                    scientist = db.query(Scientist).filter(
                        Scientist.scholar_id == scholar_id
                    ).first()

                    if scientist and scientist.name:
                        logger.info(f"✓ Resolved via DB (Scholar ID): '{abbreviated_name}' → '{scientist.name}'")
                        return scientist.name

                # Strategy 2: Fuzzy search by name — only for non-abbreviated names.
                # Abbreviated names like "L. Wang" are highly ambiguous: any "L. Wang"
                # stored in the DB (from a different researcher's analysis) could be a
                # different person. We must NOT reuse such entries cross-context.
                if not self.is_abbreviated(abbreviated_name):
                    normalized = slug(abbreviated_name)

                    # Try exact normalized match first
                    scientist = db.query(Scientist).filter(
                        Scientist.normalized_name == normalized
                    ).first()

                    if scientist and scientist.name:
                        logger.info(f"✓ Resolved via DB (exact): '{abbreviated_name}' → '{scientist.name}'")
                        return scientist.name

                    # Partial match on normalized name
                    pattern = f"%{normalized}%"
                    scientists = db.query(Scientist).filter(
                        Scientist.normalized_name.like(pattern)
                    ).limit(5).all()

                    for scientist in scientists:
                        if scientist.name:
                            # Validate: check if surnames match
                            parts_input = abbreviated_name.split()
                            parts_found = scientist.name.split()

                            if len(parts_input) > 0 and len(parts_found) > 0:
                                surname_input = parts_input[-1].lower()
                                surname_found = parts_found[-1].lower()

                                if surname_input == surname_found:
                                    logger.info(f"✓ Resolved via DB (partial): '{abbreviated_name}' → '{scientist.name}'")
                                    return scientist.name

                logger.debug(f"No match found in DB for '{abbreviated_name}'")
                return None

            finally:
                db.close()

        except Exception as e:
            logger.debug(f"Database resolution failed for '{abbreviated_name}': {e}")
            return None

    def resolve(
        self,
        abbreviated_name: str,
        scholar_id: Optional[str] = None,
        context_name: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Resolve abbreviated name to full name using multiple sources.

        Strategy:
        1. Check cache
        2. If scholar_id provided → use Google Scholar
        3. If abbreviated → try OpenAlex
        4. Fallback → try Semantic Scholar
        5. Last resort → return abbreviated name

        Args:
            abbreviated_name: Name with initials (e.g., "M Berger").
            scholar_id: Optional Google Scholar ID.
            context_name: Optional collaborator name for validation.

        Returns:
            Tuple of (resolved_name, source):
            - resolved_name: Full name if found, abbreviated otherwise
            - source: "scholar", "openalex", "semantic_scholar", or "none"
        """
        # Check cache first
        cache_key = f"{abbreviated_name}:{scholar_id or 'no_id'}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.debug(f"Cache hit: '{abbreviated_name}' → '{cached[0]}'")
            return cached

        # Strategy 0: Try Database first (always - it's fast and free)
        full_name = self.resolve_via_database(abbreviated_name, scholar_id)
        if full_name:
            result = (full_name, "database")
            self._cache[cache_key] = result
            return result

        # If DB-only mode, stop here (no API calls)
        if self._use_db_only:
            logger.debug(f"DB-only mode: Could not resolve '{abbreviated_name}' from database, using as-is")
            result = (abbreviated_name, "none")
            self._cache[cache_key] = result
            return result

        # === API-BASED RESOLUTION (only if not use_db_only) ===

        # Strategy 1: Google Scholar (if ID available)
        if scholar_id:
            full_name = self.resolve_via_scholar(abbreviated_name, scholar_id)
            if full_name:
                result = (full_name, "scholar")
                self._cache[cache_key] = result
                return result

        # Strategy 2: Google Scholar search (even without ID, if abbreviated)
        # Skip if skip_scholar_search=True (very expensive: fetches full profiles per candidate)
        if self.is_abbreviated(abbreviated_name) and not self._skip_scholar_search:
            full_name = self.resolve_via_scholar_search(abbreviated_name, context_name)
            if full_name:
                result = (full_name, "scholar_search")
                self._cache[cache_key] = result
                return result

        # Strategy 3: OpenAlex (fallback for academic names)
        if self.is_abbreviated(abbreviated_name):
            full_name = self.resolve_via_openalex(abbreviated_name, context_name)
            if full_name:
                result = (full_name, "openalex")
                self._cache[cache_key] = result
                return result

            # Strategy 4: Semantic Scholar (last resort)
            full_name = self.resolve_via_semantic_scholar(abbreviated_name)
            if full_name:
                result = (full_name, "semantic_scholar")
                self._cache[cache_key] = result
                return result

        # Last resort: return as-is
        logger.debug(f"Could not resolve '{abbreviated_name}', using as-is")
        result = (abbreviated_name, "none")
        self._cache[cache_key] = result
        return result

    def batch_resolve(
        self,
        coauthors: List,
        context_name: Optional[str] = None
    ) -> List[Tuple[str, str, str]]:
        """
        Batch resolve a list of co-authors.

        Args:
            coauthors: List of CoAuthor objects with name and scholar_id.
            context_name: Optional name of main researcher for validation.

        Returns:
            List of tuples (original_name, resolved_name, source).
        """
        resolved = []

        for coauthor in coauthors:
            full_name, source = self.resolve(
                coauthor.name,
                coauthor.scholar_id,
                context_name
            )
            resolved.append((coauthor.name, full_name, source))

        return resolved
