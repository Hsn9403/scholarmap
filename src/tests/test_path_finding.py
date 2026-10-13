#!/usr/bin/env python3
"""
Tests for path-finding module (schema, finder, scorer, explainer).

Tests the graph path analysis system for discovering and scoring
relationships between researchers and organizations.
"""
import pytest
from unittest.mock import Mock

from src.graph.path_finding import (
    # Schema
    EvidenceLevel,
    Hypothesis,
    PathPattern,
    H1_DIRECT_ASSIGNEE,
    H1_CURRENT_AFFILIATION,
    H2_CITED_BY_COMPANY,
    H3_CITES_COMPANY,
    ALL_PATTERNS,
    get_pattern,
    get_patterns_for_hypothesis,
    # PathFinder
    GraphIndex,
    PathFinder,
    FoundPath,
    find_paths,
    # Scorer
    PathScorer,
    ScoredPath,
    TargetScore,
    score_and_rank,
    # Explainer
    PathExplainer,
    explain_paths,
    explain_targets,
)


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def simple_graph():
    """
    Simple graph for testing:
    - Seed person (person:seed)
    - 1 patent (patent:p1)
    - 1 organization (org:company)
    - Edges: seed -> has_patent -> p1 -> assigned_to -> company
    """
    return {
        "meta": {
            "seed_person_id": "person:seed",
            "generated_at": "2024-01-01T00:00:00",
        },
        "nodes": [
            {"id": "person:seed", "type": "person", "label": "Seed Person"},
            {"id": "patent:p1", "type": "patent", "label": "Patent 1"},
            {"id": "org:company", "type": "corporate", "label": "Test Company"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "person:seed",
                "target": "patent:p1",
                "type": "has_patent",
                "weight": 1,
            },
            {
                "id": "e2",
                "source": "patent:p1",
                "target": "org:company",
                "type": "assigned_to",
                "weight": 1,
            },
        ],
    }


@pytest.fixture
def complex_graph():
    """
    Complex graph with multiple paths:
    - Seed -> Patent1 -> assigned_to -> Company
    - Seed -> Patent2 -> cites -> Company
    - Seed -> affiliated_with -> University
    """
    return {
        "meta": {
            "seed_person_id": "person:seed",
            "generated_at": "2024-01-01T00:00:00",
        },
        "nodes": [
            {"id": "person:seed", "type": "person", "label": "Seed Person"},
            {"id": "patent:p1", "type": "patent", "label": "Patent 1"},
            {"id": "patent:p2", "type": "patent", "label": "Patent 2"},
            {"id": "org:company", "type": "corporate", "label": "Test Company"},
            {"id": "org:university", "type": "institution", "label": "Test University"},
        ],
        "edges": [
            {
                "source": "person:seed",
                "target": "patent:p1",
                "type": "has_patent",
                "weight": 1,
            },
            {
                "source": "patent:p1",
                "target": "org:company",
                "type": "assigned_to",
                "weight": 1,
            },
            {
                "source": "person:seed",
                "target": "patent:p2",
                "type": "has_patent",
                "weight": 1,
            },
            {
                "source": "patent:p2",
                "target": "org:company",
                "type": "cites",
                "weight": 1,
            },
            {
                "source": "person:seed",
                "target": "org:university",
                "type": "affiliated_with",
                "weight": 1,
            },
        ],
    }


# =============================================================================
# Schema Tests
# =============================================================================

