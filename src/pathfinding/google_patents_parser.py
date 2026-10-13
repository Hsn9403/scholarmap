"""
Google Patents parser.

This module fetches and parses Google Patents pages to extract
the INVENTORS list, which is critical for validating patent-based
corporate connections.

CRITICAL: We must verify that a co-author's name appears in the
inventors list, not just that a patent exists with that assignee.
"""
import re
import requests
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

from src.logger import logger


class GooglePatentsParser:
    """Parser for Google Patents pages."""

    def __init__(self):
        """Initialize parser."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def parse_patent_page(self, patent_url: str) -> Optional[Dict[str, Any]]:
        """
        Parse a Google Patents page to extract inventors and other metadata.

        Args:
            patent_url: URL to patent page (e.g., https://patents.google.com/patent/US10292592B2)

        Returns:
            Dict with:
            - inventors: List[str] - List of inventor names
            - assignee: str - Current assignee
            - title: str - Patent title
            - patent_id: str - Patent ID
            Or None if parsing failed.
        """
        logger.info(f"Parsing patent page: {patent_url}")

        try:
            response = self.session.get(patent_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract patent ID from URL
            patent_id_match = re.search(r'/patent/([^/]+)', patent_url)
            patent_id = patent_id_match.group(1) if patent_id_match else "Unknown"

            # Extract title
            title_elem = soup.find('meta', {'name': 'DC.title'})
            title = title_elem.get('content', 'Unknown') if title_elem else "Unknown"

            # Extract inventors
            # Google Patents uses <dd itemprop="inventor">
            inventors = []
            inventor_elems = soup.find_all('dd', {'itemprop': 'inventor'})

            if inventor_elems:
                for elem in inventor_elems:
                    # Get text and clean it
                    inventor_name = elem.get_text(strip=True)
                    if inventor_name:
                        inventors.append(inventor_name)
                        logger.debug(f"  Found inventor: {inventor_name}")
            else:
                # Fallback: Try to find in text
                # Look for "Inventor:" label
                inventor_section = soup.find(string=re.compile(r'Inventor:', re.IGNORECASE))
                if inventor_section:
                    # Get next sibling or parent's next sibling
                    parent = inventor_section.parent
                    if parent:
                        # Try to find names after "Inventor:"
                        text = parent.get_text()
                        # Simple heuristic: names are usually capitalized words separated by commas
                        names_match = re.search(r'Inventor:\s*([A-Z][^:]+?)(?:Current Assignee|Worldwide|$)', text)
                        if names_match:
                            names_text = names_match.group(1).strip()
                            # Split by comma
                            inventors = [name.strip() for name in names_text.split(',') if name.strip()]

            # Extract current assignee
            assignee = "Unknown"
            assignee_elem = soup.find('dd', {'itemprop': 'assigneeCurrent'})
            if assignee_elem:
                assignee = assignee_elem.get_text(strip=True)
            else:
                # Fallback: Look for "Current Assignee:" text
                assignee_section = soup.find(string=re.compile(r'Current Assignee:', re.IGNORECASE))
                if assignee_section:
                    parent = assignee_section.parent
                    if parent:
                        text = parent.get_text()
                        assignee_match = re.search(r'Current Assignee:\s*([^\n]+)', text)
                        if assignee_match:
                            assignee = assignee_match.group(1).strip()

            logger.info(f"  ✓ Parsed: {len(inventors)} inventor(s), assignee: {assignee}")

            return {
                "patent_id": patent_id,
                "title": title,
                "inventors": inventors,
                "assignee": assignee,
                "source_url": patent_url
            }

        except requests.RequestException as e:
            logger.error(f"Error fetching patent page: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing patent page: {e}")
            return None

    def extract_inventors_from_text(self, html_text: str) -> List[str]:
        """
        Extract inventors from raw HTML text (fallback method).

        Args:
            html_text: Raw HTML text.

        Returns:
            List of inventor names.
        """
        inventors = []

        # Look for inventor section
        inventor_match = re.search(
            r'<meta\s+name="DC\.creator"\s+content="([^"]+)"',
            html_text,
            re.IGNORECASE
        )

        if inventor_match:
            inventor_name = inventor_match.group(1).strip()
            inventors.append(inventor_name)

        return inventors


def fetch_and_validate_inventors(
    patent_url: str,
    coauthor_name: str,
    min_confidence: float = 0.85
) -> tuple[bool, Optional[str], List[str]]:
    """
    Fetch patent page and validate that co-author is in inventors list.

    Args:
        patent_url: URL to patent page.
        coauthor_name: Name to validate.
        min_confidence: Minimum confidence for name matching.

    Returns:
        (is_valid, matching_inventor, all_inventors) tuple.
    """
    from src.pathfinding.evidence_validator import find_matching_inventor

    parser = GooglePatentsParser()
    patent_data = parser.parse_patent_page(patent_url)

    if not patent_data:
        logger.warning(f"Could not parse patent page: {patent_url}")
        return (False, None, [])

    inventors = patent_data.get("inventors", [])

    if not inventors:
        logger.warning(f"No inventors found on patent page: {patent_url}")
        return (False, None, [])

    # Validate using evidence_validator
    result = find_matching_inventor(coauthor_name, inventors, min_confidence)

    if result:
        matching_name, confidence = result
        logger.info(f"  ✓ VALIDATED: '{coauthor_name}' → '{matching_name}' in inventors")
        return (True, matching_name, inventors)
    else:
        logger.warning(f"  ✗ NOT FOUND: '{coauthor_name}' not in inventors: {', '.join(inventors)}")
        return (False, None, inventors)
