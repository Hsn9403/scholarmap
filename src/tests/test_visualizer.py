#!/usr/bin/env python3
"""
Unit tests for graph visualizer.

Ces tests vérifient la génération de visualisations HTML du graphe de réseau.
"""
import os
import tempfile

from src.graph.visualizer import (
    render_graph_html,
    LEGEND_HTML,
)


# =============================================================================
# Test Legend Content
# =============================================================================


class TestLegendContent:
    """Tests for legend HTML content."""

    def test_legend_contains_node_types(self):
        """
        Test: La légende contient tous les types de nœuds.

        La légende doit afficher Person, Corporate, Institution, Patent.
        """
        assert "Person (Founder, KOLs)" in LEGEND_HTML
        assert "Corporate" in LEGEND_HTML
        assert "Institution" in LEGEND_HTML
        assert "Patent" in LEGEND_HTML

    def test_legend_contains_node_colors(self):
        """
        Test: La légende affiche les couleurs des nœuds.

        Chaque type de nœud a une couleur différente.
        """
        assert "#2D7FF9" in LEGEND_HTML  # Person (blue)
        assert "#F39C12" in LEGEND_HTML  # Corporate (orange)
        assert "#9B59B6" in LEGEND_HTML  # Institution (purple)
        assert "#34495E" in LEGEND_HTML  # Patent (dark gray)

    def test_legend_contains_node_size_explanation(self):
        """
        Test: La légende explique la signification de la taille des nœuds.

        Les nœuds plus grands indiquent des individus clés (high betweenness).
        """
        assert "Node size" in LEGEND_HTML
        assert "key bridges" in LEGEND_HTML
        assert "network connectivity" in LEGEND_HTML

    def test_legend_contains_edge_direction_section(self):
        """
        Test: La légende contient une section "Edge direction".

        Cette section explique la signification des flèches.
        """
        assert "Edge direction" in LEGEND_HTML
        assert "With arrow" in LEGEND_HTML
        assert "Citation relationships" in LEGEND_HTML

    def test_legend_explains_arrows_for_citations(self):
        """
        Test: La légende explique que les flèches indiquent des citations.

        Avec flèche (→): relations de citation (cites, cites_patent)
        """
        assert "→" in LEGEND_HTML
        assert "cites" in LEGEND_HTML
        assert "patent → organization cited" in LEGEND_HTML
        assert "organization → patent citing" in LEGEND_HTML

    def test_legend_explains_no_arrows_for_other_relations(self):
        """
        Test: La légende explique les relations sans flèches.

        Sans flèche (—): autres relations (collaboration, affiliation, ownership)
        """
        assert "—" in LEGEND_HTML or "No arrow" in LEGEND_HTML
        assert "Other relationships" in LEGEND_HTML
        assert "collaboration" in LEGEND_HTML
        assert "affiliation" in LEGEND_HTML
        assert "ownership" in LEGEND_HTML


# =============================================================================
# Test HTML Generation
# =============================================================================


class TestHTMLGeneration:
    """Tests for HTML generation with legend."""

    def test_render_graph_html_includes_legend(self):
        """
        Test: render_graph_html() génère un HTML contenant la légende.

        Le HTML généré doit inclure la légende avec toutes les sections.
        """
        # Create a minimal test graph
        test_graph = {
            "meta": {
                "graph_id": "test_graph",
                "seed_person_id": "person:test_person",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "sources": ["test"],
                "scope": {"max_patents": 10},
            },
            "nodes": [
                {
                    "id": "person:test_person",
                    "type": "person",
                    "label": "Test Person",
                    "attributes": {},
                    "links": {},
                },
                {
                    "id": "org:test_org",
                    "type": "corporate",
                    "label": "Test Org",
                    "attributes": {},
                    "links": {},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "person:test_person",
                    "target": "org:test_org",
                    "type": "affiliated_with",
                    "weight": 1,
                }
            ],
        }

        # Generate HTML in a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            temp_path = f.name

        try:
            render_graph_html(test_graph, temp_path)

            # Read generated HTML
            with open(temp_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Verify legend is included
            assert "Legend" in html_content
            assert "Person (Founder, KOLs)" in html_content
            assert "Corporate" in html_content
            assert "Institution" in html_content
            assert "Patent" in html_content

            # Verify edge direction section is included
            assert "Edge direction" in html_content
            assert "With arrow" in html_content or "→" in html_content
            assert "Citation relationships" in html_content

        finally:
            # Cleanup
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_render_graph_html_creates_valid_html(self):
        """
        Test: render_graph_html() génère un HTML valide.

        Le HTML doit contenir les balises essentielles.
        """
        test_graph = {
            "meta": {
                "graph_id": "test",
                "seed_person_id": "person:test",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "sources": ["test"],
                "scope": {},
            },
            "nodes": [
                {
                    "id": "person:test",
                    "type": "person",
                    "label": "Test",
                    "attributes": {},
                    "links": {},
                }
            ],
            "edges": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            temp_path = f.name

        try:
            render_graph_html(test_graph, temp_path)

            with open(temp_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Check for essential HTML tags
            assert "<html>" in html_content.lower()
            assert "</html>" in html_content.lower()
            assert "<body>" in html_content.lower()
            assert "</body>" in html_content.lower()

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
