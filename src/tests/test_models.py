#!/usr/bin/env python3
"""Tests for data models."""
from src.models import (
    ScholarCandidate,
    ScholarPublication,
    ScholarData,
    PatentItem,
    PatentsData,
    CitingPatent,
)


class TestScholarCandidate:
    """Tests for ScholarCandidate model."""

    def test_creates_valid_candidate(self):
        candidate = ScholarCandidate(
            author_id="abc123",
            title="John Doe - MIT",
            link="https://scholar.google.com/citations?user=abc123",
            snippet="Professor of Computer Science"
        )
        assert candidate.author_id == "abc123"
        assert "MIT" in candidate.title
        assert "scholar.google.com" in candidate.link


class TestScholarPublication:
    """Tests for ScholarPublication model."""

    def test_creates_valid_publication(self):
        pub = ScholarPublication(
            title="Machine Learning Paper",
            link="https://scholar.google.com/paper",
            cited_by=150
        )
        assert pub.title == "Machine Learning Paper"
        assert pub.cited_by == 150

    def test_handles_none_citations(self):
        pub = ScholarPublication(
            title="Recent Paper",
            link="https://scholar.google.com/paper",
            cited_by=None
        )
        assert pub.cited_by is None


class TestScholarData:
    """Tests for ScholarData model."""

    def test_creates_valid_scholar_data(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="MIT",
            citations_total=5000,
            h_index=25,
            publications_total=100,
            top_publications=[]
        )
        assert scholar.author_id == "abc123"
        assert scholar.name == "John Doe"
        assert scholar.citations_total == 5000
        assert scholar.h_index == 25

    def test_handles_optional_fields(self):
        scholar = ScholarData(
            author_id="abc123",
            name="John Doe",
            affiliation="MIT",
            citations_total=None,
            h_index=None,
            publications_total=None,
            top_publications=[]
        )
        assert scholar.citations_total is None
        assert scholar.h_index is None


class TestPatentItem:
    """Tests for PatentItem model."""

    def test_creates_basic_patent(self):
        patent = PatentItem(
            title="Innovative Device",
            link="https://patents.google.com/patent/US123456",
            patent_id="US123456A1"
        )
        assert patent.title == "Innovative Device"
        assert patent.patent_id == "US123456A1"

    def test_creates_enriched_patent(self):
        patent = PatentItem(
            title="AI System",
            link="https://patents.google.com/patent/US789012",
            patent_id="US789012B2",
            publication_date="2024-01-15",
            filing_date="2023-01-15",
            current_assignee="Google LLC",
            claims_top3=["Claim 1", "Claim 2", "Claim 3"],
            cited_assignees=["Apple Inc.", "Microsoft Corp"],
            citing_assignees=["Tesla Inc.", "Amazon"],
            co_inventors=["Jane Smith", "Bob Wilson"]
        )
        assert patent.current_assignee == "Google LLC"
        assert len(patent.claims_top3) == 3
        assert len(patent.cited_assignees) == 2
        assert len(patent.co_inventors) == 2


class TestPatentsData:
    """Tests for PatentsData model."""

    def test_creates_valid_patents_data(self):
        patents = PatentsData(
            patents_total=10,
            top_patents=[
                PatentItem(title="Patent 1", link="link1"),
                PatentItem(title="Patent 2", link="link2")
            ]
        )
        assert patents.patents_total == 10
        assert len(patents.top_patents) == 2

    def test_handles_string_total(self):
        patents = PatentsData(
            patents_total="≥100",
            top_patents=[]
        )
        assert patents.patents_total == "≥100"


class TestCitingPatent:
    """Tests for CitingPatent model."""

    def test_creates_citing_patent(self):
        citing = CitingPatent(
            publication_number="US111222A1",
            link="https://patents.google.com/patent/US111222A1",
            assignee="Apple Inc.",
            publication_date="2024-06-01",
            filing_date="2023-06-01",
            priority_date="2023-01-01"
        )
        assert citing.publication_number == "US111222A1"
        assert citing.assignee == "Apple Inc."

    def test_handles_optional_fields(self):
        citing = CitingPatent(
            publication_number="US333444B2",
            link="https://patents.google.com/patent/US333444B2"
        )
        assert citing.assignee is None
        assert citing.publication_date is None
