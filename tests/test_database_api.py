"""
Unit tests for the Database API.

Run with: pytest tests/test_database_api.py -v
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.api import DatabaseAPI


@pytest.fixture
def api():
    """Create a DatabaseAPI instance for testing."""
    api = DatabaseAPI()
    yield api
    api.close()


class TestScientistMethods:
    """Test scientist-related API methods."""

    def test_get_all_scientists(self, api):
        """Test getting all scientists."""
        scientists = api.get_all_scientists(limit=10)
        assert len(scientists) > 0
        assert all(hasattr(s, "name") for s in scientists)
        assert all(hasattr(s, "scholar_id") for s in scientists)

    def test_search_scientists(self, api):
        """Test searching for scientists."""
        # Search for a known scientist
        results = api.search_scientists("philippe")
        assert len(results) > 0
        assert all("philippe" in s.name.lower() for s in results)

    def test_get_scientist_by_name(self, api):
        """Test getting a scientist by exact name."""
        # Get a known scientist
        scientist = api.get_scientist_by_name("Hervé Philippe")
        if scientist:  # Only test if this scientist exists
            assert scientist.name == "Hervé Philippe"
            assert hasattr(scientist, "publications_count")
            assert hasattr(scientist, "total_citations")

    def test_search_scientists_case_insensitive(self, api):
        """Test that search is case-insensitive."""
        results_lower = api.search_scientists("marie")
        results_upper = api.search_scientists("MARIE")
        # Should return same results regardless of case
        assert len(results_lower) == len(results_upper)

    def test_get_top_scientists_by_citations(self, api):
        """Test getting top scientists by citations."""
        top_scientists = api.get_top_scientists_by_citations(limit=5)
        if len(top_scientists) > 1:
            # Check that they are ordered by citations
            citations = [s.total_citations for s in top_scientists]
            assert citations == sorted(citations, reverse=True)


class TestPublicationMethods:
    """Test publication-related API methods."""

    def test_get_top_publications(self, api):
        """Test getting top publications."""
        top_pubs = api.get_top_publications(limit=5)
        assert len(top_pubs) > 0
        assert all(hasattr(p, "title") for p in top_pubs)
        assert all(hasattr(p, "cited_by") for p in top_pubs)

        # Check ordering
        if len(top_pubs) > 1:
            citations = [p.cited_by for p in top_pubs]
            assert citations == sorted(citations, reverse=True)

    def test_search_publications(self, api):
        """Test searching publications by title."""
        results = api.search_publications("muscle")
        # Should find at least some results (if there are publications with "muscle")
        assert isinstance(results, list)

    def test_get_publications_by_scientist(self, api):
        """Test getting publications for a scientist."""
        # First get a scientist that we know has publications
        scientist = api.get_scientist_by_name("Hervé Philippe")
        if scientist and scientist.publications_count > 0:
            pubs = api.get_publications_by_scientist(scientist.id)
            assert len(pubs) == scientist.publications_count
            assert all(hasattr(p, "title") for p in pubs)

    def test_get_publications_by_year(self, api):
        """Test getting publications by year."""
        pubs_2020 = api.get_publications_by_year(2020)
        if len(pubs_2020) > 0:
            assert all(p.year == 2020 for p in pubs_2020)


class TestInstitutionMethods:
    """Test institution-related API methods."""

    def test_get_all_institutions(self, api):
        """Test getting all institutions."""
        institutions = api.get_all_institutions()
        assert len(institutions) > 0
        assert all(hasattr(inst, "name") for inst in institutions)

    def test_search_institutions(self, api):
        """Test searching institutions."""
        results = api.search_institutions("university")
        # Should find institutions with "university" in name
        assert isinstance(results, list)

    def test_get_scientists_by_institution(self, api):
        """Test getting scientists by institution."""
        institutions = api.get_all_institutions()
        if len(institutions) > 0:
            first_inst = institutions[0]
            scientists = api.get_scientists_by_institution(first_inst.id)
            assert isinstance(scientists, list)


class TestStatisticsMethods:
    """Test statistics-related API methods."""

    def test_get_database_stats(self, api):
        """Test getting overall database statistics."""
        stats = api.get_database_stats()

        assert "scientists" in stats
        assert "publications" in stats
        assert "institutions" in stats
        assert "patents" in stats
        assert "api_calls" in stats

        # All counts should be non-negative
        assert all(count >= 0 for count in stats.values())

        # We know there should be some data
        assert stats["scientists"] > 0
        assert stats["publications"] > 0

    def test_get_publication_stats_by_year(self, api):
        """Test getting publication statistics by year."""
        stats = api.get_publication_stats_by_year()
        assert isinstance(stats, list)

        if len(stats) > 0:
            # Check structure of each stat
            for stat in stats:
                assert "year" in stat
                assert "count" in stat
                assert "avg_citations" in stat
                assert stat["count"] > 0


class TestExportMethods:
    """Test export-related API methods."""

    def test_export_scientist_to_dict(self, api):
        """Test exporting scientist data to dictionary."""
        # Get a scientist
        scientist = api.get_scientist_by_name("Hervé Philippe")
        if scientist:
            data = api.export_scientist_to_dict(scientist.id)

            assert "scientist" in data
            assert "publications" in data

            # Check scientist data
            sci_data = data["scientist"]
            assert "name" in sci_data
            assert "scholar_id" in sci_data
            assert "publications_count" in sci_data

            # Check publications data
            assert isinstance(data["publications"], list)

    def test_scientist_to_dict(self, api):
        """Test ScientistData to_dict method."""
        scientist = api.get_scientist_by_name("Hervé Philippe")
        if scientist:
            data = scientist.to_dict()

            required_keys = [
                "id",
                "name",
                "scholar_id",
                "affiliation",
                "publications_count",
                "total_citations",
                "institutions",
            ]

            for key in required_keys:
                assert key in data

    def test_publication_to_dict(self, api):
        """Test PublicationData to_dict method."""
        pubs = api.get_top_publications(limit=1)
        if len(pubs) > 0:
            pub = pubs[0]
            data = pub.to_dict()

            required_keys = ["id", "title", "cited_by", "year", "authors"]

            for key in required_keys:
                assert key in data


class TestContextManager:
    """Test context manager usage."""

    def test_context_manager(self):
        """Test using DatabaseAPI as a context manager."""
        with DatabaseAPI() as api:
            stats = api.get_database_stats()
            assert "scientists" in stats

        # API should be closed after exiting context


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_get_nonexistent_scientist(self, api):
        """Test getting a scientist that doesn't exist."""
        scientist = api.get_scientist_by_name("This Scientist Does Not Exist")
        assert scientist is None

    def test_search_empty_query(self, api):
        """Test searching with empty query."""
        results = api.search_scientists("")
        # Should return all scientists
        assert len(results) > 0

    def test_get_publications_for_scientist_without_pubs(self, api):
        """Test getting publications for scientist with no publications."""
        # Find a scientist with 0 publications
        scientists = api.get_all_scientists()
        scientist_without_pubs = next(
            (s for s in scientists if s.publications_count == 0), None
        )

        if scientist_without_pubs:
            pubs = api.get_publications_by_scientist(scientist_without_pubs.id)
            assert len(pubs) == 0


if __name__ == "__main__":
    # Run tests with: python tests/test_database_api.py
    pytest.main([__file__, "-v"])
