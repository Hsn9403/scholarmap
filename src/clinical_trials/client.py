#!/usr/bin/env python3
"""
ClinicalTrials.gov API client for detecting researcher-corporate links.

This module provides a strict, evidence-based approach to identifying
collaborations between academic researchers and corporate entities through
clinical trial sponsorship and involvement.

METHODOLOGY:
    A valid link requires:
    1. Researcher is listed as Principal Investigator (PI)
    2. Any organization in Lead Sponsor or Study Collaborators is recorded
    3. Corporate/academic filtering is done downstream (ROR client)

Example:
    >>> from src.clinical_trials.client import ClinicalTrialsClient
    >>> client = ClinicalTrialsClient()
    >>> results = client.find_corporate_links("Edgar Duval")
    >>> for link in results:
    ...     print(f"{link.researcher} → {link.corporate} (NCT{link.nct_id})")
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

import requests

from src.logger import logger


@dataclass
class CorporateLink:
    """Evidence of a researcher-corporate collaboration via clinical trial."""

    researcher: str
    corporate: str
    role: str  # e.g., "Principal Investigator"
    nct_id: str
    study_title: str
    detection_field: str  # Where corporate was found (Sponsor/Intervention/etc)
    detection_value: str  # Exact value from that field
    study_url: str
    confidence: float = 0.95  # High confidence for explicit matches

    def __str__(self) -> str:
        return (
            f"{self.researcher} → {self.corporate}\n"
            f"  Role: {self.role}\n"
            f"  Study: {self.study_title}\n"
            f"  NCT ID: {self.nct_id}\n"
            f"  Found in: {self.detection_field} = '{self.detection_value}'\n"
            f"  URL: {self.study_url}\n"
            f"  Confidence: {self.confidence}"
        )


@dataclass
class ClinicalTrialsSearchResult:
    """Summary of a clinical trials search."""

    researcher_name: str
    total_studies_found: int
    studies_as_pi: int
    corporate_links: List[CorporateLink] = field(default_factory=list)
    corporates_found: Set[str] = field(default_factory=set)

    def __str__(self) -> str:
        return (
            f"Clinical Trials Search: {self.researcher_name}\n"
            f"  Total studies: {self.total_studies_found}\n"
            f"  As Principal Investigator: {self.studies_as_pi}\n"
            f"  Corporate links: {len(self.corporate_links)}\n"
            f"  Unique corporates: {len(self.corporates_found)}"
        )


class ClinicalTrialsClient:
    """
    Client for ClinicalTrials.gov API v2.

    Implements strict methodology for detecting researcher-corporate links
    through clinical trial sponsorship and involvement.

    Attributes:
        base_url: ClinicalTrials.gov API v2 base URL
        timeout: Request timeout in seconds
        rate_limit_delay: Delay between requests (seconds)
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2"

    def __init__(
        self,
        timeout: int = 10,
        rate_limit_delay: float = 0.5,
    ):
        """
        Initialize ClinicalTrials client.

        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between API requests
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        logger.info("ClinicalTrialsClient initialized")

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for robust matching.

        - Convert to lowercase
        - Remove accents
        - Remove medical titles (MD, PhD, Dr, Prof)
        - Normalize whitespace

        Args:
            text: Input text

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Normalize unicode (decompose accents)
        text = unicodedata.normalize('NFD', text)
        # Remove accent marks
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        # Lowercase and strip
        text = text.lower().strip()

        # Remove medical/academic titles
        titles = [
            r'\bmd\b', r'\bphd\b', r'\bmsc\b', r'\bmba\b',
            r'\bdr\.?\b', r'\bprof\.?\b', r'\bprof\b',
            r'\bmr\b', r'\bmrs\b', r'\bms\b'
        ]
        for title in titles:
            text = re.sub(title, '', text)

        # Remove punctuation except hyphens in names
        text = re.sub(r'[,;.]', ' ', text)

        # Normalize whitespace
        text = ' '.join(text.split())

        return text

    def _matches_researcher(self, pi_name: str, target_name: str) -> bool:
        """
        Check if PI name matches target researcher name.

        Handles:
        - Case insensitivity
        - Accents
        - Name order variations (Last, First vs First Last)

        Args:
            pi_name: Name from clinical trial
            target_name: Researcher name we're searching for

        Returns:
            True if names match
        """
        pi_norm = self._normalize_text(pi_name)
        target_norm = self._normalize_text(target_name)

        # Direct match
        if pi_norm == target_norm:
            return True

        # Check if all words from target appear in PI name
        target_words = set(target_norm.split())
        pi_words = set(pi_norm.split())

        if target_words.issubset(pi_words):
            return True

        # Check reverse order (Last, First → First Last)
        if ',' in pi_norm:
            parts = [p.strip() for p in pi_norm.split(',')]
            reversed_name = ' '.join(reversed(parts))
            if reversed_name == target_norm:
                return True

        return False

    def find_studies_by_investigator(
        self,
        investigator_name: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search for clinical trials where person is listed as investigator.

        Uses ClinicalTrials.gov API v2 query syntax.

        Args:
            investigator_name: Name of investigator to search
            max_results: Maximum number of results to return

        Returns:
            List of study records
        """
        logger.info(f"Searching ClinicalTrials for investigator: {investigator_name}")

        # Query parameters
        # Note: API v2 doesn't have investigator-specific search
        # Use full-text search and filter manually
        params = {
            "query.term": investigator_name,
            "pageSize": min(max_results, 100),
            "format": "json"
        }

        try:
            response = requests.get(
                f"{self.BASE_URL}/studies",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            studies = data.get("studies", [])

            logger.info(f"Found {len(studies)} studies for {investigator_name}")

            time.sleep(self.rate_limit_delay)

            return studies

        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            return []

    def _extract_investigators(self, study: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract all investigators from study record.

        Args:
            study: Study record from API

        Returns:
            List of investigators with name and role
        """
        investigators = []

        # Navigate to contacts/locations module
        protocol = study.get("protocolSection", {})
        contacts_module = protocol.get("contactsLocationsModule", {})
        locations = contacts_module.get("locations", [])

        # Also check central contacts
        central_contacts = contacts_module.get("centralContacts", [])
        for contact in central_contacts:
            name = contact.get("name", "")
            role = contact.get("role", "")
            if name:
                investigators.append({"name": name, "role": role})

        # Extract from locations
        for location in locations:
            location_contacts = location.get("contacts", [])
            for contact in location_contacts:
                name = contact.get("name", "")
                role = contact.get("role", "")
                if name:
                    investigators.append({"name": name, "role": role})

        # Also check overall officials
        officials = contacts_module.get("overallOfficials", [])
        for official in officials:
            name = official.get("name", "")
            role = official.get("role", "")
            if name:
                investigators.append({"name": name, "role": role})

        return investigators

    def _is_principal_investigator(self, investigator: Dict[str, str]) -> bool:
        """
        Check if investigator has PI role.

        Args:
            investigator: Investigator record

        Returns:
            True if role indicates Principal Investigator
        """
        role = investigator.get("role", "").lower()

        pi_keywords = [
            "principal investigator",
            "principal_investigator",
            "study_director",
            "study director"
        ]

        return any(keyword in role for keyword in pi_keywords)

    def _extract_lead_sponsor(self, study: Dict[str, Any]) -> Optional[str]:
        """
        Extract lead sponsor name from study.

        Args:
            study: Study record

        Returns:
            Lead sponsor name or None
        """
        protocol = study.get("protocolSection", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        lead_sponsor = sponsor_module.get("leadSponsor", {})
        return lead_sponsor.get("name") or None

    def _extract_collaborators(self, study: Dict[str, Any]) -> List[str]:
        """
        Extract study collaborator names from sponsorCollaboratorsModule.

        Args:
            study: Study record

        Returns:
            List of collaborator names
        """
        protocol = study.get("protocolSection", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        collaborators = sponsor_module.get("collaborators", [])
        return [c.get("name") for c in collaborators if c.get("name")]

    def _extract_interventions(self, study: Dict[str, Any]) -> List[str]:
        """
        Extract intervention names/descriptions/otherNames.

        Args:
            study: Study record

        Returns:
            List of intervention descriptions
        """
        interventions = []

        protocol = study.get("protocolSection", {})
        arms_module = protocol.get("armsInterventionsModule", {})
        intervention_list = arms_module.get("interventions", [])

        for intervention in intervention_list:
            if name := intervention.get("name"):
                interventions.append(name)
            if desc := intervention.get("description"):
                interventions.append(desc)

            # IMPORTANT: Also check otherNames field!
            other_names = intervention.get("otherNames", [])
            for other_name in other_names:
                if other_name:
                    interventions.append(other_name)

        return interventions

    def find_corporate_links(
        self,
        researcher_name: str,
        max_studies: int = 100
    ) -> ClinicalTrialsSearchResult:
        """
        Find all corporate links for a researcher via clinical trials.

        STRICT METHODOLOGY:
        1. Search for studies where researcher is listed
        2. Verify researcher is Principal Investigator
        3. Check if corporate appears in: Lead Sponsor or Study Collaborators
        4. Only explicit matches are accepted

        Args:
            researcher_name: Name of researcher
            max_studies: Maximum studies to analyze

        Returns:
            Search result with all corporate links found
        """
        logger.info("=" * 80)
        logger.info(f"Clinical Trials Corporate Link Detection: {researcher_name}")
        logger.info("=" * 80)

        # Search for studies
        studies = self.find_studies_by_investigator(researcher_name, max_studies)

        result = ClinicalTrialsSearchResult(
            researcher_name=researcher_name,
            total_studies_found=len(studies),
            studies_as_pi=0
        )

        if not studies:
            logger.warning(f"No studies found for {researcher_name}")
            return result

        # Analyze each study
        for study in studies:
            nct_id = study.get("protocolSection", {}).get(
                "identificationModule", {}
            ).get("nctId", "UNKNOWN")

            title = study.get("protocolSection", {}).get(
                "identificationModule", {}
            ).get("briefTitle", "No title")

            logger.info(f"\n[Study {nct_id}] {title}")

            # Extract investigators
            investigators = self._extract_investigators(study)

            # Check if researcher is PI
            is_pi = False
            pi_role = None

            for inv in investigators:
                if self._matches_researcher(inv["name"], researcher_name):
                    if self._is_principal_investigator(inv):
                        is_pi = True
                        pi_role = inv["role"]
                        logger.info(f"  ✓ {researcher_name} is PI (role: {pi_role})")
                        result.studies_as_pi += 1
                        break
                    else:
                        logger.info(
                            f"  ✗ {researcher_name} found but NOT PI "
                            f"(role: {inv['role']})"
                        )

            if not is_pi:
                # Still log sponsors to see what we're missing
                lead = self._extract_lead_sponsor(study)
                logger.info(
                    f"  → Skipping (not PI) - Lead sponsor: {lead}"
                )
                continue

            # Extract lead sponsor and collaborators separately
            lead_sponsor = self._extract_lead_sponsor(study)
            collaborators = self._extract_collaborators(study)

            logger.info(f"  Lead sponsor: {lead_sponsor}")
            logger.info(f"  Collaborators: {collaborators}")

            # Record links for every lead sponsor and collaborator found
            study_url = f"https://clinicaltrials.gov/study/{nct_id}"

            # Lead sponsor
            if lead_sponsor:
                link = CorporateLink(
                    researcher=researcher_name,
                    corporate=lead_sponsor,
                    role=pi_role or "Principal Investigator",
                    nct_id=nct_id,
                    study_title=title,
                    detection_field="Sponsor",
                    detection_value=lead_sponsor,
                    study_url=study_url
                )
                result.corporate_links.append(link)
                result.corporates_found.add(lead_sponsor)
                logger.info(f"  ✓✓ LINK: {lead_sponsor} (Lead Sponsor)")

            # Collaborators
            for collaborator in collaborators:
                # Avoid duplicate for the same study
                if not any(
                    lk.corporate == collaborator and lk.nct_id == nct_id
                    for lk in result.corporate_links
                ):
                    link = CorporateLink(
                        researcher=researcher_name,
                        corporate=collaborator,
                        role=pi_role or "Principal Investigator",
                        nct_id=nct_id,
                        study_title=title,
                        detection_field="Collaborateur",
                        detection_value=collaborator,
                        study_url=study_url
                    )
                    result.corporate_links.append(link)
                    result.corporates_found.add(collaborator)
                    logger.info(f"  ✓✓ LINK: {collaborator} (Collaborateur)")

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(str(result))

        if result.corporate_links:
            logger.info("\nDETAILED LINKS:")
            for i, link in enumerate(result.corporate_links, 1):
                logger.info(f"\n[{i}] {link}")
        else:
            logger.info("\n✗ No corporate links found")

        return result

    async def find_corporate_links_async(
        self,
        session: "httpx.AsyncClient",
        researcher_name: str,
        max_studies: int = 100,
    ) -> "ClinicalTrialsSearchResult":
        """Async version — fetches studies via httpx, processing logic unchanged."""
        import httpx
        params = {
            "query.term": researcher_name,
            "pageSize": min(max_studies, 100),
            "format": "json"
        }
        try:
            response = await session.get(
                f"{self.BASE_URL}/studies", params=params, timeout=self.timeout
            )
            response.raise_for_status()
            studies = response.json().get("studies", [])
            logger.info(f"[CT async] {researcher_name}: {len(studies)} studies found")
        except Exception as e:
            logger.warning(f"[CT async] {researcher_name}: {e}")
            studies = []

        # Processing is in-memory — reuse sync logic directly
        result = ClinicalTrialsSearchResult(
            researcher_name=researcher_name,
            total_studies_found=len(studies),
            studies_as_pi=0
        )
        for study in studies:
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "UNKNOWN")
            title = study.get("protocolSection", {}).get("identificationModule", {}).get("briefTitle", "")
            investigators = self._extract_investigators(study)
            is_pi, pi_role = False, None
            for inv in investigators:
                if self._matches_researcher(inv["name"], researcher_name) and self._is_principal_investigator(inv):
                    is_pi, pi_role = True, inv["role"]
                    result.studies_as_pi += 1
                    break
            if not is_pi:
                continue
            study_url = f"https://clinicaltrials.gov/study/{nct_id}"
            lead = self._extract_lead_sponsor(study)
            if lead:
                result.corporate_links.append(CorporateLink(
                    researcher=researcher_name, corporate=lead, role=pi_role or "Principal Investigator",
                    nct_id=nct_id, study_title=title, detection_field="Sponsor",
                    detection_value=lead, study_url=study_url
                ))
                result.corporates_found.add(lead)
            for collaborator in self._extract_collaborators(study):
                if not any(lk.corporate == collaborator and lk.nct_id == nct_id for lk in result.corporate_links):
                    result.corporate_links.append(CorporateLink(
                        researcher=researcher_name, corporate=collaborator, role=pi_role or "Principal Investigator",
                        nct_id=nct_id, study_title=title, detection_field="Collaborateur",
                        detection_value=collaborator, study_url=study_url
                    ))
                    result.corporates_found.add(collaborator)
        return result


# Convenience function
def search_clinical_trials_corporate(
    researcher_name: str,
    corporate_keywords: Optional[List[str]] = None
) -> ClinicalTrialsSearchResult:
    """
    Search for corporate links via clinical trials.

    Convenience wrapper around ClinicalTrialsClient.

    Args:
        researcher_name: Name of researcher
        corporate_keywords: Optional list of corporate keywords

    Returns:
        Search result with corporate links

    Example:
        >>> results = search_clinical_trials_corporate("Edgar Duval")
        >>> for link in results.corporate_links:
        ...     print(f"{link.researcher} → {link.corporate}")
    """
    client = ClinicalTrialsClient(corporate_keywords=corporate_keywords)
    return client.find_corporate_links(researcher_name)
