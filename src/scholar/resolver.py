#!/usr/bin/env python3
"""
Google Scholar profile disambiguation and resolution.

This module handles the resolution of researcher names to unique
Google Scholar author IDs, including interactive disambiguation
when multiple candidates match.
"""
from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

from src.models import ScholarCandidate, ScholarData
from src.logger import logger

from .matching import name_matches_query, score_candidate

if TYPE_CHECKING:
    from .client import ScholarClient


class ScholarResolver:
    """
    Resolves researcher names to Google Scholar author IDs.

    This class handles the disambiguation process when multiple
    Scholar profiles match a search query.

    Attributes:
        client (ScholarClient): The underlying Scholar client.

    Example:
        >>> from src.scholar import ScholarClient
        >>> client = ScholarClient()
        >>> resolver = ScholarResolver(client)
        >>> author_id = resolver.resolve("John Smith")
    """

    def __init__(self, client: "ScholarClient"):
        """
        Initialize the resolver.

        Args:
            client: A ScholarClient instance for API calls.
        """
        self.client = client

    def resolve(
        self,
        researcher_name: str,
        hl: Optional[str] = None,
        max_candidates: int = 8,
        interactive: bool = True
    ) -> Optional[str]:
        """
        Resolve a researcher name to a single Google Scholar author ID.

        This method handles disambiguation when multiple profiles match:
        - If 0 candidates: returns None
        - If 1 candidate (with name match): returns the author_id
        - If multiple candidates: interactive selection or first match

        Args:
            researcher_name: Name of the researcher to search.
            hl: Language code (uses client default if not specified).
            max_candidates: Maximum candidates to enrich with full data.
            interactive: If True, prompt user for selection when ambiguous.

        Returns:
            The resolved author_id, None if not found, or "__QUIT__" if cancelled.

        Example:
            >>> author_id = resolver.resolve("Marie Curie")
            >>> if author_id and author_id != "__QUIT__":
            ...     print(f"Found: {author_id}")
        """
        hl = hl or self.client.hl
        candidates = self.client.find_candidates(researcher_name, hl=hl, num=10)

        if not candidates:
            self._print_not_found(researcher_name)
            return None

        # Single candidate: verify name match
        if len(candidates) == 1:
            return self._handle_single_candidate(
                candidates[0], researcher_name, hl
            )

        # Multiple candidates: enrich and filter
        enriched = self._enrich_candidates(candidates[:max_candidates], hl)

        # Strict filtering: only keep name matches
        strict = [
            (c, sd) for (c, sd) in enriched
            if sd and name_matches_query(researcher_name, sd.name)
        ]

        if not strict:
            print(f"\n Aucun profil Google Scholar ne correspond a \"{researcher_name}\".")
            print("Les profils trouves semblent etre des co-auteurs.")
            self._print_suggestions()
            return None

        # Single match after filtering
        if len(strict) == 1:
            return strict[0][0].author_id

        # Multiple matches: need disambiguation
        if not interactive:
            logger.warning(
                f"Multiple candidates for '{researcher_name}', "
                "returning None (non-interactive)"
            )
            return None

        return self._interactive_selection(researcher_name, strict)

    def _handle_single_candidate(
        self,
        candidate: ScholarCandidate,
        researcher_name: str,
        hl: str
    ) -> Optional[str]:
        """Handle the case of a single candidate found."""
        try:
            sd = self.client.fetch_author_data(candidate.author_id, hl=hl)
        except Exception:
            sd = None

        if sd and name_matches_query(researcher_name, sd.name):
            return candidate.author_id

        print(f"\n Aucun profil Google Scholar ne correspond a \"{researcher_name}\".")
        print("Le seul profil trouve semble etre un co-auteur.")
        self._print_suggestions()
        return None

    def _enrich_candidates(
        self,
        candidates: List[ScholarCandidate],
        hl: str
    ) -> List[Tuple[ScholarCandidate, Optional[ScholarData]]]:
        """Fetch full ScholarData for each candidate."""
        enriched = []
        for c in candidates:
            try:
                sd = self.client.fetch_author_data(c.author_id, hl=hl)
            except Exception:
                sd = None
            enriched.append((c, sd))
        return enriched

    def _interactive_selection(
        self,
        researcher_name: str,
        candidates: List[Tuple[ScholarCandidate, Optional[ScholarData]]]
    ) -> Optional[str]:
        """
        Interactive CLI selection of a Scholar profile.

        Args:
            researcher_name: Original search query.
            candidates: List of (ScholarCandidate, ScholarData) tuples.

        Returns:
            Selected author_id, None if cancelled, or "__QUIT__" if user quit.
        """
        current = candidates
        enriched = candidates  # Keep original for filtering

        while True:
            print(f"\n Plusieurs profils Google Scholar trouves pour: {researcher_name}")
            print("Choisis le bon profil (ou tape un filtre pour affiner).")
            print('Exemples filtres: "Oxford", "INRIA", "neuroscience"...\n')

            for i, (c, sd) in enumerate(current, start=1):
                self._print_candidate(i, c, sd)

            choice = input(
                f" Entre un numero (1-{len(current)}), f pour filtrer, "
                f"ou 0 pour quitter: "
            )

            if choice == "0":
                print("\n Annulation demandee. Aucun rapport genere.\n")
                return "__QUIT__"

            if choice.lower() == "f":
                current = self._apply_filter(enriched, current)
                continue

            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(current):
                    selected_candidate, selected_sd = current[idx - 1]
                    name_display = (
                        selected_sd.name if selected_sd
                        else selected_candidate.author_id
                    )
                    print(
                        f"\n Profil selectionne: {name_display} "
                        f"(author_id={selected_candidate.author_id})\n"
                    )
                    return selected_candidate.author_id

            print(" Entree invalide. Reessaie.")

    def _apply_filter(
        self,
        enriched: List[Tuple[ScholarCandidate, Optional[ScholarData]]],
        current: List[Tuple[ScholarCandidate, Optional[ScholarData]]]
    ) -> List[Tuple[ScholarCandidate, Optional[ScholarData]]]:
        """Apply a user filter to candidates."""
        ft = input("Filtre (affiliation/mots-cles): ").strip()
        if not ft:
            return current

        scored = []
        for c, sd in enriched:
            if not sd:
                continue
            s = score_candidate(ft, sd, google_snippet=c.snippet)
            scored.append((s, c, sd))

        scored.sort(key=lambda x: x[0], reverse=True)
        filtered = [(c, sd) for s, c, sd in scored if s > 0]
        if not filtered:
            filtered = [(c, sd) for s, c, sd in scored]

        return filtered if filtered else current

    def _print_candidate(
        self,
        index: int,
        candidate: ScholarCandidate,
        data: Optional[ScholarData]
    ) -> None:
        """Print a single candidate for display."""
        if data:
            print(f"[{index}] {data.name or '(no name)'} - {data.affiliation or '(no affiliation)'}")
            cit = data.citations_total if data.citations_total is not None else "?"
            h = data.h_index if data.h_index is not None else "?"
            pubs = data.publications_total if data.publications_total is not None else "?"
            print(f"    Citations: {cit} | H-index: {h} | Pubs: {pubs}")
        else:
            print(f"[{index}] {candidate.title or '(profil Scholar)'}")
        print(f"    Profile: {candidate.link}")
        if candidate.snippet:
            print(f"    Snippet: {candidate.snippet}")
        print("")

    def _print_not_found(self, researcher_name: str) -> None:
        """Print message when no profiles are found."""
        print(f"\n Aucun profil Google Scholar trouve pour \"{researcher_name}\".")
        print("Suggestions :")
        print("- Verifie l'orthographe")
        print('- Essaie avec une initiale (ex: "John A. Doe")')
        print("- Ajoute une affiliation")
        print("- Le chercheur n'a peut-etre pas de profil public\n")

    def _print_suggestions(self) -> None:
        """Print suggestions when no match is found."""
        print("Suggestions :")
        print('- Verifie l\'orthographe (accents inclus)')
        print('- Essaie avec une initiale : ex "T. Smith"')
        print("- Ajoute une affiliation dans ta recherche")
        print("- Si la personne n'a pas de profil public, il est normal de ne rien trouver\n")
