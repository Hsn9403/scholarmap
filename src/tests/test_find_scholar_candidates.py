#!/usr/bin/env python3
"""
Tests for Google Scholar candidate search functionality.

Tests both the legacy function interface and the underlying ScholarClient.
"""
import os
import vcr
import pytest
from typing import Any
from unittest.mock import MagicMock, patch

from src.scholar import find_scholar_candidates_via_google
from src.models import ScholarCandidate


def get_field(item: Any, field: str):
    """Helper to read a field whether item is a dict or an object with attributes."""
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


# -----------------------
# Integration (VCR)
# -----------------------
my_vcr = vcr.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "path", "query"],
    filter_query_parameters=["api_key"],
)


@pytest.mark.integration
def test_find_scholar_candidates_integration_vcr():
    """
    Integration test which will record a cassette on first run.
    Requires SERPAPI_KEY in env for the first run, subsequent runs use cassette.
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        pytest.skip("SERPAPI_KEY not set (skip integration test)")

    cassette_path = "tests/cassettes/google_scholar_candidates.yaml"
    with my_vcr.use_cassette(cassette_path):
        results = find_scholar_candidates_via_google(
            name="Alice Smith",
            api_key=api_key
        )

    assert isinstance(results, list)
    # May be empty if no Scholar profile exists
    for r in results:
        author_id = get_field(r, "author_id")
        assert author_id is not None


# -----------------------
# Unit tests (mocked)
# -----------------------
def test_find_scholar_candidates_returns_expected_shape_with_mock():
    """
    Unit test: mock underlying SerpAPIClient to return a known payload,
    then assert that the function translates it to the expected shape.
    """
    fake_response = {
        "search_metadata": {"status": "Success"},
        "organic_results": [
            {
                "title": "Alice Smith - University of Paris",
                "link": "https://scholar.google.com/citations?user=ABC123&hl=en",
                "snippet": "Professor Alice Smith ...",
            }
        ],
    }

    with patch("src.scholar.client.SerpAPIClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = fake_response
        MockClient.return_value = mock_instance

        results = find_scholar_candidates_via_google(
            name="Alice Smith",
            api_key="DUMMY"
        )

    assert isinstance(results, list)
    assert len(results) == 1

    r = results[0]
    assert isinstance(r, ScholarCandidate)
    assert r.author_id == "ABC123"
    assert "Alice Smith" in r.title


def test_find_scholar_candidates_handles_empty_results():
    """Ensure empty lists are handled gracefully (no exceptions, empty list returned)."""
    fake_response = {
        "search_metadata": {"status": "Success"},
        "organic_results": []
    }

    with patch("src.scholar.client.SerpAPIClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = fake_response
        MockClient.return_value = mock_instance

        results = find_scholar_candidates_via_google(
            name="NonExistingPersonForSure",
            api_key="DUMMY"
        )

    assert isinstance(results, list)
    assert results == []


def test_find_scholar_candidates_extracts_author_id_from_url():
    """Verify that author_id is correctly extracted from Scholar profile URLs."""
    fake_response = {
        "organic_results": [
            {
                "title": "John Doe",
                "link": "https://scholar.google.com/citations?user=XYZ789&hl=fr",
                "snippet": "Researcher at MIT",
            },
            {
                "title": "Jane Doe",
                "link": "https://scholar.google.com/citations?user=ABC123&hl=en",
                "snippet": "Professor at Stanford",
            },
        ],
    }

    with patch("src.scholar.client.SerpAPIClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = fake_response
        MockClient.return_value = mock_instance

        results = find_scholar_candidates_via_google(
            name="Doe",
            api_key="DUMMY"
        )

    assert len(results) == 2
    assert results[0].author_id == "XYZ789"
    assert results[1].author_id == "ABC123"


def test_find_scholar_candidates_deduplicates_by_author_id():
    """Ensure duplicate author_ids are filtered out."""
    fake_response = {
        "organic_results": [
            {
                "title": "John Doe",
                "link": "https://scholar.google.com/citations?user=ABC123",
                "snippet": "First result",
            },
            {
                "title": "John Doe - Duplicated",
                "link": "https://scholar.google.com/citations?user=ABC123",
                "snippet": "Duplicate result",
            },
        ],
    }

    with patch("src.scholar.client.SerpAPIClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = fake_response
        MockClient.return_value = mock_instance

        results = find_scholar_candidates_via_google(
            name="John Doe",
            api_key="DUMMY"
        )

    assert len(results) == 1
    assert results[0].author_id == "ABC123"


def test_find_scholar_candidates_ignores_non_scholar_links():
    """Ensure non-Scholar links are filtered out."""
    fake_response = {
        "organic_results": [
            {
                "title": "Random Page",
                "link": "https://example.com/profile",
                "snippet": "Not a scholar profile",
            },
            {
                "title": "John Doe",
                "link": "https://scholar.google.com/citations?user=ABC123",
                "snippet": "Real scholar profile",
            },
        ],
    }

    with patch("src.scholar.client.SerpAPIClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.search.return_value = fake_response
        MockClient.return_value = mock_instance

        results = find_scholar_candidates_via_google(
            name="John Doe",
            api_key="DUMMY"
        )

    assert len(results) == 1
    assert results[0].author_id == "ABC123"