class TestSchema:
    """Tests for pattern schema definitions."""

    def test_evidence_levels_exist(self):
        """Evidence levels are properly defined."""
        assert EvidenceLevel.HARD.value == "hard"
        assert EvidenceLevel.MEDIUM.value == "medium"
        assert EvidenceLevel.SOFT.value == "soft"

    def test_hypothesis_levels_exist(self):
        """Hypothesis levels are properly defined."""
        assert Hypothesis.H1.value == "H1"
        assert Hypothesis.H2.value == "H2"
        assert Hypothesis.H3.value == "H3"

    def test_all_patterns_registered(self):
        """All patterns are in ALL_PATTERNS registry."""
        assert len(ALL_PATTERNS) == 7
        pattern_ids = {p.pattern_id for p in ALL_PATTERNS}
        assert "H1_direct_assignee" in pattern_ids
        assert "H1_current_affiliation" in pattern_ids
        assert "H2_cited_by_company" in pattern_ids
        assert "H3_cites_company" in pattern_ids

    def test_get_pattern_by_id(self):
        """get_pattern() returns correct pattern."""
        pattern = get_pattern("H1_direct_assignee")
        assert pattern is not None
        assert pattern.pattern_id == "H1_direct_assignee"
        assert pattern.hypothesis == Hypothesis.H1
        assert pattern.evidence_level == EvidenceLevel.HARD

    def test_get_patterns_for_hypothesis(self):
        """get_patterns_for_hypothesis() filters correctly."""
        h1_patterns = get_patterns_for_hypothesis(Hypothesis.H1)
        assert len(h1_patterns) == 2
        assert all(p.hypothesis == Hypothesis.H1 for p in h1_patterns)

        h2_patterns = get_patterns_for_hypothesis(Hypothesis.H2)
        assert all(p.hypothesis == Hypothesis.H2 for p in h2_patterns)

    def test_pattern_has_edge_sequence(self):
        """Patterns define valid edge sequences."""
        pattern = H1_DIRECT_ASSIGNEE
        assert len(pattern.edge_sequence) == 2
        assert pattern.edge_sequence[0] == ("has_patent", "out")
        assert pattern.edge_sequence[1] == ("assigned_to", "out")

    def test_pattern_path_length_property(self):
        """PathPattern.path_length returns edge count."""
        assert H1_DIRECT_ASSIGNEE.path_length == 2
        assert H1_CURRENT_AFFILIATION.path_length == 1


# =============================================================================
# GraphIndex Tests
# =============================================================================

class TestGraphIndex:
    """Tests for graph indexing."""

    def test_builds_node_index(self, simple_graph):
        """GraphIndex indexes all nodes by ID."""
        index = GraphIndex(simple_graph)
        assert len(index.nodes_by_id) == 3
        assert "person:seed" in index.nodes_by_id
        assert "patent:p1" in index.nodes_by_id
        assert "org:company" in index.nodes_by_id

    def test_builds_outgoing_edge_index(self, simple_graph):
        """GraphIndex indexes outgoing edges."""
        index = GraphIndex(simple_graph)
        outgoing = index.get_outgoing_edges("person:seed")
        assert len(outgoing) == 1
        assert outgoing[0]["target"] == "patent:p1"

    def test_builds_incoming_edge_index(self, simple_graph):
        """GraphIndex indexes incoming edges."""
        index = GraphIndex(simple_graph)
        incoming = index.get_incoming_edges("patent:p1")
        assert len(incoming) == 1
        assert incoming[0]["source"] == "person:seed"

    def test_filters_edges_by_type(self, simple_graph):
        """get_outgoing_edges filters by edge type."""
        index = GraphIndex(simple_graph)
        has_patent_edges = index.get_outgoing_edges("person:seed", "has_patent")
        assert len(has_patent_edges) == 1

        assigned_to_edges = index.get_outgoing_edges("person:seed", "assigned_to")
        assert len(assigned_to_edges) == 0

    def test_get_node_returns_node_dict(self, simple_graph):
        """get_node() returns node dictionary."""
        index = GraphIndex(simple_graph)
        node = index.get_node("person:seed")
        assert node is not None
        assert node["type"] == "person"
        assert node["label"] == "Seed Person"


# =============================================================================
# PathFinder Tests
# =============================================================================

