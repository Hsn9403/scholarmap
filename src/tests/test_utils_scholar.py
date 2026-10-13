#!/usr/bin/env python3
"""Tests for Scholar-related utility functions."""
import pytest
from unittest.mock import MagicMock, patch

from src.scholar import name_matches_query, score_candidate, ScholarClient
from src.models import ScholarData


class TestNameMatchesQuery:
    """Tests for name matching in Scholar search."""

    def test_exact_match(self):
        assert name_matches_query("John Doe", "John Doe") is True

    def test_case_insensitive(self):
        assert name_matches_query("john doe", "John Doe") is True
        assert name_matches_query("JOHN DOE", "John Doe") is True

    def test_accent_insensitive(self):
        assert name_matches_query("François Müller", "Francois Muller") is True

    def test_requires_last_name_match(self):
        assert name_matches_query("John Smith", "John Doe") is False

    def test_accepts_first_initial(self):
        assert name_matches_query("John Doe", "J. Doe") is True
        assert name_matches_query("J. Doe", "John Doe") is True

    def test_middle_names_flexible(self):
        assert name_matches_query("John Michael Doe", "John Doe") is True
        assert name_matches_query("John Doe", "John M. Doe") is True

    def test_rejects_single_word_names(self):
        assert name_matches_query("Madonna", "Cher") is False


class TestScoreCandidate:
    """Tests for candidate scoring in disambiguation."""

    def test_affiliation_match_scores_high(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="MIT Computer Science",
            citations_total=1000,
            h_index=20,
            publications_total=50,
            top_publications=[]
        )
        score = score_candidate("MIT", scholar, "")
        assert score >= 3  # affiliation match is worth 3 points

    def test_name_match_scores(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="Some University",
            citations_total=1000,
            h_index=20,
            publications_total=50,
            top_publications=[]
        )
        score = score_candidate("John", scholar, "")
        assert score >= 2  # name match is worth 2 points

    def test_snippet_match_scores(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="Some University",
            citations_total=1000,
            h_index=20,
            publications_total=50,
            top_publications=[]
        )
        score = score_candidate("machine learning", scholar, "Expert in machine learning")
        assert score >= 1  # snippet match is worth 1 point

    def test_no_match_returns_zero(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="Some University",
            citations_total=1000,
            h_index=20,
            publications_total=50,
            top_publications=[]
        )
        score = score_candidate("completely different text", scholar, "")
        assert score == 0

    def test_empty_filter_returns_zero(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="MIT",
            citations_total=1000,
            h_index=20,
            publications_total=50,
            top_publications=[]
        )
        score = score_candidate("", scholar, "")
        assert score == 0


class TestExtractMetricFromCitedByTable:
    """Tests for extracting metrics from Scholar API response."""

    @pytest.fixture
    def mock_client(self):
        """Create a ScholarClient with mocked API."""
        with patch("src.scholar.client.SerpAPIClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            client = ScholarClient(api_key="DUMMY")
            return client

    def test_extracts_citations(self, mock_client):
        author_json = {
            "cited_by": {
                "table": [
                    {"citations": {"all": 1500, "since_2021": 800}}
                ]
            }
        }
        result = mock_client._extract_metric(author_json, "citations")
        assert result == 1500

    def test_extracts_h_index(self, mock_client):
        author_json = {
            "cited_by": {
                "table": [
                    {"h_index": {"all": 25, "since_2021": 20}}
                ]
            }
        }
        result = mock_client._extract_metric(author_json, "h_index")
        assert result == 25

    def test_handles_h_index_variations(self, mock_client):
        # Test with hindex instead of h_index
        author_json = {
            "cited_by": {
                "table": [
                    {"hindex": {"all": 25}}
                ]
            }
        }
        result = mock_client._extract_metric(author_json, "h_index")
        assert result == 25

    def test_handles_missing_metric(self, mock_client):
        author_json = {
            "cited_by": {
                "table": [
                    {"citations": {"all": 1500}}
                ]
            }
        }
        result = mock_client._extract_metric(author_json, "h_index")
        assert result is None

    def test_handles_empty_table(self, mock_client):
        author_json = {
            "cited_by": {
                "table": []
            }
        }
        result = mock_client._extract_metric(author_json, "citations")
        assert result is None

    def test_handles_missing_cited_by(self, mock_client):
        author_json = {}
        result = mock_client._extract_metric(author_json, "citations")
        assert result is None
