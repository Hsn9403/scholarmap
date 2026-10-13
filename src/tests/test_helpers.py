#!/usr/bin/env python3
"""Tests for helper functions (normalization, dates, slugs, etc.)."""
from src.helpers import (
    strip_accents_basic,
    safe_int,
    slug,
    parse_yyyy_mm_dd,
    normalize_for_match,
)


class TestStripAccents:
    """Tests for accent removal."""

    def test_removes_accents(self):
        assert strip_accents_basic("café") == "cafe"
        assert strip_accents_basic("naïve") == "naive"
        assert strip_accents_basic("François") == "Francois"

    def test_handles_empty_string(self):
        assert strip_accents_basic("") == ""

    def test_preserves_non_accented(self):
        assert strip_accents_basic("hello") == "hello"


class TestSafeInt:
    """Tests for safe integer conversion."""

    def test_converts_valid_int(self):
        assert safe_int(42) == 42
        assert safe_int("123") == 123
        assert safe_int("456") == 456

    def test_returns_none_for_invalid(self):
        assert safe_int(None) is None
        assert safe_int("abc") is None
        assert safe_int("") is None
        assert safe_int([]) is None

    def test_converts_float_to_int(self):
        assert safe_int(42.7) == 42
        assert safe_int(42.9) == 42


class TestSlug:
    """Tests for slug generation."""

    def test_basicslug(self):
        assert slug("Hello World") == "hello_world"
        assert slug("Jean-Paul Dupont") == "jean_paul_dupont"

    def test_removes_accents(self):
        assert slug("François Hollande") == "francois_hollande"

    def test_handles_special_chars(self):
        assert slug("Test@#$%123") == "test_123"
        assert slug("A B  C   D") == "a_b_c_d"

    def test_handles_empty_string(self):
        assert slug("") == "unknown"
        assert slug("   ") == "unknown"

    def test_multiple_underscores(self):
        assert slug("A___B") == "a_b"


class TestParseDate:
    """Tests for date parsing."""

    def test_parses_valid_date(self):
        result = parse_yyyy_mm_dd("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_returns_none_for_invalid_format(self):
        assert parse_yyyy_mm_dd("15/01/2024") is None
        assert parse_yyyy_mm_dd("2024-1-15") is None
        assert parse_yyyy_mm_dd("2024-13-01") is None
        assert parse_yyyy_mm_dd("abc") is None

    def test_returns_none_for_empty(self):
        assert parse_yyyy_mm_dd(None) is None
        assert parse_yyyy_mm_dd("") is None
        assert parse_yyyy_mm_dd("   ") is None


class TestNormalizeForMatch:
    """Tests for name normalization."""

    def test_normalizes_to_lowercase(self):
        assert normalize_for_match("JOHN DOE") == "john doe"

    def test_removes_accents(self):
        assert normalize_for_match("François Müller") == "francois muller"

    def test_collapses_whitespace(self):
        assert normalize_for_match("John   Doe") == "john doe"
        assert normalize_for_match("  John Doe  ") == "john doe"

    def test_handles_empty(self):
        assert normalize_for_match("") == ""
