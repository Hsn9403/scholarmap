#!/usr/bin/env python3
"""
Google Patents client for patent data retrieval.

This module provides the main PatentsClient class that orchestrates
patent search, detail fetching, and data enrichment.
"""
from __future__ import annotations

import os
import re
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote_plus

from src.api import SerpAPIClient
from src.models import PatentItem, PatentsData
from src.helpers import strip_accents_basic
from src.logger import logger
from src.exceptions import APIError
from src.validation import validate_patent_id, validate_researcher_name, validate_integer
from .entity import same_person, same_org
from .extractors import (
    extract_citing_patents,
    extract_cited_patents,
    extract_inventors,
    extract_top_claims,
    extract_cited_by_count,
    extract_assignees,
    extract_current_assignee,
    extract_dates,
)
from .parsers import (
    parse_cited_by_table,
    parse_current_assignee,
    has_cited_by_section,
)


class PatentsClient:
    """
    Client for interacting with Google Patents via SerpAPI.

    This class provides methods to search for patents, fetch details,
    and enrich patent data with citations and co-inventors.

    Attributes:
        api_client (SerpAPIClient): The underlying SerpAPI client.
        hl (str): Default language code for searches.

    Example:
        >>> client = PatentsClient()
        >>> data = client.fetch_patents_data("Marie Curie")
        >>> print(f"Total: {data.patents_total}")
        >>> for p in data.top_patents:
        ...     print(f"  - {p.title}")
    """

    def __init__(
        self,
        api_client: Optional[SerpAPIClient] = None,
        api_key: Optional[str] = None,
        hl: str = "en"
    ):
        """
        Initialize the Patents client.

        Args:
            api_client: Existing SerpAPIClient instance (optional).
            api_key: SerpAPI key (used if api_client not provided).
            hl: Default language code (default: "en").
        """
        self.api_client = api_client or SerpAPIClient(api_key=api_key)
        self.hl = hl
        logger.debug(f"PatentsClient initialized (hl={hl})")

    def search(self, query: str, num: int = 10) -> Dict[str, Any]:
        """
        Search Google Patents.

        Args:
            query: Search query (can use inventor:, assignee:, etc.).
            num: Number of results (default: 10).

        Returns:
            Raw API response dictionary.
        """
        params = {
            "engine": "google_patents",
            "q": query,
            "num": num,
            "no_cache": "false",
        }
        return self.api_client.search(params)

    def search_by_inventor(self, inventor_name: str, num: int = 10) -> Dict[str, Any]:
        """
        Search Google Patents using the dedicated inventor parameter.

        Uses the `inventor=` SerpAPI param (more precise than q=inventor:"...")
        and restricts language to ENGLISH,FRENCH to avoid duplicate JP/CN/KR versions
        of the same patent appearing as separate results.
        """
        params = {
            "engine": "google_patents",
            "q": "",
            "inventor": strip_accents_basic(inventor_name),
            "language": "ENGLISH,FRENCH",
            "num": num,
            "no_cache": "false",
        }
        return self.api_client.search(params)

    def get_details(self, patent_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information for a patent.

        Args:
            patent_id: Patent ID (e.g., "US10000000" or "patent/US10000000/en").

        Returns:
            Patent details dictionary.
        """
        # Validate and normalize patent ID
        patent_id = validate_patent_id(patent_id)

        if not patent_id.startswith("patent/"):
            patent_id = f"patent/{patent_id}/en"

        params = {
            "engine": "google_patents_details",
            "patent_id": patent_id,
            "hl": self.hl,
            "no_cache": "false",
        }
        return self.api_client.search(params)

    def get_html(self, patent_id: str) -> str:
        """
        Fetch full HTML page for a patent.

        Args:
            patent_id: Patent ID.

        Returns:
            HTML content string.
        """
        if not patent_id:
            return ""

        if not patent_id.startswith("patent/"):
            patent_id = f"patent/{patent_id}/en"

        params = {
            "engine": "google_patents_details",
            "patent_id": patent_id,
            "hl": self.hl,
            "no_cache": "false",
            "output": "html",
        }

        res = self.api_client.search(params)

        # Direct HTML in response
        html = res.get("html")
        if isinstance(html, str) and len(html) > 50_000:
            return html

        # Try raw_html_file URL
        raw_url = (res.get("search_metadata") or {}).get("raw_html_file", "").strip()
        if raw_url:
            try:
                r = requests.get(raw_url, timeout=30)
                if r.status_code == 200 and len(r.text) > 10_000:
                    return r.text
            except Exception as e:
                logger.warning(f"Failed to fetch raw HTML: {e}")

        return html if isinstance(html, str) else ""

    def resolve_patent_assignee(self, publication_number: str) -> str:
        """
        Resolve the current assignee for a patent by its publication number.

        This method is used when a patent citation lists a person name instead
        of the company assignee. It fetches the patent details and returns the
        current assignee (company).

        Args:
            publication_number: Patent publication number (e.g., "US10000000").

        Returns:
            Current assignee name, or empty string if not found.

        Example:
            >>> assignee = client.resolve_patent_assignee("US10000000")
            >>> print(assignee)  # "Acme Corp"
        """
        if not publication_number or not publication_number.strip():
            return ""

        try:
            # Normalize patent ID
            patent_id = publication_number.strip()
            if not patent_id.startswith("patent/"):
                patent_id = f"patent/{patent_id}/en"

            # Get details
            details = self.get_details(patent_id)

            # Try to extract current assignee from API response
            current_assignee = extract_current_assignee(details)
            if current_assignee:
                return current_assignee

            # Fallback to HTML parsing
            html = self.get_html(patent_id)
            return parse_current_assignee(html)

        except Exception as e:
            logger.warning(f"Failed to resolve assignee for {publication_number}: {e}")
            return ""

    def fetch_patents_data(self, inventor_name: str, max_patents: int = 10, researcher_specialty: str = "") -> PatentsData:
        """
        Fetch and enrich patent data for an inventor.

        This is the main method that:
        1. Searches patents by inventor name
        2. Fetches details for each patent
        3. Extracts citations, assignees, co-inventors
        4. For names with a middle initial: also searches without middle name
           and validates new patents via GPT against researcher specialty.

        Args:
            inventor_name: Name of the inventor.
            max_patents: Maximum patents to process (default: 10).
            researcher_specialty: Researcher's specialty (comma-separated tags or
                free text). Used to validate patents found via without-middle-name
                search. If empty, fetched from OpenAlex automatically.

        Returns:
            PatentsData with total count and enriched patents.

        Example:
            >>> data = client.fetch_patents_data("John Smith")
            >>> for p in data.top_patents:
            ...     print(f"{p.title}: {p.cited_by} citations")
        """
        # Validate inputs
        inventor_name = validate_researcher_name(inventor_name)
        max_patents = validate_integer(max_patents, min_val=1, max_val=100, param_name="max_patents")

        # Try to search for patents, but handle gracefully if none found
        # Use dedicated inventor= param + language filter (ENGLISH,FRENCH) to avoid
        # JP/CN/KR duplicate versions of the same patent appearing as separate results
        try:
            res = self.search_by_inventor(inventor_name, num=max_patents)
        except APIError as e:
            # If no patents found, return empty data instead of crashing
            if "hasn't returned any results" in str(e):
                logger.info(f"No patents found for '{inventor_name}'")
                res = {}
            else:
                raise

        # Extract total
        info = res.get("search_information") or {}
        total_raw = info.get("total_results")
        patents_total = (
            "≥100" if isinstance(total_raw, int) and total_raw > 100
            else (total_raw if isinstance(total_raw, int) else "")
        )

        # Build patent list
        results = res.get("organic_results") or []

        # ── Middle-initial logic ───────────────────────────────────────────────
        # For names with a middle initial (e.g. "Jeffrey L. Saver", "Gregory W. Albers"):
        #
        # Rule 1 — Search WITH middle initial (already done above) → keep ALL results.
        #
        # Rule 2/3/4 — Search WITHOUT middle initial → enrich → filter:
        #   Rule 2: inventor has the correct middle initial/name → KEEP (certain match)
        #           e.g. "Gregory William Albers" when looking for "Gregory W. Albers"
        #   Rule 3: inventor has no middle name (just first + last) → GPT validates
        #           against researcher specialty → KEEP if yes, REJECT if no
        #   Rule 4: inventor has a *different* middle initial → REJECT (homonym)
        #           e.g. "Gregory J. Albers" when looking for "Gregory W. Albers"
        #
        # New patents from without-middle search are merged with Rule 1 results.
        initial = self._extract_middle_initial(inventor_name)
        _no_middle_raw: List[dict] = []  # raw SerpAPI results from without-middle search

        # Only run without-middle search if primary results are sparse (< 10).
        # When a researcher already has several patents indexed under their full
        # name+initial, the without-middle search returns mostly homonyms and
        # adds no value (e.g. "Thanh Nguyen" → 8000+ unrelated results).
        _WITHOUT_MIDDLE_THRESHOLD = 10

        if initial and len(results) < _WITHOUT_MIDDLE_THRESHOLD:
            name_parts = inventor_name.strip().split()
            first_last = f"{name_parts[0]} {name_parts[-1]}"
            logger.info(
                f"[Patents] Middle-initial search: '{inventor_name}' ({len(results)} result(s)) "
                f"+ without-middle search: '{first_last}'"
            )
            try:
                res_no_mid = self.search_by_inventor(first_last, num=max_patents * 3)
                results_no_mid = res_no_mid.get("organic_results") or []
                # Only keep patents not already found in the primary (Rule 1) results
                primary_titles = {(r.get("title") or "").strip().lower() for r in results}
                _no_middle_raw = [
                    r for r in results_no_mid
                    if (r.get("title") or "").strip().lower() not in primary_titles
                ]
                logger.info(
                    f"[Patents] Without-middle: {len(results_no_mid)} result(s), "
                    f"{len(_no_middle_raw)} new candidate(s) to filter (Rules 2/3/4)"
                )
            except APIError:
                pass

        fallback_url = f"https://patents.google.com/?inventor={quote_plus(strip_accents_basic(inventor_name))}"

        top: List[PatentItem] = []
        for r in results[:max_patents]:
            title = (r.get("title") or "").strip() or "(no title)"
            link = (r.get("link") or "").strip()

            if not link:
                pub = r.get("publication_number") or r.get("patent_id")
                link = f"https://patents.google.com/patent/{pub}/en" if pub else fallback_url

            top.append(PatentItem(
                title=title,
                link=link,
                patent_id=self._extract_id_from_url(link),
                claims_top3=[],
                cited_by=None,
                cited_assignees=[],
                citing_assignees=[],
                co_inventors=[],
                inventors=[],
            ))

        # Enrich each patent in parallel (each call is one independent SerpAPI request)
        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
        with ThreadPoolExecutor(max_workers=5) as _pool:
            _futures = {_pool.submit(self._enrich_patent, p, inventor_name): p for p in top}
            for _fut in _as_completed(_futures):
                try:
                    _fut.result()
                except Exception as _e:
                    logger.warning(f"Patent enrichment error: {_e}")

        # Deduplicate by normalized title (same invention, different patent offices/languages)
        seen_titles: dict = {}
        deduped: List[PatentItem] = []
        for patent in top:
            title_key = patent.title.strip().lower()
            if title_key not in seen_titles:
                seen_titles[title_key] = patent
                deduped.append(patent)
            else:
                existing = seen_titles[title_key]
                existing_score = (existing.cited_by or 0) + len(existing.co_inventors or [])
                new_score = (patent.cited_by or 0) + len(patent.co_inventors or [])
                if new_score > existing_score:
                    deduped[deduped.index(existing)] = patent
                    seen_titles[title_key] = patent
                    logger.debug(f"Replaced duplicate patent with richer version: {patent.title[:60]}")
                else:
                    logger.debug(f"Skipped duplicate patent: {patent.title[:60]}")

        if len(deduped) < len(top):
            logger.info(f"Deduplicated patents: {len(top)} → {len(deduped)}")
        top = deduped

        # ── Apply Rules 2/3/4 to without-middle candidates ────────────────────
        # Optimisation : on classe via les données brutes SerpAPI (champ `inventors`
        # déjà présent) au lieu d'enrichir tous les candidats juste pour avoir la liste
        # des inventeurs. L'enrichissement SerpAPI n'intervient qu'APRÈS GPT, uniquement
        # sur les quelques patents réellement conservés (typiquement 0–3).
        if _no_middle_raw and initial:
            name_parts_fl = inventor_name.strip().split()
            first_last_fl = f"{name_parts_fl[0]} {name_parts_fl[-1]}"

            # Pré-classification via données brutes (Rules 2/3/4)
            rule2_raw: List[dict] = []
            rule3_ambiguous_raw: List[dict] = []

            for r in _no_middle_raw:
                raw_inventors = self._normalize_inventor_list(r.get("inventors"))
                if raw_inventors:
                    correct = any(
                        self._inventor_matches_middle_initial(inv, first_last_fl, initial)
                        for inv in raw_inventors
                    )
                    if correct:
                        logger.info(f"[Patents] Rule 2 KEEP (raw) '{(r.get('title') or '')[:60]}'")
                        rule2_raw.append(r)
                        continue

                    wrong = any(
                        len(strip_accents_basic(inv).strip().split()) >= 3
                        and strip_accents_basic(inv).strip().split()[0].lower().rstrip(".") == first_last_fl.split()[0].lower()
                        and strip_accents_basic(inv).strip().split()[-1].lower() == first_last_fl.split()[-1].lower()
                        and not self._inventor_matches_middle_initial(inv, first_last_fl, initial)
                        for inv in raw_inventors
                    )
                    if wrong:
                        logger.info(f"[Patents] Rule 4 REJECT (raw) '{(r.get('title') or '')[:60]}'")
                        continue

                # Rule 3 : pas d'info middle ou inventeurs absents → ambigu
                rule3_ambiguous_raw.append(r)

            # Rule 3 : validation GPT sur les titres/snippets bruts — toujours pas d'enrichissement
            rule3_validated_raw: List[dict] = []
            if rule3_ambiguous_raw:
                specialty = researcher_specialty.strip()
                if not specialty:
                    specialty = self._fetch_specialty_from_openalex(inventor_name)
                if specialty:
                    rule3_validated_raw = self._validate_patents_raw(
                        rule3_ambiguous_raw, specialty, inventor_name, fallback_url
                    )
                    logger.info(
                        f"[Patents] Rule 3 GPT: {len(rule3_validated_raw)}/{len(rule3_ambiguous_raw)} "
                        f"ambiguous patent(s) kept for '{inventor_name}'"
                    )
                else:
                    rule3_validated_raw = rule3_ambiguous_raw  # pas de spécialité → tout garder

            # Enrichissement uniquement sur les patents conservés (Rule 2 + Rule 3 GPT-validés)
            to_enrich = rule2_raw + rule3_validated_raw
            rule2_kept: List[PatentItem] = []
            rule3_kept: List[PatentItem] = []

            if to_enrich:
                n_rule2 = len(rule2_raw)

                def _build_and_enrich(args):
                    r, idx = args
                    title = (r.get("title") or "").strip() or "(no title)"
                    link = (r.get("link") or "").strip()
                    if not link:
                        pub = r.get("publication_number") or r.get("patent_id")
                        link = f"https://patents.google.com/patent/{pub}/en" if pub else fallback_url
                    item = PatentItem(
                        title=title, link=link,
                        patent_id=self._extract_id_from_url(link),
                        claims_top3=[], cited_by=None, cited_assignees=[],
                        citing_assignees=[], co_inventors=[], inventors=[],
                    )
                    self._enrich_patent(item, inventor_name)
                    return idx, item

                from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed2
                _enriched_map: dict = {}
                with ThreadPoolExecutor(max_workers=5) as _pool2:
                    _futs2 = {_pool2.submit(_build_and_enrich, (r, i)): i
                              for i, r in enumerate(to_enrich)}
                    for _f in _as_completed2(_futs2):
                        try:
                            idx, item = _f.result()
                            _enriched_map[idx] = item
                        except Exception as _e:
                            logger.warning(f"Patent enrichment error (no-middle): {_e}")

                for i in sorted(_enriched_map):
                    if i < n_rule2:
                        rule2_kept.append(_enriched_map[i])
                    else:
                        rule3_kept.append(_enriched_map[i])

            top.extend(rule2_kept)
            top.extend(rule3_kept)
            if rule2_kept or rule3_kept:
                logger.info(
                    f"[Patents] Without-middle final: +{len(rule2_kept)} Rule2 "
                    f"+{len(rule3_kept)} Rule3 patent(s) added for '{inventor_name}'"
                )

        logger.info(f"Fetched {len(top)} patents for '{inventor_name}'")
        return PatentsData(patents_total=patents_total, top_patents=top)

    def _enrich_patent(self, patent: PatentItem, inventor_name: str) -> None:
        """Enrich a PatentItem with detailed information."""
        # Initialize fields
        patent.cited_patents = []
        patent.citing_patents = []
        patent.current_assignee = ""
        patent.publication_date = None
        patent.filing_date = None
        patent.priority_date = None
        patent.inventors = []
        patent.co_inventors = []
        patent.cited_assignees = []
        patent.citing_assignees = []

        if not patent.patent_id:
            patent.cited_patents = []
            patent.citing_assignees = ["no corporate has cited this patent"]
            return

        try:
            details = self.get_details(patent.patent_id)

            # Current assignee
            patent.current_assignee = extract_current_assignee(details)
            if not patent.current_assignee:
                html = self.get_html(patent.patent_id)
                patent.current_assignee = parse_current_assignee(html)

            # Dates
            dates = extract_dates(details)
            patent.publication_date = dates["publication_date"]
            patent.filing_date = dates["filing_date"]
            patent.priority_date = dates["priority_date"]

            # Claims and citation count
            patent.claims_top3 = extract_top_claims(details)
            patent.cited_by = extract_cited_by_count(details)

            # Backward citations (cited patents)
            cited = extract_cited_patents(details)
            patent.cited_patents = [cp.__dict__ for cp in cited]

            # Forward citations (citing patents)
            citing = extract_citing_patents(details)
            patent.citing_patents = [cp.__dict__ for cp in citing]

            # HTML fallback for citations
            if not patent.citing_patents:
                html = self.get_html(patent.patent_id)
                if has_cited_by_section(html):
                    patent.citing_patents = parse_cited_by_table(html)

            # Citing assignees (filter self-citations)
            patent.citing_assignees = self._dedup([
                (e.get("assignee") or "").strip()
                for e in (patent.citing_patents or [])
                if (e.get("assignee") or "").strip()
                and not same_org(e.get("assignee", ""), patent.current_assignee)
            ])
            event_assignees = patent.citing_assignees[:]

            # Cited/citing from tables
            cited, citing_table = extract_assignees(details)
            patent.cited_assignees = cited

            if event_assignees:
                patent.citing_assignees = event_assignees
            else:
                patent.citing_assignees = [
                    c for c in citing_table
                    if c and not same_org(c, patent.current_assignee)
                ]

            # Co-inventors
            inventors = extract_inventors(details)
            patent.inventors = inventors  # ALL inventors (complete list)
            patent.co_inventors = [
                inv for inv in inventors
                if not same_person(inv, inventor_name)
            ]

        except Exception as e:
            logger.warning(f"Failed to enrich {patent.patent_id}: {e}")
            patent.claims_top3 = []
            patent.cited_by = None
            patent.cited_assignees = []
            patent.cited_patents = []
            patent.citing_patents = []
            patent.citing_assignees = ["no corporate has cited this patent"]
            patent.inventors = []
            patent.co_inventors = []

    def _fetch_specialty_from_openalex(self, inventor_name: str) -> str:
        """Fetch researcher specialty (top 3 topics) from OpenAlex by name."""
        try:
            import requests as _req
            _key = os.getenv("OPENALEX_API_KEY")
            resp = _req.get(
                "https://api.openalex.org/authors",
                params={"search": inventor_name, "per-page": 1},
                headers={"Authorization": f"Bearer {_key}"} if _key else None,
                timeout=10,
            )
            results = resp.json().get("results", [])
            if not results:
                return ""
            topics = results[0].get("topics", [])
            top3 = sorted(topics, key=lambda x: x.get("score") or 0, reverse=True)[:3]
            names = [t.get("display_name", "") for t in top3 if t.get("display_name")]
            return ", ".join(names)
        except Exception as e:
            logger.warning(f"[Patents] Could not fetch specialty from OpenAlex for '{inventor_name}': {e}")
            return ""

    def _validate_patents_raw(
        self,
        raw_results: List[dict],
        specialty: str,
        inventor_name: str,
        fallback_url: str,
    ) -> List[dict]:
        """
        GPT specialty validation on raw SerpAPI dicts.
        Returns the validated raw dicts — no enrichment (caller enriches after).
        """
        import os
        try:
            from openai import OpenAI
        except ImportError:
            return raw_results

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return raw_results

        client = OpenAI(api_key=api_key)

        def _check_one(r: dict) -> Optional[dict]:
            title = (r.get("title") or "").strip() or "(no title)"
            assignees_raw = r.get("assignees") or []
            assignee_str = (
                ", ".join(a.get("name", a) if isinstance(a, dict) else str(a) for a in assignees_raw)
                if isinstance(assignees_raw, list) else str(assignees_raw)
            )
            snippet = (r.get("snippet") or "").strip()
            context_parts = [f"Patent title: {title}"]
            if assignee_str:
                context_parts.append(f"Assignee: {assignee_str}")
            if snippet:
                context_parts.append(f"Abstract: {snippet[:300]}")
            try:
                response = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": (
                        f"Researcher specialty: {specialty}\n"
                        f"{chr(10).join(context_parts)}\n\n"
                        f"Could this patent plausibly belong to a researcher with this specialty? "
                        f"Answer only 'yes' or 'no'."
                    )}],
                    max_completion_tokens=10,
                    temperature=0,
                )
                answer = response.choices[0].message.content.strip().lower()
                if answer.startswith("yes"):
                    logger.info(f"[Patents] GPT: KEEP '{title[:60]}' (matches specialty of '{inventor_name}')")
                    return r
                else:
                    logger.info(f"[Patents] GPT: REJECT '{title[:60]}' (does not match specialty of '{inventor_name}')")
                    return None
            except Exception as e:
                logger.warning(f"[Patents] GPT specialty check failed for '{title[:60]}': {e}")
                return r  # conserver en cas d'erreur

        from concurrent.futures import ThreadPoolExecutor, as_completed as _ac_gpt
        validated: List[dict] = []
        with ThreadPoolExecutor(max_workers=20) as _pool:
            futures = {_pool.submit(_check_one, r): r for r in raw_results}
            for fut in _ac_gpt(futures):
                result = fut.result()
                if result is not None:
                    validated.append(result)
        return validated

    def _validate_patents_by_specialty(
        self,
        raw_results: List[dict],
        specialty: str,
        inventor_name: str,
        fallback_url: str,
    ) -> List[PatentItem]:
        """
        For each raw SerpAPI result, ask GPT whether the patent title matches
        the researcher's specialty. Return PatentItem list for validated patents.
        """
        import os
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("[Patents] openai not installed — skipping specialty validation")
            return []

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("[Patents] OPENAI_API_KEY not set — skipping specialty validation")
            return []

        client = OpenAI(api_key=api_key)
        validated: List[PatentItem] = []

        def _check_one(r: dict) -> Optional[PatentItem]:
            title = (r.get("title") or "").strip() or "(no title)"
            link = (r.get("link") or "").strip()
            if not link:
                pub = r.get("publication_number") or r.get("patent_id")
                link = f"https://patents.google.com/patent/{pub}/en" if pub else fallback_url

            assignees_raw = r.get("assignees") or []
            if isinstance(assignees_raw, list):
                assignee_str = ", ".join(
                    a.get("name", a) if isinstance(a, dict) else str(a)
                    for a in assignees_raw
                )
            else:
                assignee_str = str(assignees_raw)
            snippet = (r.get("snippet") or "").strip()

            try:
                context_parts = [f"Patent title: {title}"]
                if assignee_str:
                    context_parts.append(f"Assignee: {assignee_str}")
                if snippet:
                    context_parts.append(f"Abstract: {snippet[:300]}")

                prompt = (
                    f"Researcher specialty: {specialty}\n"
                    f"{chr(10).join(context_parts)}\n\n"
                    f"Could this patent plausibly belong to a researcher with this specialty? "
                    f"Answer only 'yes' or 'no'."
                )
                response = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=10,
                    temperature=0,
                )
                answer = response.choices[0].message.content.strip().lower()
                if answer.startswith("yes"):
                    logger.info(f"[Patents] GPT: KEEP '{title[:60]}' (matches specialty of '{inventor_name}')")
                    item = PatentItem(
                        title=title, link=link,
                        patent_id=self._extract_id_from_url(link),
                        claims_top3=[], cited_by=None, cited_assignees=[],
                        citing_assignees=[], co_inventors=[], inventors=[],
                    )
                    self._enrich_patent(item, inventor_name)
                    return item
                else:
                    logger.info(f"[Patents] GPT: REJECT '{title[:60]}' (does not match specialty of '{inventor_name}')")
                    return None
            except Exception as e:
                logger.warning(f"[Patents] GPT specialty check failed for '{title[:60]}': {e}")
                return None

        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed_gpt
        with ThreadPoolExecutor(max_workers=5) as _pool:
            futures = {_pool.submit(_check_one, r): r for r in raw_results}
            for fut in _as_completed_gpt(futures):
                result = fut.result()
                if result is not None:
                    validated.append(result)

        return validated

    def _extract_id_from_url(self, link: str) -> Optional[str]:
        """Extract patent ID from URL."""
        if not link:
            return None
        try:
            path = urlparse(link).path or ""
        except Exception:
            path = link

        m = re.search(r"/patent/([^/]+)/", path)
        if not m:
            m = re.search(r"patent/([^/]+)/", link)
        if m:
            return f"patent/{m.group(1).strip()}/en"
        return None

    @staticmethod
    def _extract_middle_initial(name: str) -> Optional[str]:
        """
        Return the middle initial (uppercase) if the name has exactly one.

        "Gregory W. Albers" → "W"
        "Sean I. Savitz"    → "I"
        "John Smith"        → None  (no middle)
        "John William Smith"→ None  (full middle name, not just an initial)
        """
        parts = name.strip().split()
        if len(parts) != 3:
            return None
        middle = parts[1].rstrip(".")
        if len(middle) == 1 and middle.isalpha():
            return middle.upper()
        return None

    @staticmethod
    def _normalize_inventor_list(inv_field) -> List[str]:
        """
        Normalize the inventors field from a SerpAPI organic result to a list of strings.

        Handles:
        - None / missing                       → []
        - "Gregory W. Albers"  (str)           → ["Gregory W. Albers"]
        - ["Gregory W. Albers", "John Smith"]  → as-is
        - [{"name": "Gregory W. Albers"}, ...]  → extracts "name" key
        """
        if not inv_field:
            return []
        if isinstance(inv_field, str):
            return [inv_field]
        if isinstance(inv_field, list):
            out: List[str] = []
            for item in inv_field:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    name = (item.get("name") or item.get("display_name") or "").strip()
                    if name:
                        out.append(name)
            return out
        return []

    @staticmethod
    def _inventor_matches_middle_initial(inventor_str: str, first_last: str, initial: str) -> bool:
        """
        True if `inventor_str` matches the first+last name of `first_last` AND has
        a middle name/initial starting with `initial`.

        Used for post-enrichment filtering of fallback search results.

        Examples:
          "Gregory William Albers", "Gregory Albers", "W" → True  (full middle name)
          "Gregory W. Albers",      "Gregory Albers", "W" → True  (middle initial)
          "Gregory Albers",         "Gregory Albers", "W" → False (no middle → homonyme)
          "Gregory J. Albers",      "Gregory Albers", "W" → False (wrong initial)
        """
        raw = strip_accents_basic(str(inventor_str)).strip()
        parts = raw.split()
        fl = first_last.strip().lower().split()
        if len(parts) < 3 or len(fl) != 2:
            return False
        # Match first and last (case-insensitive, strip trailing dots)
        if parts[0].lower().rstrip(".") != fl[0].rstrip("."):
            return False
        if parts[-1].lower() != fl[-1]:
            return False
        middle = parts[1].rstrip(".")
        return bool(middle) and middle[0].upper() == initial.upper()

    @staticmethod
    def _inventor_has_matching_initial(inventor_str: str, initial: str) -> bool:
        """
        Return True if the inventor name has a middle name/initial starting with `initial`.

        Handles:
        - "Gregory William ALBERS"  → middle="William" → "W" ✓
        - "Gregory W. Albers"       → middle="W."      → "W" ✓
        - "Gregory Albers"          → no middle        → False
        """
        parts = strip_accents_basic(str(inventor_str)).strip().split()
        if len(parts) < 3:
            return False
        middle = parts[1].rstrip(".")
        return bool(middle) and middle[0].upper() == initial.upper()

    @staticmethod
    def _dedup(xs: List[str]) -> List[str]:
        """Deduplicate list preserving order."""
        seen = set()
        out = []
        for x in xs:
            x = (x or "").strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    @staticmethod
    def normalize_id(patent_id: str) -> str:
        """
        Normalize patent ID to document number.

        Args:
            patent_id: Any format patent ID.

        Returns:
            Just the document number (e.g., "US10000000").
        """
        if not patent_id:
            return patent_id
        m = re.search(r"patent/([^/]+)/", patent_id)
        return m.group(1) if m else patent_id


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def fetch_patents_data(inventor_name: str, api_key: str) -> PatentsData:
    """Deprecated: Use PatentsClient.fetch_patents_data()."""
    return PatentsClient(api_key=api_key).fetch_patents_data(inventor_name)
