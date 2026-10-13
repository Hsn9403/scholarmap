#!/usr/bin/env python3
"""
EU Cordis API client for fetching European research project data.

This module provides a client for the EU Cordis API, which contains
information about EU-funded research projects (FP7, H2020, Horizon Europe).

API Documentation: https://cordis.europa.eu/datalab/
No API key required.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests

from src.logger import logger, log_api_call, log_error
from src.exceptions import APIError


class CordisClient:
    """
    Client for interacting with EU Cordis API.

    This client fetches European research project information including:
    - Project participants (universities, research centers, companies)
    - Project details (title, objective, funding)
    - Participant roles and countries

    No API key required.

    Attributes:
        base_url: Base URL for EU Cordis API.
        session: Requests session for connection pooling.

    Example:
        >>> client = CordisClient()
        >>> projects = client.search_projects_by_person("John Doe")
        >>> corporates = client.get_industry_partners_for_person("John Doe")
    """

    BASE_URL = "https://cordis.europa.eu/api"

    # Keywords to identify corporate entities vs academic/government
    CORPORATE_KEYWORDS = [
        r'\binc\b', r'\bincorporated\b', r'\bcorp\b', r'\bcorporation\b',
        r'\bltd\b', r'\blimited\b', r'\bgmbh\b', r'\bag\b', r'\bs\.a\b',
        r'\bllc\b', r'\bplc\b', r'\bsa\b', r'\bsas\b', r'\bsrl\b',
        r'\bco\b', r'\bcompany\b', r'\bgroup\b',
        r'\btechnologies\b', r'\bsystems\b', r'\bsolutions\b',
        r'\bengineering\b', r'\bindustries\b', r'\bmanufacturing\b'
    ]

    ACADEMIC_KEYWORDS = [
        r'\buniversity\b', r'\buniversité\b', r'\buniversität\b', r'\buniversidad\b',
        r'\buniversita\b', r'\bcollege\b', r'\binstitute\b', r'\binstitut\b',
        r'\bhospital\b', r'\bclinic\b', r'\bmedical center\b',
        r'\bschool\b', r'\bacademy\b', r'\backademie\b', r'\bécole\b',
        r'\bfaculty\b', r'\bdepartment\b', r'\blaboratory\b', r'\blaboratoire\b',
        r'\bresearch center\b', r'\bcentre de recherche\b', r'\bforschung\b'
    ]

    GOVERNMENT_KEYWORDS = [
        r'\bnational\b', r'\bgovernment\b', r'\bministr\b', r'\bpublic\b',
        r'\bstate\b', r'\bfederal\b', r'\bagency\b', r'\bcommission\b',
        r'\bcouncil\b', r'\bauthority\b', r'\badministration\b'
    ]

    def __init__(self):
        """Initialize the Cordis client."""
        self.base_url = self.BASE_URL
        self.session = requests.Session()

        # Simple in-memory cache
        self._cache: Dict[str, Any] = {}

        # Set user agent
        self.session.headers["User-Agent"] = "Scholarmap/1.0 (Academic Research)"

        logger.debug("CordisClient initialized (no API key required)")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request to Cordis API.

        Args:
            endpoint: API endpoint (e.g., "/projects").
            params: Query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"

        if params is None:
            params = {}

        try:
            log_api_call("cordis", {"endpoint": endpoint, "params": params})
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(
                    "Cordis API rate limit exceeded (429). "
                    "Will continue without Cordis data."
                )
                raise APIError("Cordis API rate limit exceeded.") from e
            log_error(e, f"Cordis API HTTP error: {e.response.status_code}")
            raise APIError(f"Cordis API request failed: {e}") from e
        except requests.RequestException as e:
            log_error(e, "Cordis API request failed")
            raise APIError(f"Failed to connect to Cordis API: {e}") from e
        except ValueError as e:
            log_error(e, "Invalid JSON response from Cordis")
            raise APIError("Invalid response from Cordis API") from e

    def _is_corporate(self, organization_name: str) -> bool:
        """
        Determine if an organization is a corporate entity.

        Args:
            organization_name: Name of the organization.

        Returns:
            True if likely corporate, False if academic/government.
        """
        if not organization_name:
            return False

        org_lower = organization_name.lower()

        # Exclude academic/research institutions
        for pattern in self.ACADEMIC_KEYWORDS:
            if re.search(pattern, org_lower):
                return False

        # Exclude government entities
        for pattern in self.GOVERNMENT_KEYWORDS:
            if re.search(pattern, org_lower):
                return False

        # Check for corporate indicators
        for pattern in self.CORPORATE_KEYWORDS:
            if re.search(pattern, org_lower):
                return True

        # Additional heuristic: If all uppercase and short (< 10 chars), likely acronym
        # which could be corporate (e.g., "AIRBUS", "SAFRAN")
        if organization_name.isupper() and len(organization_name) < 10:
            return True

        return False

    def search_projects_by_person(
        self,
        person_name: str,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search for EU projects involving a specific person.

        Note: Cordis API doesn't have direct person search. This method
        searches for projects using the person's name in various fields
        (project metadata, participants).

        Args:
            person_name: Name of the person to search for.
            max_results: Maximum number of results to return.

        Returns:
            List of project dictionaries.
        """
        # Check cache
        cache_key = f"person:{person_name.lower()}"
        if cache_key in self._cache:
            logger.debug(f"Using cached result for person: {person_name}")
            return self._cache[cache_key]

        try:
            # Search in project metadata
            # Cordis API uses different endpoints for different programmes
            # We'll search across H2020 and Horizon Europe
            endpoint = "/projects"
            params = {
                "q": person_name,
                "format": "json",
                "pageSize": max_results
            }

            logger.debug(f"Searching Cordis for person: {person_name}")
            result = self._make_request(endpoint, params)

            # Extract projects
            projects = result.get("projects", [])
            if not projects:
                logger.info(f"No Cordis projects found for: {person_name}")
                self._cache[cache_key] = []
                return []

            logger.info(f"Found {len(projects)} Cordis projects for: {person_name}")

            # Cache result
            self._cache[cache_key] = projects
            return projects

        except APIError:
            raise
        except Exception as e:
            logger.warning(f"Error searching Cordis for '{person_name}': {e}")
            return []

    def get_project_participants(
        self,
        project_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all participants (organizations) for a specific project.

        Args:
            project_id: Cordis project ID (e.g., "101234567").

        Returns:
            List of participant dictionaries with name, country, role, etc.
        """
        try:
            endpoint = f"/projects/{project_id}/participants"
            params = {"format": "json"}

            result = self._make_request(endpoint, params)
            participants = result.get("participants", [])

            logger.debug(f"Found {len(participants)} participants for project {project_id}")
            return participants

        except APIError:
            logger.warning(f"Could not fetch participants for project {project_id}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching participants for project {project_id}: {e}")
            return []

    def get_industry_partners_for_person(
        self,
        person_name: str,
        max_projects: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all industry partners for a given person via their EU projects.

        This method:
        1. Finds all EU projects where the person is involved
        2. Extracts all participants from those projects
        3. Filters to keep only corporate entities

        Args:
            person_name: Name of the person.
            max_projects: Maximum number of projects to search.

        Returns:
            List of dicts with industry partner information:
            [
                {
                    "organization": "Airbus Defence and Space",
                    "projects": ["101234567", "101234568"],
                    "project_titles": ["Project A", "Project B"],
                    "country": "FR",
                    "role": "Participant"
                },
                ...
            ]
        """
        # Get all projects for this person
        projects = self.search_projects_by_person(person_name, max_results=max_projects)

        if not projects:
            return []

        # Extract industry partners from all projects
        partner_map: Dict[str, Dict[str, Any]] = {}

        for project in projects[:max_projects]:
            project_id = project.get("id") or project.get("rcn")
            project_title = project.get("title", "Unknown")

            if not project_id:
                continue

            # Get participants for this project
            participants = self.get_project_participants(project_id)

            for participant in participants:
                org_name = participant.get("name") or participant.get("shortName")
                country = participant.get("country", "Unknown")
                role = participant.get("activityType", "Participant")

                if not org_name:
                    continue

                # Only keep corporate entities
                if self._is_corporate(org_name):
                    if org_name not in partner_map:
                        partner_map[org_name] = {
                            "organization": org_name,
                            "projects": [],
                            "project_titles": [],
                            "countries": set(),
                            "roles": set()
                        }

                    partner_map[org_name]["projects"].append(project_id)
                    partner_map[org_name]["project_titles"].append(project_title)
                    partner_map[org_name]["countries"].add(country)
                    partner_map[org_name]["roles"].add(role)

            # Rate limiting
            time.sleep(0.5)

        # Convert to list and clean up
        result = []
        for partner_data in partner_map.values():
            result.append({
                "organization": partner_data["organization"],
                "projects": partner_data["projects"],
                "project_count": len(partner_data["projects"]),
                "project_titles": partner_data["project_titles"][:5],  # Keep first 5
                "countries": sorted(list(partner_data["countries"])),
                "roles": sorted(list(partner_data["roles"]))
            })

        # Sort by project count
        result.sort(key=lambda x: x["project_count"], reverse=True)

        logger.info(
            f"Found {len(result)} industry partners for '{person_name}' via Cordis"
        )

        return result
