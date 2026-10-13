"""
CMS Open Payments API client.

Provides access to the U.S. federal database of payments and transfers of value
from pharmaceutical and medical device companies to physicians and teaching hospitals.

Open Payments is a federally mandated transparency program under the Sunshine Act
(Section 6002 of the Affordable Care Act). Data is public and free — no API key needed.

Source: https://openpaymentsdata.cms.gov
API docs: https://openpaymentsdata.cms.gov/about/api

## How this client works

Two-step approach (mirrors how the CMS website itself queries data):

  Step 1 — Unified search:
      GET /api/search/unified_endpoint?q=FIRSTNAME+LASTNAME
      → returns covered_recipient_profile_id  (~0.4 s, fast)
      → returns empty for non-US recipients (no wasted queries)

  Step 2 — Payment query by profile_id:
      GET /api/1/datastore/query/{year_datastore_uuid}/0
          ?conditions[0][property]=covered_recipient_profile_id
          &conditions[0][value]={profile_id}
      → returns all payments for that person in that year  (~1–2 s)

The year-specific datastore UUIDs are extracted from the CMS website's own JS bundle
(source of truth). They are stable identifiers tied to each program year's published
dataset and do not change after publication.
"""

import requests
from concurrent.futures import ThreadPoolExecutor as _YearTPE, as_completed as _year_as_completed
from dataclasses import dataclass
from typing import List, Set, Optional, Dict, Tuple

from src.logger import logger


# ---------------------------------------------------------------------------
# Datastore UUIDs (extracted from CMS JS bundle — stable per program year)
# ---------------------------------------------------------------------------
PAYMENT_DATASTORES: Dict[int, str] = {
    2024: "e6b17c6a-2534-4207-a4a1-6746a14911ff",
    2023: "fb3a65aa-c901-4a38-a813-b04b00dfa2a9",
    2022: "df01c2f8-dc1f-4e79-96cb-8208beaf143c",
    2021: "0380bbeb-aea1-58b6-b708-829f92a48202",
}

PHYSICIAN_PROFILE_DATASTORE = "6ed6ae76-2999-49da-b0b2-d7df150ac754"

DEFAULT_YEAR = max(PAYMENT_DATASTORES.keys())  # 2024
ALL_YEARS = sorted(PAYMENT_DATASTORES.keys(), reverse=True)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OpenPaymentsRecord:
    """
    A payment record from CMS Open Payments (U.S. Sunshine Act).

    Represents a financial transfer from a company to a covered recipient
    (physician, non-physician practitioner, or teaching hospital).
    """
    record_id: str
    date: str
    company_name: str
    company_state: str
    amount_usd: float
    nature_of_payment: str
    recipient_first_name: str
    recipient_last_name: str
    recipient_type: str
    recipient_specialty: str
    recipient_city: str
    recipient_state: str
    program_year: int

    @property
    def full_recipient_name(self) -> str:
        return f"{self.recipient_first_name} {self.recipient_last_name}"

    def __repr__(self) -> str:
        return (
            f"<OpenPaymentsRecord({self.company_name} → {self.full_recipient_name}: "
            f"${self.amount_usd:,.2f} for {self.nature_of_payment}, {self.program_year})>"
        )


