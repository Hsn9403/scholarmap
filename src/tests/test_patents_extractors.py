#!/usr/bin/env python3
"""
Unit tests for patents extraction utilities.

Tests all extraction functions with various API response formats,
edge cases, and data quality scenarios.
"""


from src.patents.extractors import (
    extract_citing_patents,
    extract_cited_patents,
    extract_inventors,
    extract_top_claims,
    extract_cited_by_count,
    extract_assignees,
    extract_current_assignee,
    extract_dates,
    _split_names,
    _collect_assignees_from_block,
)
from src.models import CitingPatent, CitedPatent


# =============================================================================
# Test extract_citing_patents
# =============================================================================

class TestExtractCitingPatents:
    """Tests for extract_citing_patents function."""

    def test_extract_from_cited_by_key(self):
        """Test extraction from 'cited_by' key."""
        details = {
            "cited_by": [
                {
                    "publication_number": "US1234567",
                    "link": "https://patents.google.com/patent/US1234567",
                    "assignee": "Acme Corp",
                    "publication_date": "2023-01-15",
                    "filing_date": "2022-06-10",
                    "priority_date": "2021-12-01",
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert isinstance(result[0], CitingPatent)
        assert result[0].publication_number == "US1234567"
        assert result[0].link == "https://patents.google.com/patent/US1234567"
        assert result[0].assignee == "Acme Corp"
        assert result[0].publication_date == "2023-01-15"
        assert result[0].filing_date == "2022-06-10"
        assert result[0].priority_date == "2021-12-01"

    def test_extract_from_forward_citations_key(self):
        """Test extraction from 'forward_citations' fallback key."""
        details = {
            "forward_citations": [
                {
                    "publication": "EP9876543",
                    "link": "https://example.com/EP9876543",
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "EP9876543"
        assert result[0].link == "https://example.com/EP9876543"

    def test_extract_with_multiple_patents(self):
        """Test extraction with multiple citing patents."""
        details = {
            "cited_by": [
                {"publication_number": "US111", "link": "http://a.com"},
                {"publication_number": "US222", "link": "http://b.com"},
                {"publication_number": "US333", "link": "http://c.com"},
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 3
        assert result[0].publication_number == "US111"
        assert result[1].publication_number == "US222"
        assert result[2].publication_number == "US333"

    def test_extract_with_patent_id_fallback(self):
        """Test extraction when using 'patent_id' field."""
        details = {
            "cited_by": [
                {"patent_id": "WO2023012345"}
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "WO2023012345"

    def test_extract_with_optional_fields_missing(self):
        """Test extraction when optional fields are missing."""
        details = {
            "cited_by": [
                {
                    "publication_number": "US999",
                    # No assignee, no dates
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US999"
        assert result[0].assignee is None
        assert result[0].publication_date is None
        assert result[0].filing_date is None
        assert result[0].priority_date is None

    def test_extract_with_non_string_assignee(self):
        """Test extraction filters out non-string assignees."""
        details = {
            "cited_by": [
                {
                    "publication_number": "US555",
                    "assignee": {"name": "Complex Object"},  # Not a string
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].assignee is None

    def test_extract_with_non_string_dates(self):
        """Test extraction filters out non-string dates."""
        details = {
            "cited_by": [
                {
                    "publication_number": "US777",
                    "publication_date": 20230101,  # Not a string
                    "filing_date": ["2023-01-01"],  # Not a string
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_date is None
        assert result[0].filing_date is None

    def test_extract_empty_list(self):
        """Test extraction with empty cited_by list."""
        details = {"cited_by": []}

        result = extract_citing_patents(details)

        assert result == []

    def test_extract_missing_key(self):
        """Test extraction when no citation keys present."""
        details = {"other_field": "value"}

        result = extract_citing_patents(details)

        assert result == []

    def test_extract_non_list_value(self):
        """Test extraction when cited_by is not a list."""
        details = {"cited_by": "not a list"}

        result = extract_citing_patents(details)

        assert result == []

    def test_extract_with_non_dict_entries(self):
        """Test extraction skips non-dict entries in list."""
        details = {
            "cited_by": [
                "invalid entry",
                {"publication_number": "US123"},
                None,
                42,
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US123"

    def test_extract_with_empty_publication_number(self):
        """Test extraction skips entries with empty publication number."""
        details = {
            "cited_by": [
                {"publication_number": ""},  # Empty
                {"publication_number": "  "},  # Whitespace only
                {"link": "http://example.com"},  # Has link, no pub number
            ]
        }

        result = extract_citing_patents(details)

        # Only the one with link should be included
        assert len(result) == 1
        assert result[0].link == "http://example.com"

    def test_extract_with_whitespace_trimming(self):
        """Test extraction trims whitespace from fields."""
        details = {
            "cited_by": [
                {
                    "publication_number": "  US888  ",
                    "link": "  http://x.com  ",
                }
            ]
        }

        result = extract_citing_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US888"
        assert result[0].link == "http://x.com"


# =============================================================================
# Test extract_cited_patents
# =============================================================================

class TestExtractCitedPatents:
    """Tests for extract_cited_patents function (backward citations)."""

    def test_extract_from_patent_citations_key(self):
        """Test extraction from 'patent_citations' key."""
        details = {
            "patent_citations": [
                {
                    "publication_number": "US2002001856A1",
                    "link": "https://patents.google.com/patent/US2002001856A1",
                    "assignee": "Chow Andrea W",
                    "publication_date": "2002-01-03",
                    "filing_date": "2000-04-06",
                    "priority_date": "2000-04-06",
                }
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert isinstance(result[0], CitedPatent)
        assert result[0].publication_number == "US2002001856A1"
        assert result[0].link == "https://patents.google.com/patent/US2002001856A1"
        assert result[0].assignee == "Chow Andrea W"
        assert result[0].publication_date == "2002-01-03"
        assert result[0].filing_date == "2000-04-06"
        assert result[0].priority_date == "2000-04-06"

    def test_extract_from_citations_key(self):
        """Test extraction from 'citations' fallback key."""
        details = {
            "citations": [
                {
                    "publication": "EP1234567",
                    "link": "https://example.com/EP1234567",
                    "assignee": "Beta Inc",
                }
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "EP1234567"
        assert result[0].assignee == "Beta Inc"

    def test_extract_from_references_key(self):
        """Test extraction from 'references' fallback key."""
        details = {
            "references": [
                {
                    "patent_id": "WO2020012345",
                    "assignee_original": "Gamma Corp",
                }
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "WO2020012345"
        assert result[0].assignee == "Gamma Corp"

    def test_extract_with_multiple_cited_patents(self):
        """Test extraction with multiple cited patents."""
        details = {
            "patent_citations": [
                {"publication_number": "US111", "assignee": "Company A"},
                {"publication_number": "US222", "assignee": "John Doe"},
                {"publication_number": "US333", "assignee": "Company B"},
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 3
        assert result[0].assignee == "Company A"
        assert result[1].assignee == "John Doe"
        assert result[2].assignee == "Company B"

    def test_extract_from_nested_original_structure(self):
        """Test extraction from nested 'original' structure."""
        details = {
            "patent_citations": {
                "original": [
                    {
                        "publication_number": "US555",
                        "assignee_original": "Delta LLC",
                    }
                ]
            }
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US555"
        assert result[0].assignee == "Delta LLC"

    def test_extract_from_nested_family_to_family(self):
        """Test extraction from nested 'family_to_family' structure."""
        details = {
            "patent_citations": {
                "family_to_family": [
                    {
                        "publication_number": "US666",
                        "assignee": "Epsilon Inc",
                    }
                ]
            }
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US666"
        assert result[0].assignee == "Epsilon Inc"

    def test_extract_with_missing_assignee(self):
        """Test extraction when assignee is missing."""
        details = {
            "patent_citations": [
                {
                    "publication_number": "US777",
                    "link": "http://example.com",
                }
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US777"
        assert result[0].assignee is None

    def test_extract_with_empty_block(self):
        """Test extraction with empty citations block."""
        details = {"patent_citations": []}

        result = extract_cited_patents(details)

        assert len(result) == 0

    def test_extract_with_no_citations_key(self):
        """Test extraction when no citations key exists."""
        details = {"some_other_key": "value"}

        result = extract_cited_patents(details)

        assert len(result) == 0

    def test_extract_ignores_entries_without_publication_or_link(self):
        """Test that entries without publication number or link are ignored."""
        details = {
            "patent_citations": [
                {"assignee": "Company X"},  # No publication number or link
                {"publication_number": "US888", "assignee": "Company Y"},  # Valid
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US888"

    def test_extract_with_whitespace_trimming(self):
        """Test that whitespace is properly trimmed."""
        details = {
            "patent_citations": [
                {
                    "publication_number": "  US999  ",
                    "assignee": "  Acme Corp  ",
                    "link": "  http://x.com  ",
                }
            ]
        }

        result = extract_cited_patents(details)

        assert len(result) == 1
        assert result[0].publication_number == "US999"
        assert result[0].link == "http://x.com"


# =============================================================================
# Test extract_inventors
# =============================================================================

class TestExtractInventors:
    """Tests for extract_inventors function."""

    def test_extract_from_string_comma_separated(self):
        """Test extraction from comma-separated string."""
        details = {"inventors": "John Smith, Jane Doe, Bob Lee"}

        result = extract_inventors(details)

        assert len(result) == 3
        assert "John Smith" in result
        assert "Jane Doe" in result
        assert "Bob Lee" in result

    def test_extract_from_string_semicolon_separated(self):
        """Test extraction from semicolon-separated string."""
        details = {"inventors": "Alice Brown; Charlie Green; Diana White"}

        result = extract_inventors(details)

        assert len(result) == 3
        assert "Alice Brown" in result
        assert "Charlie Green" in result

    def test_extract_from_string_and_separated(self):
        """Test extraction from 'and'-separated string."""
        details = {"inventors": "Tom Jones and Mary Wilson"}

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Tom Jones" in result
        assert "Mary Wilson" in result

    def test_extract_from_list_of_strings(self):
        """Test extraction from list of strings."""
        details = {"inventors": ["Emma Davis", "Frank Miller", "Grace Taylor"]}

        result = extract_inventors(details)

        assert len(result) == 3
        assert "Emma Davis" in result
        assert "Frank Miller" in result
        assert "Grace Taylor" in result

    def test_extract_from_list_of_dicts_with_name(self):
        """Test extraction from list of dicts with 'name' key."""
        details = {
            "inventors": [
                {"name": "Henry Johnson"},
                {"name": "Isabella Martinez"},
            ]
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Henry Johnson" in result
        assert "Isabella Martinez" in result

    def test_extract_from_list_of_dicts_with_inventor_key(self):
        """Test extraction from list of dicts with 'inventor' key."""
        details = {
            "inventors": [
                {"inventor": "Kevin Anderson"},
                {"inventor": "Laura Tristan"},
            ]
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Kevin Anderson" in result
        assert "Laura Tristan" in result

    def test_extract_from_list_of_dicts_with_full_name_key(self):
        """Test extraction from list of dicts with 'full_name' key."""
        details = {
            "inventors": [
                {"full_name": "Michael Jackson"},
                {"full_name": "Nancy Lee"},
            ]
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Michael Jackson" in result
        assert "Nancy Lee" in result

    def test_extract_from_dict_with_name(self):
        """Test extraction from dict format."""
        details = {"inventors": {"name": "Oliver Garcia"}}

        result = extract_inventors(details)

        assert len(result) == 1
        assert "Oliver Garcia" in result

    def test_extract_from_dict_with_name_list(self):
        """Test extraction from dict with name as list."""
        details = {
            "inventors": {
                "name": ["Patricia Rodriguez", "Quinn Harris"]
            }
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Patricia Rodriguez" in result
        assert "Quinn Harris" in result

    def test_extract_with_inventor_fallback_key(self):
        """Test extraction using 'inventor' singular fallback key."""
        details = {"inventor": "Rachel Clark"}

        result = extract_inventors(details)

        assert len(result) == 1
        assert "Rachel Clark" in result

    def test_extract_deduplicates_inventors(self):
        """Test extraction deduplicates inventors while preserving order."""
        details = {
            "inventors": "Sam Lewis, Tina Walker, Sam Lewis, Uma Hall"
        }

        result = extract_inventors(details)

        assert len(result) == 3
        assert result[0] == "Sam Lewis"
        assert result[1] == "Tina Walker"
        assert result[2] == "Uma Hall"

    def test_extract_normalizes_names(self):
        """Test extraction normalizes names (strips extra whitespace)."""
        details = {
            "inventors": [
                "  Victor   Young  ",
                "Wendy   King  ",
            ]
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Victor Young" in result
        assert "Wendy King" in result

    def test_extract_empty_string(self):
        """Test extraction with empty string."""
        details = {"inventors": ""}

        result = extract_inventors(details)

        assert result == []

    def test_extract_empty_list(self):
        """Test extraction with empty list."""
        details = {"inventors": []}

        result = extract_inventors(details)

        assert result == []

    def test_extract_missing_key(self):
        """Test extraction when inventors key is missing."""
        details = {"other_field": "value"}

        result = extract_inventors(details)

        assert result == []

    def test_extract_skips_empty_strings_in_list(self):
        """Test extraction skips empty strings in list."""
        details = {
            "inventors": ["Xavier Scott", "", "  ", "Yolanda Adams"]
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Xavier Scott" in result
        assert "Yolanda Adams" in result

    def test_extract_mixed_list_formats(self):
        """Test extraction handles mixed list formats."""
        details = {
            "inventors": [
                "Zachary Nelson",
                {"name": "Amy Carter"},
                "",
                {"inventor": "Brian Moore"},
            ]
        }

        result = extract_inventors(details)

        assert len(result) == 3
        assert "Zachary Nelson" in result
        assert "Amy Carter" in result
        assert "Brian Moore" in result

    def test_deep_scan_fallback(self):
        """Test deep scan fallback finds inventors in nested structure."""
        details = {
            "patent_info": {
                "metadata": {
                    "inventors": ["Carol White", "David Black"]
                }
            }
        }

        result = extract_inventors(details)

        assert len(result) == 2
        assert "Carol White" in result
        assert "David Black" in result


# =============================================================================
# Test extract_top_claims
# =============================================================================

class TestExtractTopClaims:
    """Tests for extract_top_claims function."""

    def test_extract_default_three_claims(self):
        """Test extraction of default 3 claims."""
        details = {
            "claims": [
                "Claim 1: A method for...",
                "Claim 2: The method of claim 1...",
                "Claim 3: An apparatus comprising...",
                "Claim 4: The apparatus of claim 3...",
            ]
        }

        result = extract_top_claims(details)

        assert len(result) == 3
        assert result[0] == "Claim 1: A method for..."
        assert result[1] == "Claim 2: The method of claim 1..."
        assert result[2] == "Claim 3: An apparatus comprising..."

    def test_extract_custom_n_claims(self):
        """Test extraction of custom N claims."""
        details = {
            "claims": [
                "Claim A",
                "Claim B",
                "Claim C",
                "Claim D",
            ]
        }

        result = extract_top_claims(details, n=2)

        assert len(result) == 2
        assert result[0] == "Claim A"
        assert result[1] == "Claim B"

    def test_extract_fewer_claims_than_requested(self):
        """Test extraction when fewer claims available than requested."""
        details = {"claims": ["Only one claim"]}

        result = extract_top_claims(details, n=5)

        assert len(result) == 1
        assert result[0] == "Only one claim"

    def test_extract_empty_claims_list(self):
        """Test extraction with empty claims list."""
        details = {"claims": []}

        result = extract_top_claims(details)

        assert result == []

    def test_extract_missing_claims_key(self):
        """Test extraction when claims key is missing."""
        details = {"other_field": "value"}

        result = extract_top_claims(details)

        assert result == []

    def test_extract_non_list_claims(self):
        """Test extraction when claims is not a list."""
        details = {"claims": "Not a list"}

        result = extract_top_claims(details)

        assert result == []

    def test_extract_skips_none_values(self):
        """Test extraction skips None values in claims."""
        details = {
            "claims": [
                "Valid claim 1",
                None,
                "Valid claim 2",
                None,
            ]
        }

        result = extract_top_claims(details, n=4)

        assert len(result) == 2
        assert result[0] == "Valid claim 1"
        assert result[1] == "Valid claim 2"

    def test_extract_converts_non_string_to_string(self):
        """Test extraction converts non-string claims to string."""
        details = {
            "claims": [
                123,
                {"claim": "complex"},
                ["list", "claim"],
            ]
        }

        result = extract_top_claims(details)

        assert len(result) == 3
        assert result[0] == "123"
        assert "claim" in result[1]
        assert "list" in result[2]

    def test_extract_strips_whitespace(self):
        """Test extraction strips whitespace from claims."""
        details = {
            "claims": [
                "  Claim with spaces  ",
                "\n\nClaim with newlines\n\n",
            ]
        }

        result = extract_top_claims(details)

        assert len(result) == 2
        assert result[0] == "Claim with spaces"
        assert result[1] == "Claim with newlines"

    def test_extract_skips_empty_string_claims(self):
        """Test extraction skips empty string claims after stripping."""
        details = {
            "claims": [
                "Valid claim",
                "   ",
                "",
                "Another valid claim",
            ]
        }

        result = extract_top_claims(details, n=4)

        assert len(result) == 2
        assert result[0] == "Valid claim"
        assert result[1] == "Another valid claim"


# =============================================================================
# Test extract_cited_by_count
# =============================================================================

class TestExtractCitedByCount:
    """Tests for extract_cited_by_count function."""

    def test_extract_from_patent_citations_dict_total(self):
        """Test extraction from patent_citations.total."""
        details = {"patent_citations": {"total": 42}}

        result = extract_cited_by_count(details)

        assert result == 42

    def test_extract_from_patent_citations_dict_value(self):
        """Test extraction from patent_citations.value."""
        details = {"patent_citations": {"value": 33}}

        result = extract_cited_by_count(details)

        assert result == 33

    def test_extract_from_patent_citations_int(self):
        """Test extraction from patent_citations as int."""
        details = {"patent_citations": 25}

        result = extract_cited_by_count(details)

        assert result == 25

    def test_extract_from_patent_citations_string(self):
        """Test extraction from patent_citations as string."""
        details = {"patent_citations": "18"}

        result = extract_cited_by_count(details)

        assert result == 18

    def test_extract_from_citations_fallback(self):
        """Test extraction from citations fallback key."""
        details = {"citations": {"total": 12}}

        result = extract_cited_by_count(details)

        assert result == 12

    def test_extract_from_citations_int(self):
        """Test extraction from citations as int."""
        details = {"citations": 7}

        result = extract_cited_by_count(details)

        assert result == 7

    def test_extract_from_citations_string(self):
        """Test extraction from citations as string."""
        details = {"citations": "9"}

        result = extract_cited_by_count(details)

        assert result == 9

    def test_extract_missing_keys(self):
        """Test extraction returns None when keys missing."""
        details = {"other_field": "value"}

        result = extract_cited_by_count(details)

        assert result is None

    def test_extract_invalid_value(self):
        """Test extraction returns None for invalid value."""
        details = {"patent_citations": "not a number"}

        result = extract_cited_by_count(details)

        assert result is None

    def test_extract_zero_citations(self):
        """Test extraction returns 0 for zero citations."""
        details = {"patent_citations": 0}

        result = extract_cited_by_count(details)

        assert result == 0

    def test_extract_prefers_patent_citations_over_citations(self):
        """Test extraction prefers patent_citations over citations."""
        details = {
            "patent_citations": 50,
            "citations": 100,
        }

        result = extract_cited_by_count(details)

        assert result == 50


# =============================================================================
# Test extract_assignees
# =============================================================================

class TestExtractAssignees:
    """Tests for extract_assignees function."""

    def test_extract_cited_and_citing_assignees(self):
        """Test extraction of both cited and citing assignees."""
        details = {
            "patent_citations": [
                {"assignee": "Acme Corp"},
                {"assignee": "Beta Inc"},
            ],
            "cited_by": [
                {"assignee": "Gamma LLC"},
                {"assignee": "Delta Co"},
            ],
        }

        cited, citing = extract_assignees(details)

        assert len(cited) == 2
        assert "Acme Corp" in cited
        assert "Beta Inc" in cited

        assert len(citing) == 2
        assert "Gamma LLC" in citing
        assert "Delta Co" in citing

    def test_extract_from_alternative_keys(self):
        """Test extraction from alternative fallback keys."""
        details = {
            "references": [{"assignee": "Ref Corp"}],
            "forward_citations": [{"assignee": "Fwd Corp"}],
        }

        cited, citing = extract_assignees(details)

        assert "Ref Corp" in cited
        assert "Fwd Corp" in citing

    def test_extract_deduplicates_assignees(self):
        """Test extraction deduplicates assignees."""
        details = {
            "patent_citations": [
                {"assignee": "Acme Corp"},
                {"assignee": "Beta Inc"},
                {"assignee": "Acme Corp"},  # Duplicate
            ],
        }

        cited, citing = extract_assignees(details)

        assert len(cited) == 2
        assert cited[0] == "Acme Corp"
        assert cited[1] == "Beta Inc"

    def test_extract_empty_blocks(self):
        """Test extraction with empty blocks."""
        details = {
            "patent_citations": [],
            "cited_by": [],
        }

        cited, citing = extract_assignees(details)

        assert cited == []
        assert citing == []

    def test_extract_missing_keys(self):
        """Test extraction when keys are missing."""
        details = {}

        cited, citing = extract_assignees(details)

        assert cited == []
        assert citing == []


# =============================================================================
# Test extract_current_assignee
# =============================================================================

class TestExtractCurrentAssignee:
    """Tests for extract_current_assignee function."""

    def test_extract_from_assignee_key(self):
        """Test extraction from 'assignee' key."""
        details = {"assignee": "Acme Corporation"}

        result = extract_current_assignee(details)

        assert result == "Acme Corporation"

    def test_extract_from_current_assignee_key(self):
        """Test extraction from 'current_assignee' key."""
        details = {"current_assignee": "Beta Industries"}

        result = extract_current_assignee(details)

        assert result == "Beta Industries"

    def test_extract_from_owner_key(self):
        """Test extraction from 'owner' fallback key."""
        details = {"owner": "Gamma LLC"}

        result = extract_current_assignee(details)

        assert result == "Gamma LLC"

    def test_extract_prefers_assignee_over_owner(self):
        """Test extraction prefers assignee over owner."""
        details = {
            "assignee": "Preferred Corp",
            "owner": "Fallback Corp",
        }

        result = extract_current_assignee(details)

        assert result == "Preferred Corp"

    def test_extract_missing_all_keys(self):
        """Test extraction returns empty string when all keys missing."""
        details = {"other_field": "value"}

        result = extract_current_assignee(details)

        assert result == ""

    def test_extract_empty_string_value(self):
        """Test extraction with empty string value."""
        details = {"assignee": ""}

        result = extract_current_assignee(details)

        assert result == ""


# =============================================================================
# Test extract_dates
# =============================================================================

class TestExtractDates:
    """Tests for extract_dates function."""

    def test_extract_all_dates(self):
        """Test extraction of all date fields."""
        details = {
            "publication_date": "2023-01-15",
            "filing_date": "2022-06-10",
            "priority_date": "2021-12-01",
        }

        result = extract_dates(details)

        assert result["publication_date"] == "2023-01-15"
        assert result["filing_date"] == "2022-06-10"
        assert result["priority_date"] == "2021-12-01"

    def test_extract_with_fallback_keys(self):
        """Test extraction using fallback keys."""
        details = {
            "published": "2023-02-20",
            "filed": "2022-07-15",
            "priority": "2021-11-30",
        }

        result = extract_dates(details)

        assert result["publication_date"] == "2023-02-20"
        assert result["filing_date"] == "2022-07-15"
        assert result["priority_date"] == "2021-11-30"

    def test_extract_prefers_primary_keys(self):
        """Test extraction prefers primary keys over fallbacks."""
        details = {
            "publication_date": "2023-03-01",
            "published": "2023-03-15",  # Fallback should be ignored
        }

        result = extract_dates(details)

        assert result["publication_date"] == "2023-03-01"

    def test_extract_missing_dates(self):
        """Test extraction with missing dates returns None."""
        details = {}

        result = extract_dates(details)

        assert result["publication_date"] is None
        assert result["filing_date"] is None
        assert result["priority_date"] is None

    def test_extract_partial_dates(self):
        """Test extraction with only some dates available."""
        details = {"filing_date": "2022-08-20"}

        result = extract_dates(details)

        assert result["publication_date"] is None
        assert result["filing_date"] == "2022-08-20"
        assert result["priority_date"] is None


# =============================================================================
# Test _split_names (private helper)
# =============================================================================

class TestSplitNames:
    """Tests for _split_names helper function."""

    def test_split_comma_separated(self):
        """Test splitting comma-separated names."""
        result = _split_names("John Smith, Jane Doe, Bob Lee")

        assert len(result) == 3
        assert "John Smith" in result
        assert "Jane Doe" in result
        assert "Bob Lee" in result

    def test_split_semicolon_separated(self):
        """Test splitting semicolon-separated names."""
        result = _split_names("Alice; Bob; Carol")

        assert len(result) == 3
        assert "Alice" in result
        assert "Bob" in result

    def test_split_and_separated(self):
        """Test splitting 'and'-separated names."""
        result = _split_names("Tom and Jerry")

        assert len(result) == 2
        assert "Tom" in result
        assert "Jerry" in result

    def test_split_et_separated_french(self):
        """Test splitting 'et'-separated names (French)."""
        result = _split_names("Paul et Marie")

        assert len(result) == 2
        assert "Paul" in result
        assert "Marie" in result

    def test_split_mixed_delimiters(self):
        """Test splitting with mixed delimiters."""
        result = _split_names("Alice, Bob and Carol; David")

        assert len(result) == 4

    def test_split_empty_string(self):
        """Test splitting empty string."""
        result = _split_names("")

        assert result == []

    def test_split_normalizes_whitespace(self):
        """Test splitting normalizes extra whitespace."""
        result = _split_names("  John   Smith  ,  Jane   Doe  ")

        assert len(result) == 2
        assert "John Smith" in result
        assert "Jane Doe" in result


# =============================================================================
# Test _collect_assignees_from_block (private helper)
# =============================================================================

class TestCollectAssigneesFromBlock:
    """Tests for _collect_assignees_from_block helper function."""

    def test_collect_from_list_of_dicts(self):
        """Test collection from list of dicts."""
        block = [
            {"assignee": "Acme Corp"},
            {"assignee": "Beta Inc"},
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 2
        assert "Acme Corp" in result
        assert "Beta Inc" in result

    def test_collect_from_nested_original(self):
        """Test collection from nested 'original' structure."""
        block = {
            "original": [
                {"assignee_original": "Gamma LLC"},
                {"assignee_original": "Delta Co"},
            ]
        }

        result = _collect_assignees_from_block(block)

        assert len(result) == 2
        assert "Gamma LLC" in result
        assert "Delta Co" in result

    def test_collect_from_nested_family_to_family(self):
        """Test collection from nested 'family_to_family' structure."""
        block = {
            "family_to_family": [
                {"assignee": "Epsilon Inc"},
            ]
        }

        result = _collect_assignees_from_block(block)

        assert len(result) == 1
        assert "Epsilon Inc" in result

    def test_collect_handles_multiple_field_names(self):
        """Test collection tries multiple field names for assignee."""
        block = [
            {"assignee": "A Corp"},
            {"assignee_original": "B Corp"},
            {"current_assignee": "C Corp"},
            {"owner": "D Corp"},
            {"applicant": "E Corp"},
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 5

    def test_collect_assignee_as_list(self):
        """Test collection when assignee field is a list."""
        block = [
            {"assignee": ["Multi Corp 1", "Multi Corp 2"]},
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 2
        assert "Multi Corp 1" in result
        assert "Multi Corp 2" in result

    def test_collect_assignee_as_list_of_dicts(self):
        """Test collection when assignee is list of dicts with 'name'."""
        block = [
            {
                "assignee": [
                    {"name": "Complex Corp 1"},
                    {"name": "Complex Corp 2"},
                ]
            },
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 2
        assert "Complex Corp 1" in result
        assert "Complex Corp 2" in result

    def test_collect_skips_non_dict_entries(self):
        """Test collection skips non-dict entries."""
        block = [
            {"assignee": "Valid Corp"},
            "invalid entry",
            None,
            42,
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 1
        assert "Valid Corp" in result

    def test_collect_skips_empty_strings(self):
        """Test collection skips empty assignee strings."""
        block = [
            {"assignee": "Valid Corp"},
            {"assignee": ""},
            {"assignee": "   "},
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 1
        assert "Valid Corp" in result

    def test_collect_normalizes_whitespace(self):
        """Test collection normalizes whitespace in assignee names."""
        block = [
            {"assignee": "  Acme   Corporation  "},
        ]

        result = _collect_assignees_from_block(block)

        assert len(result) == 1
        assert "Acme Corporation" in result

    def test_collect_empty_block(self):
        """Test collection with empty block."""
        result = _collect_assignees_from_block([])

        assert result == []

    def test_collect_none_block(self):
        """Test collection with None block."""
        result = _collect_assignees_from_block(None)

        assert result == []
