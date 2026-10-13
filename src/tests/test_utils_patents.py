#!/usr/bin/env python3
"""Tests for patent-related utility functions."""
from src.patents.entity import split_name_parts, same_person
from src.graph.builder import _normalize_patent_id as normalize_patent_id_for_html


def remove_input_name_from_inventors(inventors: list, researcher_name: str) -> list:
    """Filter out the researcher from a list of inventors."""
    return [inv for inv in inventors if not same_person(inv, researcher_name)]


class TestNormalizePatentId:
    """Tests for patent ID normalization for HTML."""

    def test_basic_patent_id(self):
        result = normalize_patent_id_for_html("US1234567A1")
        assert result == "US1234567A1"

    def test_extracts_from_full_path(self):
        # Function extracts ID from pattern: patent/ID/
        result = normalize_patent_id_for_html("patent/US1234567A1/en")
        assert result == "US1234567A1"

    def test_handles_empty(self):
        result = normalize_patent_id_for_html("")
        assert result == ""


class TestSplitNameParts:
    """Tests for name splitting into first/last."""

    def test_splits_two_part_name(self):
        first, last = split_name_parts("John Doe")
        assert first == "john"
        assert last == "doe"

    def test_splits_three_part_name(self):
        first, last = split_name_parts("Jean Paul Dupont")
        assert first == "jean"
        assert last == "dupont"

    def test_handles_single_name(self):
        first, last = split_name_parts("Madonna")
        assert first == ""
        assert last == "madonna"

    def test_normalizes_case(self):
        first, last = split_name_parts("JOHN DOE")
        assert first == "john"
        assert last == "doe"

    def test_removes_accents(self):
        first, last = split_name_parts("François Müller")
        assert first == "francois"
        assert last == "muller"


class TestSamePerson:
    """Tests for person name matching."""

    def test_exact_match(self):
        assert same_person("John Doe", "John Doe") is True

    def test_case_insensitive(self):
        assert same_person("John Doe", "john doe") is True
        assert same_person("JOHN DOE", "John Doe") is True

    def test_accent_insensitive(self):
        assert same_person("François Müller", "Francois Muller") is True

    def test_same_last_name_same_first_initial(self):
        assert same_person("John Doe", "James Doe") is True  # J.D. vs J.D.
        assert same_person("Alice Smith", "Anna Smith") is True  # A.S. vs A.S.

    def test_different_last_name(self):
        assert same_person("John Doe", "John Smith") is False

    def test_different_first_initial(self):
        assert same_person("Alice Smith", "Bob Smith") is False

    def test_handles_middle_names(self):
        assert same_person("John Michael Doe", "John Doe") is True

    def test_single_name_returns_false(self):
        assert same_person("Madonna", "Cher") is False


class TestRemoveInputNameFromInventors:
    """Tests for filtering out the main researcher from inventors list."""

    def test_removes_exact_match(self):
        inventors = ["John Doe", "Jane Smith", "Bob Wilson"]
        result = remove_input_name_from_inventors(inventors, "John Doe")
        assert result == ["Jane Smith", "Bob Wilson"]

    def test_removes_case_insensitive(self):
        inventors = ["JOHN DOE", "Jane Smith"]
        result = remove_input_name_from_inventors(inventors, "john doe")
        assert result == ["Jane Smith"]

    def test_removes_accent_variations(self):
        inventors = ["François Müller", "Jane Smith"]
        result = remove_input_name_from_inventors(inventors, "Francois Muller")
        assert result == ["Jane Smith"]

    def test_keeps_different_people(self):
        inventors = ["John Smith", "Alice Brown"]
        result = remove_input_name_from_inventors(inventors, "John Doe")
        assert len(result) == 2

    def test_handles_empty_list(self):
        result = remove_input_name_from_inventors([], "John Doe")
        assert result == []

    def test_removes_all_matches(self):
        inventors = ["John Doe", "Jane Smith", "John Doe"]
        result = remove_input_name_from_inventors(inventors, "John Doe")
        assert result == ["Jane Smith"]
