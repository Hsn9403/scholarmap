#!/usr/bin/env python3
"""Tests for graph-related utility functions."""
from src.graph.builder import (
    _node_id,
    _patent_node_id,
    _is_placeholder as _is_placeholder_company,
    _same_org as same_org_strong,
)
from src.helpers import dedup_preserve_order
from src.patents.entity import normalize_org as norm_org_tokens


class TestNodeId:
    """Tests for node ID generation."""

    def test_creates_valid_node_id(self):
        assert _node_id("person", "John Doe") == "person:john_doe"
        assert _node_id("org", "MIT") == "org:mit"

    def test_handles_special_chars(self):
        result = _node_id("person", "Jean-Paul O'Connor")
        assert result == "person:jean_paul_o_connor"

    def test_handles_accents(self):
        result = _node_id("org", "École Polytechnique")
        assert result == "org:ecole_polytechnique"


class TestPatentNodeId:
    """Tests for patent node ID generation."""

    def test_creates_patent_id(self):
        result = _patent_node_id("US1234567A1")
        assert result == "patent:US1234567A1"

    def test_cleans_patent_path(self):
        result = _patent_node_id("patent/US1234567A1/en")
        assert result == "patent:US1234567A1"

    def test_handles_empty(self):
        result = _patent_node_id("")
        assert result == "patent:unknown"


class TestDedupPreserve:
    """Tests for deduplication while preserving order."""

    def test_removes_duplicates(self):
        input_list = ["apple", "banana", "apple", "cherry", "banana"]
        result = dedup_preserve_order(input_list)
        assert result == ["apple", "banana", "cherry"]

    def test_preserves_order(self):
        input_list = ["z", "a", "m", "a", "b"]
        result = dedup_preserve_order(input_list)
        assert result == ["z", "a", "m", "b"]

    def test_strips_whitespace(self):
        input_list = ["  apple  ", "banana", " apple ", "cherry"]
        result = dedup_preserve_order(input_list)
        assert result == ["apple", "banana", "cherry"]

    def test_filters_empty_strings(self):
        input_list = ["apple", "", "banana", "  ", "cherry"]
        result = dedup_preserve_order(input_list)
        assert result == ["apple", "banana", "cherry"]

    def test_handles_empty_list(self):
        assert dedup_preserve_order([]) == []


class TestIsPlaceholderCompany:
    """Tests for placeholder company detection."""

    def test_detects_placeholder(self):
        assert _is_placeholder_company("No corporate has cited this patent") is True
        assert _is_placeholder_company("NO CORPORATE HAS CITED THIS PATENT") is True
        assert _is_placeholder_company("  no corporate has cited this patent  ") is True

    def test_rejects_real_companies(self):
        assert _is_placeholder_company("Apple Inc.") is False
        assert _is_placeholder_company("Google LLC") is False
        assert _is_placeholder_company("") is False


class TestNormOrgTokens:
    """Tests for organization name normalization."""

    def test_removes_corporate_suffixes(self):
        assert "apple" in norm_org_tokens("Apple Inc.")
        assert "google" in norm_org_tokens("Google LLC")
        assert "microsoft" in norm_org_tokens("Microsoft Corporation")

    def test_removes_accents(self):
        result = norm_org_tokens("Société Générale SA")
        assert "societe" in result
        assert "generale" in result

    def test_lowercase(self):
        result = norm_org_tokens("APPLE INC")
        assert result.islower()


class TestSameOrgStrong:
    """Tests for organization matching."""

    def test_exact_match(self):
        assert same_org_strong("Apple Inc.", "Apple Inc.") is True

    def test_suffix_variations(self):
        assert same_org_strong("Apple Inc.", "Apple Corporation") is True
        assert same_org_strong("Google LLC", "Google") is True

    def test_substring_match(self):
        assert same_org_strong("Apple", "Apple Inc.") is True
        assert same_org_strong("Microsoft Corporation", "Microsoft") is True

    def test_different_orgs(self):
        assert same_org_strong("Apple", "Google") is False
        assert same_org_strong("IBM", "Microsoft") is False

    def test_handles_empty(self):
        assert same_org_strong("", "Apple") is False
        assert same_org_strong("Apple", "") is False
        assert same_org_strong("", "") is False

    def test_accent_insensitive(self):
        assert same_org_strong("Société Générale", "Societe Generale") is True