class TestPathFinder:
    """Tests for path discovery."""

    def test_finds_h1_direct_assignee_path(self, simple_graph):
        """Finds H1 direct assignee pattern."""
        finder = PathFinder(simple_graph)
        paths = finder.find_all_paths([H1_DIRECT_ASSIGNEE])

        assert len(paths) == 1
        path = paths[0]
        assert path.pattern.pattern_id == "H1_direct_assignee"
        assert path.target_id == "org:company"
        assert path.path_length == 2

    def test_finds_h1_current_affiliation_path(self, complex_graph):
        """Finds H1 current affiliation pattern."""
        finder = PathFinder(complex_graph)
        paths = finder.find_all_paths([H1_CURRENT_AFFILIATION])

        assert len(paths) == 1
        path = paths[0]
        assert path.pattern.pattern_id == "H1_current_affiliation"
        assert path.target_id == "org:university"
        assert path.path_length == 1

    def test_finds_multiple_paths_to_same_target(self, complex_graph):
        """Finds multiple paths to same organization."""
        finder = PathFinder(complex_graph)
        paths = finder.find_all_paths([H1_DIRECT_ASSIGNEE, H3_CITES_COMPANY])

        # Should find 2 paths to company (assigned_to + cites)
        company_paths = [p for p in paths if p.target_id == "org:company"]
        assert len(company_paths) == 2

        pattern_ids = {p.pattern.pattern_id for p in company_paths}
        assert "H1_direct_assignee" in pattern_ids
        assert "H3_cites_company" in pattern_ids

    def test_calculates_raw_score_from_edge_weights(self, simple_graph):
        """Raw score is calculated from edge weights."""
        # Modify edge weight
        simple_graph["edges"][0]["weight"] = 5

        finder = PathFinder(simple_graph)
        paths = finder.find_all_paths([H1_DIRECT_ASSIGNEE])

        assert len(paths) == 1
        # Raw score should reflect edge weights and pattern factors
        assert paths[0].raw_score > 0

    def test_find_paths_to_target_filters_correctly(self, complex_graph):
        """find_paths_to_target() filters by target ID."""
        finder = PathFinder(complex_graph)
        paths = finder.find_paths_to_target("org:company")

        assert all(p.target_id == "org:company" for p in paths)
        # Should not include university paths
        assert not any(p.target_id == "org:university" for p in paths)

    def test_convenience_function_find_paths(self, simple_graph):
        """Convenience function find_paths() works."""
        paths = find_paths(simple_graph)
        assert isinstance(paths, list)
        assert len(paths) > 0


# =============================================================================
# PathScorer Tests
# =============================================================================

class TestPathScorer:
    """Tests for path scoring."""

    def test_scores_h1_higher_than_h3(self):
        """H1 paths score higher than H3 paths."""
        scorer = PathScorer()

        # Create mock paths
        h1_path = Mock(
            pattern=H1_DIRECT_ASSIGNEE,
            path_length=2,
            raw_score=1.0,
        )
        h3_path = Mock(
            pattern=H3_CITES_COMPANY,
            path_length=2,
            raw_score=1.0,
        )

        h1_scored = scorer.score_path(h1_path)
        h3_scored = scorer.score_path(h3_path)

        assert h1_scored.final_score > h3_scored.final_score

    def test_score_decreases_with_path_length(self):
        """Longer paths score lower."""
        scorer = PathScorer()

        short_path = Mock(
            pattern=H1_DIRECT_ASSIGNEE,
            path_length=1,
            raw_score=0,
        )
        long_path = Mock(
            pattern=H1_DIRECT_ASSIGNEE,
            path_length=3,
            raw_score=0,
        )

        short_scored = scorer.score_path(short_path)
        long_scored = scorer.score_path(long_path)

        assert short_scored.final_score > long_scored.final_score

    def test_aggregates_paths_by_target(self, complex_graph):
        """aggregate_by_target() groups paths correctly."""
        finder = PathFinder(complex_graph)
        paths = finder.find_all_paths()

        scorer = PathScorer()
        scored_paths = scorer.score_paths(paths)
        targets = scorer.aggregate_by_target(scored_paths)

        # Should have 2 targets (company + university)
        assert len(targets) == 2

        # Company should have multiple paths
        company_target = next(t for t in targets if "company" in t.target_label.lower())
        assert company_target.path_count >= 2
        assert company_target.total_score > 0

    def test_target_score_tracks_best_hypothesis(self, complex_graph):
        """TargetScore tracks best hypothesis level."""
        finder = PathFinder(complex_graph)
        paths = finder.find_all_paths()

        scorer = PathScorer()
        scored_paths = scorer.score_paths(paths)
        targets = scorer.aggregate_by_target(scored_paths)

        company_target = next(t for t in targets if "company" in t.target_label.lower())
        # Should have H1 as best (from direct_assignee)
        assert company_target.best_hypothesis == Hypothesis.H1

    def test_convenience_function_score_and_rank(self, simple_graph):
        """Convenience function score_and_rank() works."""
        paths = find_paths(simple_graph)
        targets = score_and_rank(paths)

        assert isinstance(targets, list)
        assert len(targets) > 0
        assert all(isinstance(t, TargetScore) for t in targets)


