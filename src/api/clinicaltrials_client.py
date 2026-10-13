#!/usr/bin/env python3
"""
ClinicalTrials.gov API client for fetching clinical trial sponsor information.

This module provides a client for the ClinicalTrials.gov API v2,
which returns information about clinical trials including sponsors and investigators.

API Documentation: https://clinicaltrials.gov/data-api/api
Rate Limits: ~50 requests per minute (no API key required)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests

from src.logger import logger, log_api_call, log_error
from src.exceptions import APIError


class ClinicalTrialsClient:
    """
    Client for interacting with ClinicalTrials.gov API v2.

    This client fetches clinical trial information including:
    - Trial sponsors (lead sponsor and collaborators)
    - Principal Investigators and their affiliations
    - Trial details (phase, status, etc.)

    No API key required.

    Attributes:
        base_url: Base URL for ClinicalTrials.gov API v2.
        session: Requests session for connection pooling.

    Example:
        >>> client = ClinicalTrialsClient()
        >>> sponsors = client.get_industry_sponsors_for_researcher("Jane Smith")
        >>> print(f"Found {len(sponsors)} industry sponsors")
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2"

    # Keywords to identify industry/corporate sponsors vs academic/government
    ACADEMIC_KEYWORDS = {
        "university", "université", "universität", "universidad",
        "college", "institute", "hospital", "clinic", "medical center",
        "health system", "akademie", "école", "school"
    }

    GOVERNMENT_KEYWORDS = {
        "nih", "national institutes", "national institute",
        "national cancer", "national heart", "nci", "nhlbi",
        "centers for disease control", "cdc", "fda",
        "department of", "ministry of", "ministère",
        "government", "gouvernement", "public health"
    }

    def __init__(self):
        """Initialize the ClinicalTrials.gov client."""
        self.base_url = self.BASE_URL
        self.session = requests.Session()

        # Simple in-memory cache to avoid duplicate requests
        self._cache: Dict[str, Any] = {}

        # Set user agent
        self.session.headers["User-Agent"] = "Scholarmap/1.0 (Academic Research)"

        logger.debug("ClinicalTrialsClient initialized (no API key required)")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to ClinicalTrials.gov API.

        Args:
            endpoint: API endpoint (e.g., "/studies").
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"

        # Ensure JSON format
        if params is None:
            params = {}
        params["format"] = "json"

        try:
            log_api_call("clinicaltrials", {"endpoint": endpoint, "params": params})
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(
                    "ClinicalTrials.gov API rate limit exceeded (429). "
                    "Will continue without clinical trials data. "
                    "This is normal and not an error."
                )
                raise APIError(
                    "ClinicalTrials.gov API rate limit exceeded. "
                    "Continuing without clinical trials enrichment."
                ) from e
            log_error(e, f"ClinicalTrials.gov API HTTP error: {e.response.status_code}")
            raise APIError(f"ClinicalTrials.gov API request failed: {e}") from e
        except requests.RequestException as e:
            log_error(e, "ClinicalTrials.gov API request failed")
            raise APIError(f"Failed to connect to ClinicalTrials.gov API: {e}") from e
        except ValueError as e:
            log_error(e, "Invalid JSON response from ClinicalTrials.gov")
            raise APIError("Invalid response from ClinicalTrials.gov API") from e

    def search_studies_by_investigator(
        self,
        investigator_name: str,
        max_studies: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search for clinical trials where the given person is an investigator.

        Args:
            investigator_name: Name of the investigator to search for.
            max_studies: Maximum number of studies to retrieve (default 100).

        Returns:
            List of study dictionaries where the person is listed as investigator.

        Example:
            >>> studies = client.search_studies_by_investigator("Jane Smith")
            >>> for study in studies:
            ...     print(f"NCT: {study['nctId']}, Sponsor: {study['sponsor']}")
        """
        # Clean investigator name
        name_clean = investigator_name.strip()
        if not name_clean:
            logger.warning("Empty investigator name provided")
            return []

        # Check cache first
        cache_key = f"investigator:{name_clean.lower()}"
        if cache_key in self._cache:
            logger.debug(f"Using cached result for investigator: {name_clean}")
            return self._cache[cache_key]

        try:
            # Search using full-text query
            endpoint = "/studies"
            params = {
                "query.term": name_clean,
                "pageSize": max_studies
            }

            logger.debug(f"Searching ClinicalTrials.gov for investigator: {name_clean}")
            result = self._make_request(endpoint, params)

            # Extract studies
            studies_data = result.get("studies", [])
            if not studies_data:
                logger.info(f"No clinical trials found for investigator: {name_clean}")
                self._cache[cache_key] = []
                return []

            # Filter studies where the person is actually an investigator
            matching_studies = []
            for study_data in studies_data:
                protocol = study_data.get("protocolSection", {})

                # Get NCT ID and title
                identification = protocol.get("identificationModule", {})
                nct_id = identification.get("nctId", "Unknown")
                title = identification.get("officialTitle") or identification.get("briefTitle", "Unknown")

                # Get sponsor information
                sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
                lead_sponsor = sponsor_module.get("leadSponsor", {})
                sponsor_name = lead_sponsor.get("name", "Unknown")

                # Get collaborators
                collaborators = sponsor_module.get("collaborators", [])
                collaborator_names = [c.get("name", "") for c in collaborators]

                # Get investigators
                contacts_module = protocol.get("contactsLocationsModule", {})
                officials = contacts_module.get("overallOfficials", [])

                # Check if our investigator is in the officials list
                is_investigator = False
                investigator_role = None
                investigator_affiliation = None

                for official in officials:
                    official_name = official.get("name", "")
                    # Case-insensitive partial match
                    if name_clean.lower() in official_name.lower() or official_name.lower() in name_clean.lower():
                        is_investigator = True
                        investigator_role = official.get("role", "Unknown")
                        investigator_affiliation = official.get("affiliation", "Unknown")
                        break

                if is_investigator:
                    matching_studies.append({
                        "nctId": nct_id,
                        "title": title,
                        "sponsor": sponsor_name,
                        "collaborators": collaborator_names,
                        "investigatorRole": investigator_role,
                        "investigatorAffiliation": investigator_affiliation
                    })

            logger.info(
                f"Found {len(matching_studies)} clinical trials for {name_clean} "
                f"(out of {len(studies_data)} searched)"
            )

            # Cache the result
            self._cache[cache_key] = matching_studies
            return matching_studies

        except APIError:
            raise
        except Exception as e:
            logger.warning(f"Error searching ClinicalTrials.gov for '{name_clean}': {e}")
            return []

    def _is_industry_sponsor(self, sponsor_name: str) -> bool:
        """
        Determine if a sponsor is an industry/corporate entity vs academic/government.

        Args:
            sponsor_name: Name of the sponsor organization.

        Returns:
            True if the sponsor appears to be industry/corporate, False otherwise.

        Example:
            >>> client._is_industry_sponsor("Pfizer Inc.")
            True
            >>> client._is_industry_sponsor("Harvard Medical School")
            False
        """
        name_lower = sponsor_name.lower()

        # Check for academic keywords
        if any(keyword in name_lower for keyword in self.ACADEMIC_KEYWORDS):
            return False

        # Check for government keywords
        if any(keyword in name_lower for keyword in self.GOVERNMENT_KEYWORDS):
            return False

        # Check for common corporate suffixes
        corporate_suffixes = [
            "inc.", "inc", "corp.", "corp", "corporation",
            "ltd.", "ltd", "limited", "llc", "gmbh",
            "sa", "s.a.", "ag", "plc", "pharma", "therapeutics",
            "biosciences", "biotech", "pharmaceuticals"
        ]
        if any(suffix in name_lower for suffix in corporate_suffixes):
            return True

        # If unclear, assume it's academic/government (conservative approach)
        return False

    def get_industry_sponsors_for_researcher(
        self,
        researcher_name: str,
        max_studies: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all industry sponsors for a given researcher.

        This method:
        1. Finds all clinical trials where the researcher is an investigator
        2. Extracts sponsors from those trials
        3. Filters to keep only industry/corporate sponsors

        Args:
            researcher_name: Name of the researcher.
            max_studies: Maximum number of studies to search (default 100).

        Returns:
            List of dicts with sponsor information:
            [
                {
                    "sponsor": "Pfizer Inc.",
                    "trials": ["NCT12345", "NCT67890"],
                    "roles": ["Principal Investigator", "Study Chair"]
                },
                ...
            ]

        Example:
            >>> sponsors = client.get_industry_sponsors_for_researcher("John Doe")
            >>> for s in sponsors:
            ...     print(f"{s['sponsor']}: {len(s['trials'])} trials")
        """
        # Get all studies for this researcher
        studies = self.search_studies_by_investigator(researcher_name, max_studies)

        if not studies:
            return []

        # Aggregate sponsors
        sponsor_map: Dict[str, Dict[str, Any]] = {}

        for study in studies:
            sponsor_name = study["sponsor"]
            nct_id = study["nctId"]
            role = study["investigatorRole"]

            # Only keep industry sponsors
            if self._is_industry_sponsor(sponsor_name):
                if sponsor_name not in sponsor_map:
                    sponsor_map[sponsor_name] = {
                        "sponsor": sponsor_name,
                        "trials": [],
                        "roles": set(),
                        "trial_details": []
                    }

                sponsor_map[sponsor_name]["trials"].append(nct_id)
                sponsor_map[sponsor_name]["roles"].add(role)
                sponsor_map[sponsor_name]["trial_details"].append({
                    "nctId": nct_id,
                    "title": study["title"],
                    "role": role,
                    "affiliation": study["investigatorAffiliation"]
                })

        # Convert to list and clean up
        result = []
        for sponsor_data in sponsor_map.values():
            result.append({
                "sponsor": sponsor_data["sponsor"],
                "trials": sponsor_data["trials"],
                "roles": sorted(list(sponsor_data["roles"])),
                "trial_count": len(sponsor_data["trials"]),
                "trial_details": sponsor_data["trial_details"]
            })

        # Sort by trial count (most trials first)
        result.sort(key=lambda x: x["trial_count"], reverse=True)

        logger.info(
            f"Found {len(result)} industry sponsors for researcher '{researcher_name}'"
        )

        return result
