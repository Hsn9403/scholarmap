#!/usr/bin/env python3
"""
HTML parsing utilities for Google Patents pages.

This module provides functions to extract structured data from
Google Patents HTML pages (tables, assignees, citations).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


def parse_cited_by_table(html: str) -> List[Dict[str, Any]]:
    """
    Extract citing patents from the "Cited By" HTML table (forward citations).

    IMPORTANT: This function specifically looks for the table following
    a "Cited By" heading, NOT "Patent Citations" (which is backward citations).

    Args:
        html: Full HTML content of the patent page.

    Returns:
        List of dicts with keys: publication_number, priority_date,
        publication_date, assignee, title, link.

    Example:
        >>> events = parse_cited_by_table(html_content)
        >>> for e in events:
        ...     print(f"{e['publication_number']} by {e['assignee']}")
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    def get_headers(table) -> List[str]:
        ths = table.find_all("th")
        if ths:
            return [norm(th.get_text(" ", strip=True)) for th in ths]
        first_tr = table.find("tr")
        if first_tr:
            tds = first_tr.find_all("td")
            return [norm(td.get_text(" ", strip=True)) for td in tds]
        return []

    def find_col_idx(hdrs: List[str], keys: List[str]) -> Optional[int]:
        for i, h in enumerate(hdrs):
            for k in keys:
                if k in h:
                    return i
        return None

    # Find the "Cited By" heading (forward citations)
    # This must be a real heading like <h2>Cited By (5)</h2>
    cited_by_heading = soup.find(
        lambda tag: tag.name in ["h1", "h2", "h3", "h4"]
        and re.match(r'^\s*Cited\s+By\s*(?:\(\d+\))?\s*$', tag.get_text(), re.IGNORECASE)
    )

    if not cited_by_heading:
        # No "Cited By" section found - return empty
        return []

    # Find the table that follows this heading
    target_table = cited_by_heading.find_next("table")
    if not target_table:
        return []

    # Get headers
    headers = get_headers(target_table)
    if not headers:
        return []

    # Find column indices
    idx_pub = find_col_idx(headers, ["publication number", "publication"])
    idx_prio = find_col_idx(headers, ["priority date", "priority"])
    idx_pubdate = find_col_idx(headers, ["publication date"])
    idx_assignee = find_col_idx(headers, ["assignee"])
    idx_title = find_col_idx(headers, ["title"])

    if idx_pub is None:
        return []

    rows = target_table.find_all("tr")
    if not rows:
        return []

    events = []
    start_row = 1 if rows and rows[0].find_all("th") else 0

    for tr in rows[start_row:]:
        tds = tr.find_all("td")
        if not tds or idx_pub >= len(tds):
            continue

        # Extract publication number and link
        pub_cell = tds[idx_pub]
        anchor = pub_cell.find("a")
        pub_number = (
            anchor.get_text(" ", strip=True) if anchor
            else pub_cell.get_text(" ", strip=True)
        ).strip()
        pub_number = re.sub(r"\s*\(\s*en\s*\)\s*", "", pub_number, flags=re.I).strip()

        if not pub_number:
            continue

        link = ""
        if anchor and anchor.has_attr("href"):
            href = anchor["href"].strip()
            link = href if href.startswith("http") else f"https://patents.google.com{href}"

        def get_cell_text(idx: Optional[int]) -> Optional[str]:
            if idx is not None and idx < len(tds):
                return tds[idx].get_text(" ", strip=True).strip() or None
            return None

        events.append({
            "publication_number": pub_number,
            "priority_date": get_cell_text(idx_prio),
            "publication_date": get_cell_text(idx_pubdate),
            "assignee": get_cell_text(idx_assignee),
            "title": get_cell_text(idx_title),
            "link": link,
        })

    return events


def parse_current_assignee(html: str) -> str:
    """
    Extract current assignee from HTML page.

    Looks for "Current Assignee" or "Assignee" in definition lists.

    Args:
        html: Full HTML content.

    Returns:
        Assignee name, or empty string if not found.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    for dt in soup.find_all("dt"):
        dt_text = (dt.get_text() or "").strip().lower()
        if "current assignee" in dt_text or dt_text == "assignee":
            dd = dt.find_next("dd")
            if dd:
                text = dd.get_text(strip=True)
                # Remove trailing country codes (e.g., ", FR", ", US")
                text = re.sub(r',\s*[A-Z]{2}\s*$', '', text)
                return text.strip()
    return ""


def parse_assignees_from_table(
    html: str,
    heading: str
) -> List[str]:
    """
    Extract assignees from a table following a specific heading.

    Args:
        html: Full HTML content.
        heading: Heading text to find (e.g., "Patent Citations", "Cited By").

    Returns:
        List of assignee names.
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")

    # Find heading
    h = soup.find(
        lambda tag: tag.name in ["h1", "h2", "h3", "h4", "div", "span"]
        and heading.lower() in tag.get_text(" ", strip=True).lower()
    )
    if not h:
        return []

    table = h.find_next("table")
    if not table:
        return []

    # Find "Assignee" column index
    headers = [
        th.get_text(" ", strip=True).lower()
        for th in table.find_all("th")
    ]

    assignee_idx = None
    for i, t in enumerate(headers):
        if "assignee" in t:
            assignee_idx = i
            break

    if assignee_idx is None:
        return []

    # Extract assignees from rows
    out: List[str] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) > assignee_idx:
            txt = re.sub(r"\s+", " ", tds[assignee_idx].get_text(" ", strip=True)).strip()
            if txt:
                out.append(txt)

    # Deduplicate preserving order
    seen = set()
    dedup = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)

    return dedup


def has_cited_by_section(html: str) -> bool:
    """
    Check if HTML contains a "Cited By" section (forward citations).

    This checks for a real heading like <h2>Cited By (5)</h2>, not just
    the text "Cited by" which appears in table captions.

    Args:
        html: HTML content.

    Returns:
        True if "Cited By" section exists.
    """
    if not html:
        return False

    # Look for a real heading, not just caption text like "Cited by examiner"
    # Match patterns like <h2>Cited By (3)</h2> or <h3>Cited By</h3>
    heading_pattern = re.compile(
        r'<h[1-4][^>]*>\s*Cited\s+By\s*(?:\(\d+\))?\s*</h[1-4]>',
        re.IGNORECASE
    )

    return bool(heading_pattern.search(html))