# =============================================================================
# PathExplainer Tests
# =============================================================================

class TestPathExplainer:
    """Tests for explanation generation."""

    def test_explains_path_with_narrative(self, simple_graph):
        """PathExplainer generates narrative for path."""
        paths = find_paths(simple_graph, [H1_DIRECT_ASSIGNEE])
        explainer = PathExplainer(lang="en")

        explanation = explainer.explain_path(paths[0])

        assert explanation.narrative != ""
        assert "Seed Person" in explanation.narrative
        assert explanation.evidence_label != ""
        assert explanation.hypothesis_label != ""

    def test_explains_in_french(self, simple_graph):
        """PathExplainer generates French explanations."""
        paths = find_paths(simple_graph, [H1_DIRECT_ASSIGNEE])
        explainer = PathExplainer(lang="fr")

        explanation = explainer.explain_path(paths[0])

        # Should have French labels
        assert "Preuve" in explanation.evidence_label or "Connexion" in explanation.hypothesis_label

    def test_explains_target_with_multiple_paths(self, complex_graph):
        """PathExplainer handles targets with multiple paths."""
        paths = find_paths(complex_graph)
        targets = score_and_rank(paths)

        explainer = PathExplainer(lang="en")
        explanation = explainer.explain_target(targets[0])

        assert explanation.summary != ""
        assert explanation.detailed != ""
        assert explanation.confidence_statement != ""
        assert len(explanation.path_explanations) > 0

    def test_generates_confidence_statement_based_on_evidence(self):
        """Confidence statement reflects evidence quality."""
        explainer = PathExplainer(lang="en")

        # Create mock target with high evidence
        high_target = Mock(
            target_id="org:test",
            target_label="Test Org",
            target_type="corporate",
            best_evidence=EvidenceLevel.HARD,
            best_hypothesis=Hypothesis.H1,
            path_count=3,
        )

        confidence = explainer._generate_confidence_statement(high_target)
        assert "HIGH" in confidence or "ÉLEVÉE" in confidence

    def test_convenience_function_explain_paths(self, simple_graph):
        """Convenience function explain_paths() works."""
        paths = find_paths(simple_graph)
        explanations = explain_paths(paths, lang="en")

        assert isinstance(explanations, list)
        assert len(explanations) == len(paths)


# =============================================================================
# Integration Tests
# =============================================================================

class TestPathFindingIntegration:
    """End-to-end integration tests."""

    def test_full_workflow_simple_graph(self, simple_graph):
        """Complete workflow: find -> score -> explain."""
        # Find paths
        paths = find_paths(simple_graph)
        assert len(paths) > 0

        # Score and rank
        targets = score_and_rank(paths)
        assert len(targets) > 0
        assert targets[0].total_score > 0

        # Explain
        explanations = explain_targets(targets, lang="en")
        assert len(explanations) > 0
        assert explanations[0].summary != ""

    def test_full_workflow_complex_graph(self, complex_graph):
        """Complete workflow with multiple paths and targets."""
        paths = find_paths(complex_graph)
        targets = score_and_rank(paths)
        explanations = explain_targets(targets[:2], lang="fr")

        # Verify results
        assert len(targets) == 2  # company + university
        assert len(explanations) == 2

        # Top target should have highest score
        assert targets[0].total_score >= targets[1].total_score

    def test_handles_empty_graph(self):
        """Handles graph with no valid paths."""
        empty_graph = {
            "meta": {"seed_person_id": "person:seed"},
            "nodes": [{"id": "person:seed", "type": "person", "label": "Seed"}],
            "edges": [],
        }

        paths = find_paths(empty_graph)
        assert len(paths) == 0

        targets = score_and_rank(paths)
        assert len(targets) == 0
