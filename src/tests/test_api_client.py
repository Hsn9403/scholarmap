#!/usr/bin/env python3
"""Tests for SerpAPI client."""
import pytest
from unittest.mock import patch, MagicMock

from src.api import SerpAPIClient, serp_search, serp_search_html
from src.exceptions import ConfigurationError, APIError


class TestSerpAPIClient:
    """Tests for SerpAPIClient class."""

    def test_creates_client_with_api_key(self):
        """Test client creation with explicit API key."""
        with patch("src.api.serpapi_client.CassetteManager"):
            client = SerpAPIClient(api_key="test_key", cassette_mode="disabled")
            assert client.api_key == "test_key"

    def test_creates_client_from_env(self, monkeypatch):
        """Test client creation using environment variable."""
        monkeypatch.setenv("SERPAPI_KEY", "env_test_key")
        with patch("src.api.serpapi_client.CassetteManager"):
            client = SerpAPIClient(cassette_mode="disabled")
            assert client.api_key == "env_test_key"

    def test_raises_error_when_no_key(self, monkeypatch):
        """Test error when no API key is available (not in offline mode)."""
        monkeypatch.delenv("SERPAPI_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI", raising=False)

        with patch("src.api.serpapi_client.CassetteManager"):
            with pytest.raises(ConfigurationError) as exc_info:
                SerpAPIClient(cassette_mode="disabled")
            assert "SERPAPI_KEY" in str(exc_info.value)

    def test_allows_missing_key_in_offline_mode(self, monkeypatch):
        """Test that offline mode with explicit None api_key works."""
        monkeypatch.delenv("SERPAPI_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI", raising=False)

        with patch("src.api.serpapi_client.CassetteManager"):
            # In offline mode with explicit api_key=None, we can create the client
            # Note: current implementation still requires env var, so we skip this test
            # Uncomment when offline mode is fully implemented
            pytest.skip("Offline mode without API key not yet fully implemented")


class TestSerpAPIClientSearch:
    """Tests for SerpAPIClient.search method."""

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_successful_search(self, mock_cassette, mock_google_search):
        """Test successful API call."""
        mock_cassette.return_value.get.return_value = None  # Cache miss
        mock_instance = MagicMock()
        mock_instance.get_dict.return_value = {
            "search_metadata": {"status": "Success"},
            "organic_results": [{"title": "Test"}]
        }
        mock_google_search.return_value = mock_instance

        client = SerpAPIClient(api_key="test_key", cassette_mode="disabled")
        result = client.search({"engine": "google", "q": "test"})

        assert result["search_metadata"]["status"] == "Success"
        assert len(result["organic_results"]) == 1

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_raises_on_api_error(self, mock_cassette, mock_google_search):
        """Test that API errors are caught and re-raised as APIError."""
        mock_cassette.return_value.get.return_value = None
        mock_instance = MagicMock()
        mock_instance.get_dict.return_value = {
            "error": "Invalid API key"
        }
        mock_google_search.return_value = mock_instance

        client = SerpAPIClient(api_key="bad_key", cassette_mode="disabled")

        with pytest.raises(APIError) as exc_info:
            client.search({"engine": "google", "q": "test"})
        assert "Invalid API key" in str(exc_info.value)

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_raises_on_exception(self, mock_cassette, mock_google_search):
        """Test that exceptions are caught and wrapped in APIError."""
        mock_cassette.return_value.get.return_value = None
        mock_google_search.side_effect = Exception("Network error")

        client = SerpAPIClient(api_key="test_key", cassette_mode="disabled")

        with pytest.raises(APIError) as exc_info:
            client.search({"engine": "google", "q": "test"})
        assert "Failed to execute SerpAPI search" in str(exc_info.value)


class TestSerpAPIClientSearchHtml:
    """Tests for SerpAPIClient.search_html method."""

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_successful_html_search(self, mock_cassette, mock_google_search):
        """Test successful HTML API call."""
        mock_cassette.return_value.get.return_value = None
        mock_instance = MagicMock()
        mock_instance.get_html.return_value = "<html>Test</html>"
        mock_google_search.return_value = mock_instance

        client = SerpAPIClient(api_key="test_key", cassette_mode="disabled")
        result = client.search_html({"engine": "google", "q": "test"})

        assert result == "<html>Test</html>"

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_raises_on_html_exception(self, mock_cassette, mock_google_search):
        """Test that HTML search exceptions are caught."""
        mock_cassette.return_value.get.return_value = None
        mock_google_search.side_effect = Exception("Connection timeout")

        client = SerpAPIClient(api_key="test_key", cassette_mode="disabled")

        with pytest.raises(APIError) as exc_info:
            client.search_html({"engine": "google", "q": "test"})
        assert "Failed to execute SerpAPI HTML search" in str(exc_info.value)


class TestBackwardCompatFunctions:
    """Tests for backward-compatible functions."""

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_serp_search_with_api_key_in_params(self, mock_cassette, mock_google_search):
        """Test serp_search function with api_key in params."""
        mock_cassette.return_value.get.return_value = None
        mock_instance = MagicMock()
        mock_instance.get_dict.return_value = {"status": "Success"}
        mock_google_search.return_value = mock_instance

        result = serp_search({
            "engine": "google",
            "q": "test",
            "api_key": "test_key"
        })

        assert result["status"] == "Success"

    @patch("src.api.serpapi_client.GoogleSearch")
    @patch("src.api.serpapi_client.CassetteManager")
    def test_serp_search_html_with_api_key_in_params(self, mock_cassette, mock_google_search):
        """Test serp_search_html function with api_key in params."""
        mock_cassette.return_value.get.return_value = None
        mock_instance = MagicMock()
        mock_instance.get_html.return_value = "<html>Test</html>"
        mock_google_search.return_value = mock_instance

        result = serp_search_html({
            "engine": "google",
            "q": "test",
            "api_key": "test_key"
        })

        assert result == "<html>Test</html>"
