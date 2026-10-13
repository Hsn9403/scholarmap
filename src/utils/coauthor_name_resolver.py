#!/usr/bin/env python3
"""
Co-author name resolver using publications.

Resolves co-author abbreviated names by finding them in the main researcher's publications.
This is the most reliable method as it uses the actual publication metadata.
"""
from typing import Optional, List, Dict
from src.logger import logger


class CoauthorNameResolver:
    """
    Resolves co-author names using publication metadata.

    Strategy:
    For a main researcher and a co-author with abbreviated name (e.g., "M Berger"):
    1. Get all publications of the main researcher
    2. Find publications that include the co-author (fuzzy match on surname)
    3. Extract the full author list from those publications
    4. Match the abbreviated name to the full name

    This is more reliable than external APIs because it uses the actual
    publication data where both researchers collaborated.
    """

    def __init__(self, scholar_data):
        """
        Initialize with main researcher's Scholar data.

        Args:
            scholar_data: ScholarData object with publications and coauthors.
        """
        self.scholar_data = scholar_data
        self._cache = {}

    def _normalize_surname(self, name: str) -> str:
        """Extract and normalize surname from a name."""
        # Take last word as surname
        parts = name.strip().split()
        if not parts:
            return ""
        surname = parts[-1].lower()
        # Remove punctuation
        surname = ''.join(c for c in surname if c.isalpha())
        return surname

    def _matches_initial(self, full_name: str, abbreviated_name: str) -> bool:
        """
        Check if full name matches abbreviated name.

        Examples:
            ("Michel Berger", "M Berger") → True
            ("Michel Berger", "M. Berger") → True
            ("Michel Berger", "MB") → False (too short)
            ("Maria Berger", "M Berger") → True
        """
        full_parts = full_name.strip().split()
        abbr_parts = abbreviated_name.strip().replace(".", "").split()

        if len(full_parts) < 2 or len(abbr_parts) < 2:
            return False

        # Check if surnames match
        if self._normalize_surname(full_parts[-1]) != self._normalize_surname(abbr_parts[-1]):
            return False

        # Check if first name matches initial
        first_full = full_parts[0].lower()
        first_abbr = abbr_parts[0].lower().replace(".", "")

        # Accept if abbreviated is initial of full
        if len(first_abbr) == 1 and first_full.startswith(first_abbr):
            return True

        # Accept if they're the same
        if first_full == first_abbr:
            return True

        return False

    def resolve(self, abbreviated_coauthor_name: str) -> Optional[str]:
        """
        Resolve co-author abbreviated name to full name.

        Args:
            abbreviated_coauthor_name: Abbreviated co-author name (e.g., "M Berger").

        Returns:
            Full name if found, None otherwise.
        """
        # Check cache
        if abbreviated_coauthor_name in self._cache:
            return self._cache[abbreviated_coauthor_name]

        logger.debug(f"Resolving '{abbreviated_coauthor_name}' from publications")

        # Get surname from abbreviated name
        abbr_surname = self._normalize_surname(abbreviated_coauthor_name)

        if not abbr_surname:
            return None

        # Search through all publications and collect ALL matching full names.
        # Only resolve if there is exactly one unique match — multiple different
        # full names that fit the same initial (e.g., "Linlin Wang" and "Lei Wang"
        # both matching "L. Wang") means we cannot disambiguate safely.
        import re
        _abbreviated_pattern = re.compile(r'^[A-Z]{1,3}[\s\.\-]*\s+[A-Z][a-z]+')

        candidates: set = set()

        for pub in self.scholar_data.top_publications:
            if not pub.authors:
                continue

            for author in pub.authors:
                author_surname = self._normalize_surname(author)

                if author_surname == abbr_surname:
                    if self._matches_initial(author, abbreviated_coauthor_name):
                        # Skip if the match is itself an abbreviated name
                        if not _abbreviated_pattern.match(author.strip()):
                            candidates.add(author)

        if len(candidates) == 1:
            resolved = next(iter(candidates))
            logger.info(
                f"✓ Resolved from publications: '{abbreviated_coauthor_name}' → '{resolved}' "
                f"(unique match across all publications)"
            )
            self._cache[abbreviated_coauthor_name] = resolved
            return resolved
        elif len(candidates) > 1:
            logger.warning(
                f"⚠ Ambiguous resolution for '{abbreviated_coauthor_name}': "
                f"multiple full names found {candidates} — keeping abbreviated"
            )

        logger.debug(f"Could not resolve '{abbreviated_coauthor_name}' from publications")
        return None

    def batch_resolve(self, coauthor_names: List[str]) -> Dict[str, Optional[str]]:
        """
        Batch resolve multiple co-author names.

        Args:
            coauthor_names: List of abbreviated co-author names.

        Returns:
            Dict mapping abbreviated name → full name (or None if not found).
        """
        resolved = {}
        for name in coauthor_names:
            resolved[name] = self.resolve(name)
        return resolved
