#!/usr/bin/env python3
"""
Integration tests for SerpAPI client.

These tests use VCR to record and replay API responses.
First run with SERPAPI_KEY set will record the cassette.
Subsequent runs replay from cassette without API calls.
"""
import os
import vcr
import pytest
from unittest.mock import MagicMock, patch

from src.api import serp_search, SerpAPIClient


my_vcr = vcr.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "path", "query"],
    filter_query_parameters=["api_key"],
)


@pytest.mark.integration
def test_google_coffee_response_shape():
    """
    Integration test for Google search.

    Requires SERPAPI_KEY in env for first run to record cassette.
    Delete tests/cassettes/google_coffee.yaml to re-record.
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        pytest.skip("SERPAPI_KEY not set (skip integration test)")

    params = {
        "engine": "google",
        "q": "Coffee",
        "location": "Austin, Texas, United States",
        "api_key": api_key,
    }

    with my_vcr.use_cassette("google_coffee.yaml"):
        res = serp_search(params)

    assert res["search_metadata"]["status"] == "Success"
    assert res["search_parameters"]["engine"] == "google"
    assert "search_information" in res
    assert isinstance(res["search_information"], dict)


# -----------------------
# Unit tests (mocked)
# -----------------------
def test_serp_search_returns_dict():
    """Unit test: verify serp_search returns a dict with mocked client."""
    fake_response = {
        "search_metadata": {"status": "Success"},
        "search_parameters": {"engine": "google", "q": "test"},
        "organic_results": [{"title": "Test Result"}],
    }

    with patch("src.api.serpapi_client.GoogleSearch") as MockGoogleSearch:
        mock_instance = MagicMock()
        mock_instance.get_dict.return_value = fake_response
        MockGoogleSearch.return_value = mock_instance

        result = serp_search({
            "engine": "google",
            "q": "test",
            "api_key": "DUMMY"
        })

    assert isinstance(result, dict)
    assert result["search_metadata"]["status"] == "Success"


def test_serpapi_client_search_method():
    """Unit test: verify SerpAPIClient.search method works."""
    fake_response = {
        "search_metadata": {"status": "Success"},
        "organic_results": [{"title": "Test"}],
    }

    with patch("src.api.serpapi_client.GoogleSearch") as MockGoogleSearch:
        mock_instance = MagicMock()
        mock_instance.get_dict.return_value = fake_response
        MockGoogleSearch.return_value = mock_instance

        client = SerpAPIClient(api_key="DUMMY")
        result = client.search({"engine": "google", "q": "test"})

    assert isinstance(result, dict)
    assert result["search_metadata"]["status"] == "Success"