@dataclass
class OpenPaymentsSearchResult:
    """Results from a CMS Open Payments search (may span multiple years)."""
    total_records: int
    total_amount_usd: float
    companies_found: Set[str]
    records: List[OpenPaymentsRecord]
    years_queried: List[int]
    profile_id: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"<OpenPaymentsSearchResult("
            f"total={self.total_records}, "
            f"total_amount=${self.total_amount_usd:,.2f}, "
            f"companies={len(self.companies_found)}, "
            f"years={self.years_queried})>"
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class OpenPaymentsClient:
    """
    Client for the CMS Open Payments API (U.S. Sunshine Act).

    Free, public REST API — no authentication required.

    Usage:
        client = OpenPaymentsClient()
        result = client.search_by_name("John", "Smith")
        # result.records contains all payments found across all available years
        # result.companies_found is the set of paying company names

    Thread safety:
        Create one instance per thread when using ThreadPoolExecutor.
    """

    BASE_URL = "https://openpaymentsdata.cms.gov"

    def __init__(self, timeout: float = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Scholarmap/1.0 (Research Tool)",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_by_name(
        self,
        first_name: str,
        last_name: str,
        min_amount_usd: float = 0.0,
        years: Optional[List[int]] = None,
    ) -> OpenPaymentsSearchResult:
        """
        Search for all payments to a given recipient across program years.

        Step 1: unified search to resolve covered_recipient_profile_id.
        Step 2: query payment datastore(s) by profile_id.

        Args:
            first_name: First name (case-insensitive).
            last_name: Last name (case-insensitive).
            min_amount_usd: Minimum payment amount to return (default: 0 = all payments).
            years: List of program years to query. Defaults to ALL_YEARS.

        Returns:
            OpenPaymentsSearchResult — empty result if recipient not found in CMS.
        """
        _years = years if years is not None else ALL_YEARS
        empty = OpenPaymentsSearchResult(
            total_records=0, total_amount_usd=0.0,
            companies_found=set(), records=[], years_queried=_years,
        )

        # Step 1: resolve profile_id via unified search
        profile_id = self._resolve_profile_id(first_name, last_name)
        if not profile_id:
            logger.debug(f"[OP] No CMS profile found: {first_name} {last_name}")
            return empty

        logger.info(f"[OP] Profile found: {first_name} {last_name} → profile_id={profile_id}")
        empty.profile_id = profile_id

        # Step 2: query all years in parallel (one thread per year)
        all_records: List[OpenPaymentsRecord] = []

        def _fetch_year(year: int) -> List[OpenPaymentsRecord]:
            uuid = PAYMENT_DATASTORES.get(year)
            if not uuid:
                return []
            return self._query_payments_by_profile(
                profile_id=profile_id,
                year=year,
                datastore_uuid=uuid,
                min_amount_usd=min_amount_usd,
            )

        with _YearTPE(max_workers=len(_years)) as year_pool:
            year_futures = {year_pool.submit(_fetch_year, y): y for y in _years}
            for future in _year_as_completed(year_futures):
                try:
                    all_records.extend(future.result())
                except Exception as _ye:
                    logger.debug(f"[OP] Year query error: {_ye}")

        companies: Set[str] = {r.company_name for r in all_records if r.company_name}
        total_amount = sum(r.amount_usd for r in all_records)

        logger.info(
            f"[OP] {first_name} {last_name}: {len(all_records)} payments across "
            f"{len(_years)} year(s), ${total_amount:,.2f}, "
            f"{len(companies)} company(ies)"
        )

        return OpenPaymentsSearchResult(
            total_records=len(all_records),
            total_amount_usd=total_amount,
            companies_found=companies,
            records=all_records,
            years_queried=_years,
            profile_id=profile_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_profile_id(self, first_name: str, last_name: str) -> Optional[str]:
        """
        Call unified search to find the CMS profile ID for a given name.

        Returns None if no match found or on error.
        """
        query = f"{first_name.strip()} {last_name.strip()}"
        try:
            r = self.session.get(
                f"{self.BASE_URL}/api/search/unified_endpoint",
                params={"q": query},
                timeout=self.timeout,
            )
            r.raise_for_status()
            results = r.json().get("search_results", [])

            # Match first+last name.
            # CMS stores middle initials WITHOUT trailing period (e.g. "SEAN I" not "SEAN I.").
            # Normalize both sides by stripping all periods so "Sean I." matches "SEAN I".
            #
            # Strategy:
            #   Pass 1 — normalized match (handles "Sean I." → "SEAN I", "Sean" → "SEAN")
            #   Pass 2 — first-token fallback, but only if unambiguous
            #             (CMS may omit the middle initial entirely; reject if ambiguous)
            def _norm(s: str) -> str:
                """Strip periods and collapse spaces for CMS name comparison."""
                return s.replace(".", "").upper().strip()

            first_norm = _norm(first_name)        # "Sean I." → "SEAN I"
            first_token_norm = first_norm.split()[0]  # "SEAN I" → "SEAN"
            last_up = last_name.strip().upper()

            # Pass 1: normalized match (period-insensitive)
            for hit in results:
                hit_first = _norm(hit.get("sort_first_name") or "")
                hit_last = (hit.get("sort_last_name") or "").upper()
                if hit_first == first_norm and hit_last == last_up:
                    return str(hit["covered_recipient_profile_id"])

            # Pass 2: first-token fallback for cases where CMS omits the middle initial
            if first_token_norm != first_norm:
                fallback_hits = [
                    hit for hit in results
                    if (hit.get("sort_last_name") or "").upper() == last_up
                    and _norm(hit.get("sort_first_name") or "") == first_token_norm
                ]
                if len(fallback_hits) == 1:
                    logger.debug(
                        f"[OP] First-token fallback matched: "
                        f"{first_name} {last_name} → {first_token_norm} {last_up}"
                    )
                    return str(fallback_hits[0]["covered_recipient_profile_id"])
                elif len(fallback_hits) > 1:
                    logger.debug(
                        f"[OP] Ambiguous first-token fallback for {first_name} {last_name} "
                        f"({len(fallback_hits)} hits) — skipping"
                    )

            return None

        except Exception as e:
            logger.debug(f"[OP] Unified search error for '{query}': {e}")
            return None

    def _query_payments_by_profile(
        self,
        profile_id: str,
        year: int,
        datastore_uuid: str,
        min_amount_usd: float = 0.0,
        max_results: int = 500,
    ) -> List[OpenPaymentsRecord]:
        """
        Query the payments datastore for a specific profile_id and year.

        Returns list of OpenPaymentsRecord (empty list on error or no results).
        """
        params: Dict = {
            "conditions[0][property]": "covered_recipient_profile_id",
            "conditions[0][value]": profile_id,
            "conditions[0][operator]": "=",
            "limit": max_results,
            "sort": "total_amount_of_payment_usdollars",
            "sort_order": "DESC",
        }
        if min_amount_usd > 0:
            params["conditions[1][property]"] = "total_amount_of_payment_usdollars"
            params["conditions[1][value]"] = str(int(min_amount_usd))
            params["conditions[1][operator]"] = ">"

        url = f"{self.BASE_URL}/api/1/datastore/query/{datastore_uuid}/0"

        try:
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            rows = r.json().get("results", [])

            records = []
            for row in rows:
                amount = float(row.get("total_amount_of_payment_usdollars") or 0)
                company = (
                    row.get("applicable_manufacturer_or_applicable_gpo_making_payment_name", "")
                    or row.get("submitting_applicable_manufacturer_or_applicable_gpo_name", "")
                    or ""
                )
                records.append(OpenPaymentsRecord(
                    record_id=str(row.get("record_id", "")),
                    date=(row.get("date_of_payment") or "")[:10],
                    company_name=company,
                    company_state=row.get(
                        "applicable_manufacturer_or_applicable_gpo_making_payment_state", ""
                    ) or "",
                    amount_usd=amount,
                    nature_of_payment=row.get(
                        "nature_of_payment_or_transfer_of_value", ""
                    ) or "",
                    recipient_first_name=row.get("covered_recipient_first_name", "") or "",
                    recipient_last_name=row.get("covered_recipient_last_name", "") or "",
                    recipient_type=row.get("covered_recipient_type", "") or "",
                    recipient_specialty=(
                        row.get("covered_recipient_specialty_1")
                        or row.get("covered_recipient_specialty_2")
                        or ""
                    ),
                    recipient_city=row.get("recipient_city", "") or "",
                    recipient_state=row.get("recipient_state", "") or "",
                    program_year=year,
                ))

            if records:
                logger.debug(f"[OP]   {year}: {len(records)} payment(s)")
            return records

        except Exception as e:
            logger.debug(f"[OP] Payment query error ({year}): {e}")
            return []
