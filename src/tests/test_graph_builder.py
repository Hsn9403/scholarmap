#!/usr/bin/env python3
"""
Unit tests for network graph builder.

Ces tests vérifient la construction du graphe de réseau KOL (Key Opinion Leaders)
à partir des données Scholar et Patents.
"""
from unittest.mock import patch, Mock

from src.graph.builder import (
    _node_id,
    _patent_node_id,
    _normalize_patent_id,
    _is_placeholder,
    _same_org,
    _normalize_person_name,
    _is_same_person,
    GraphBuilder,
    build_graph_data,
)
from src.models import ScholarData, PatentsData, PatentItem, CoAuthor, ScholarPublication


# =============================================================================
# Test Helper Functions
# =============================================================================
# Ces fonctions utilitaires génèrent des IDs uniques et normalisent les données


class TestGraphBuilderHelpers:
    """Tests for graph builder helper functions."""

    def test_node_id_generates_unique_id(self):
        """
        Test: _node_id() génère un ID unique à partir du type et du label.

        Format: "type:label_slugifie"
        Le label est transformé en slug (minuscules, underscores, pas d'accents).
        """
        # Cas nominal
        assert _node_id("person", "John Smith") == "person:john_smith"
        assert _node_id("org", "Acme Corp") == "org:acme_corp"

        # Accents et caractères spéciaux sont normalisés
        assert _node_id("person", "François Müller") == "person:francois_muller"

        # Espaces multiples → un seul underscore
        assert _node_id("org", "Big   Tech   Company") == "org:big_tech_company"

    def test_patent_node_id_normalizes_format(self):
        """
        Test: _patent_node_id() normalise l'ID d'un brevet.

        Enlève les préfixes "patent/" et suffixes "/en" pour avoir
        un format uniforme: "patent:US1234567"
        """
        # Cas nominal: numéro de publication simple
        assert _patent_node_id("US1234567") == "patent:US1234567"

        # Format complet avec préfixe/suffixe
        assert _patent_node_id("patent/US1234567/en") == "patent:US1234567"

        # Whitespace trimming
        assert _patent_node_id("  US1234567  ") == "patent:US1234567"

        # Vide ou None → "patent:unknown"
        assert _patent_node_id("") == "patent:unknown"
        assert _patent_node_id(None) == "patent:unknown"

    def test_normalize_patent_id_extracts_document_number(self):
        """
        Test: _normalize_patent_id() extrait le numéro de document.

        "patent/US1234567/en" → "US1234567"
        Utilisé pour comparer des IDs de différentes sources.
        """
        assert _normalize_patent_id("patent/US1234567/en") == "US1234567"
        assert _normalize_patent_id("patent/EP9999999B1/fr") == "EP9999999B1"

        # Déjà normalisé → retourné tel quel
        assert _normalize_patent_id("US1234567") == "US1234567"

        # Vide → retourné tel quel
        assert _normalize_patent_id("") == ""

    def test_is_placeholder_detects_placeholder_text(self):
        """
        Test: _is_placeholder() détecte le texte placeholder spécial.

        "no corporate has cited this patent" est un message d'erreur
        utilisé quand on n'a pas de données de citation.
        Il ne doit PAS être traité comme une vraie entreprise.
        """
        assert _is_placeholder("no corporate has cited this patent") is True
        assert _is_placeholder("No Corporate Has Cited This Patent") is True  # Case-insensitive

        # Avec espaces en trop
        assert _is_placeholder("  no corporate has cited this patent  ") is True

        # Vrais noms d'entreprise → False
        assert _is_placeholder("Acme Corp") is False
        assert _is_placeholder("") is False

    def test_same_org_compares_organizations(self):
        """
        Test: _same_org() compare deux noms d'organisations de manière fuzzy.

        La comparaison ignore :
        - Majuscules/minuscules
        - Accents
        - Suffixes légaux (Inc, Corp, Ltd, LLC, etc.)
        - Ponctuation

        Utile pour détecter les auto-citations (même entreprise sous noms différents).
        """
        # Mêmes noms avec variations
        assert _same_org("Acme Corporation", "Acme Corp") is True
        assert _same_org("Acme Inc", "ACME") is True
        assert _same_org("Beta LLC", "Beta Limited") is True

        # Inclusion (substring match)
        assert _same_org("Google LLC", "Google") is True
        assert _same_org("Microsoft Corporation", "Microsoft") is True

        # Noms différents → False
        assert _same_org("Acme Corp", "Beta Inc") is False

        # Vide → False
        assert _same_org("", "Acme Corp") is False
        assert _same_org("Acme Corp", "") is False

    def test_normalize_person_name(self):
        """
        Test: _normalize_person_name() normalise les noms de personnes.

        La normalisation :
        - Convertit en minuscules
        - Supprime les accents
        - Garde seulement alphanumériques + espaces
        - Collapse les espaces multiples
        """
        assert _normalize_person_name("Alice Nedelec") == "alice nedelec"
        assert _normalize_person_name("ALICE NEDELEC") == "alice nedelec"
        assert _normalize_person_name("Àlice Nedelec") == "alice nedelec"
        assert _normalize_person_name("  Alice   Nedelec  ") == "alice nedelec"
        assert _normalize_person_name("Jean-Paul Sartre") == "jeanpaul sartre"

    def test_is_same_person_handles_abbreviations(self):
        """
        Test: _is_same_person() détecte quand deux noms correspondent.

        Gère les cas où le prénom est abrégé (première lettre seulement).
        C'est crucial car Google Scholar renvoie souvent des noms abrégés.

        Exemples de cas réels :
        - "A Nedelec" devrait matcher "Alice Nedelec"
        - "P Sharan" devrait matcher "Priyanka Sharan"
        """
        # Noms exacts
        assert _is_same_person("Alice Nedelec", "Alice Nedelec") is True

        # Prénom abrégé (initial)
        assert _is_same_person("A Nedelec", "Alice Nedelec") is True
        assert _is_same_person("Alice Nedelec", "A Nedelec") is True
        assert _is_same_person("P Sharan", "Priyanka Sharan") is True

        # Avec variations de casse et accents
        assert _is_same_person("a nedelec", "ALICE NEDELEC") is True
        assert _is_same_person("A Nédelec", "Alice Nedelec") is True

        # Noms différents → False
        assert _is_same_person("John Smith", "Jane Smith") is False
        assert _is_same_person("A Nedelec", "P Sharan") is False

        # Prénom initial ne match pas
        assert _is_same_person("A Nedelec", "Priyanka Nedelec") is False

        # Noms multiples (partial surnames)
        assert _is_same_person("A Nedelec Mercier", "Alice Nedelec") is True
        assert _is_same_person("Alice Nedelec", "A Nedelec Mercier") is True
        assert _is_same_person("J Smith Jones", "John Smith") is True


# =============================================================================
# Test GraphBuilder Class
# =============================================================================
# Cette classe accumule les nœuds et arêtes du graphe


class TestGraphBuilderClass:
    """Tests for GraphBuilder class."""

    def test_add_node_stores_node(self):
        """
        Test: add_node() stocke un nœud dans le dictionnaire.

        Les nœuds sont stockés par leur ID pour éviter les doublons.
        """
        gb = GraphBuilder()
        node = {
            "id": "person:john-smith",
            "type": "person",
            "label": "John Smith",
        }

        gb.add_node(node)

        assert "person:john-smith" in gb.nodes
        assert gb.nodes["person:john-smith"]["label"] == "John Smith"

    def test_add_edge_creates_new_edge(self):
        """
        Test: add_edge() crée une nouvelle arête.

        Première fois qu'on ajoute une arête → créée avec weight=1.
        """
        gb = GraphBuilder()
        edge = {
            "source": "person:john",
            "target": "patent:US123",
            "type": "has_patent",
        }

        gb.add_edge("edge_key_1", edge)

        assert "edge_key_1" in gb.edges
        assert gb.edges["edge_key_1"]["weight"] == 1
        assert gb.edges["edge_key_1"]["id"] == "edge_key_1"

    def test_add_edge_increments_weight_for_duplicate(self):
        """
        Test: add_edge() incrémente le poids si l'arête existe déjà.

        Si on ajoute 2 fois la même arête (même clé) :
        - weight = 1 (première fois)
        - weight = 2 (deuxième fois)
        - weight = 3 (troisième fois), etc.

        Utile pour compter les co-inventions multiples ou citations multiples.
        """
        gb = GraphBuilder()
        edge1 = {"source": "a", "target": "b", "type": "test"}
        edge2 = {"source": "a", "target": "b", "type": "test"}

        gb.add_edge("edge_key", edge1)
        gb.add_edge("edge_key", edge2)  # Même clé

        # Weight devrait être incrémenté
        assert gb.edges["edge_key"]["weight"] == 2

    def test_add_edge_accumulates_evidence(self):
        """
        Test: add_edge() accumule les preuves (evidence) pour les arêtes dupliquées.

        Les arêtes peuvent avoir une liste "evidence" (URLs, etc.).
        Si on ajoute plusieurs fois la même arête, on garde les preuves.
        """
        gb = GraphBuilder()

        edge1 = {
            "source": "a",
            "target": "b",
            "type": "test",
            "evidence": [{"url": "http://example.com/1"}]
        }

        edge2 = {
            "source": "a",
            "target": "b",
            "type": "test",
            "evidence": [{"url": "http://example.com/2"}]
        }

        gb.add_edge("edge_key", edge1)
        gb.add_edge("edge_key", edge2)  # Même clé

        # Evidence devrait être accumulée (limitée à 1 par ajout)
        assert len(gb.edges["edge_key"]["evidence"]) == 2


# =============================================================================
# Test build_graph_data Function
# =============================================================================
# Fonction principale qui construit le graphe complet


class TestBuildGraphDataBasic:
    """Tests basiques pour build_graph_data - structure du graphe."""

    @patch('src.graph.builder._classify_org_type')
    def test_build_graph_creates_seed_person_node(self, mock_classify):
        """
        Test: build_graph_data() crée le nœud de la personne seed (chercheur).

        Le nœud seed est le chercheur principal pour lequel on construit le réseau.
        Il contient ses métriques Scholar (citations, h-index, etc.).
        """
        mock_classify.return_value = "institution"

        scholar = ScholarData(
            name="Marie Curie",
            author_id="abc123",
            affiliation="University of Paris",
            citations_total=50000,
            h_index=80,
            publications_total=150,
            coauthors=[],
            top_publications=[],
        )

        patents = PatentsData(patents_total=10, top_patents=[])

        graph = build_graph_data("Marie Curie", scholar, patents)

        # Vérifier structure du graphe
        assert "meta" in graph
        assert "nodes" in graph
        assert "edges" in graph

        # Vérifier le nœud seed
        seed_nodes = [n for n in graph["nodes"] if n["type"] == "person" and "Marie Curie" in n["label"]]
        assert len(seed_nodes) == 1

        seed = seed_nodes[0]
        assert seed["attributes"]["citations_total"] == 50000
        assert seed["attributes"]["h_index"] == 80
        assert seed["attributes"]["scholar_author_id"] == "abc123"

    @patch('src.graph.builder._classify_org_type')
    def test_build_graph_creates_affiliation_node(self, mock_classify):
        """
        Test: Créer un nœud pour l'affiliation du chercheur.

        L'affiliation (université, labo, entreprise) du chercheur
        est ajoutée comme nœud + une arête "affiliated_with".
        """
        mock_classify.return_value = "institution"

        scholar = ScholarData(
            name="John Smith",
            author_id="xyz789",
            affiliation="MIT",
            citations_total=0,
            h_index=0,
            publications_total=0,
            coauthors=[],
            top_publications=[],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("John Smith", scholar, patents)

        # Vérifier le nœud affiliation
        aff_nodes = [n for n in graph["nodes"] if n["type"] == "institution"]
        assert len(aff_nodes) == 1
        assert aff_nodes[0]["label"] == "MIT"

        # Vérifier l'arête affiliated_with
        aff_edges = [e for e in graph["edges"] if e["type"] == "affiliated_with"]
        assert len(aff_edges) == 1

    @patch('src.graph.builder._classify_org_type')
    @patch('src.graph.builder._classify_entity_type')
    def test_build_graph_creates_patent_nodes(self, mock_entity, mock_org):
        """
        Test: Créer des nœuds pour les brevets.

        Chaque brevet du chercheur devient un nœud avec :
        - Titre, dates, assignee actuel
        - Lien vers Google Patents
        - Arête "has_patent" depuis le chercheur
        """
        mock_org.return_value = "corporate"
        mock_entity.return_value = "corporate"

        scholar = ScholarData(
            name="Jane Doe",
            author_id="test",
            affiliation="",
            citations_total=0,
            h_index=0,
            publications_total=0,
            coauthors=[],
            top_publications=[],
        )

        patent = PatentItem(
            title="Method for Testing",
            link="https://patents.google.com/patent/US1234567/en",
            patent_id="patent/US1234567/en",
            publication_date="2021-01-15",
            current_assignee="Acme Corp",
            claims_top3=["Claim 1"],
            cited_by=10,
            cited_assignees=[],
            citing_assignees=[],
            co_inventors=[],
        )

        patents = PatentsData(patents_total=1, top_patents=[patent])

        graph = build_graph_data("Jane Doe", scholar, patents)

        # Vérifier le nœud patent
        patent_nodes = [n for n in graph["nodes"] if n["type"] == "patent"]
        assert len(patent_nodes) == 1
        assert patent_nodes[0]["label"] == "Method for Testing"
        assert patent_nodes[0]["attributes"]["current_assignee"] == "Acme Corp"

        # Vérifier l'arête has_patent
        patent_edges = [e for e in graph["edges"] if e["type"] == "has_patent"]
        assert len(patent_edges) == 1

    @patch('src.graph.builder._classify_org_type')
    @patch('src.graph.builder._classify_entity_type')
    def test_build_graph_creates_coinventor_nodes(self, mock_entity, mock_org):
        """
        Test: Créer des nœuds pour les co-inventeurs.

        Les co-inventeurs (collaborateurs sur un brevet) deviennent des nœuds
        avec une arête "co_invented" depuis le chercheur.
        """
        mock_org.return_value = "corporate"
        mock_entity.return_value = "person"

        scholar = ScholarData(
            name="Alice",
            author_id="test",
            affiliation="",
            citations_total=0,
            h_index=0,
            publications_total=0,
            coauthors=[],
            top_publications=[],
        )

        patent = PatentItem(
            title="Test Patent",
            link="https://example.com",
            patent_id="patent/US999/en",
            co_inventors=["Bob Lee", "Carol White"],
            cited_assignees=[],
            citing_assignees=[],
        )

        patents = PatentsData(patents_total=1, top_patents=[patent])

        graph = build_graph_data("Alice", scholar, patents)

        # Vérifier les nœuds co-inventeurs
        coinventor_nodes = [n for n in graph["nodes"] if "co_inventor" in n.get("role", [])]
        assert len(coinventor_nodes) == 2

        labels = {n["label"] for n in coinventor_nodes}
        assert "Bob Lee" in labels
        assert "Carol White" in labels

        # Vérifier les arêtes co_invented
        coinv_edges = [e for e in graph["edges"] if e["type"] == "co_invented"]
        assert len(coinv_edges) == 2

    def test_build_graph_creates_coauthor_nodes(self):
        """
        Test: Créer des nœuds pour les co-auteurs.

        Les co-auteurs (collaborateurs sur des publications) deviennent des nœuds
        avec une arête "co_author_with" depuis le chercheur.
        """
        coauthor1 = CoAuthor(
            name="John Smith",
            shared_pubs_count=5,
            last_shared_year="2023",
            example_titles=["Paper 1", "Paper 2"]
        )
        coauthor2 = CoAuthor(
            name="Jane Doe",
            shared_pubs_count=3,
            last_shared_year="2022",
            example_titles=["Paper 3"]
        )

        scholar = ScholarData(
            name="Alice",
            author_id="test",
            affiliation="MIT",
            citations_total=100,
            h_index=10,
            publications_total=20,
            coauthors=[coauthor1, coauthor2],
            top_publications=[],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("Alice", scholar, patents)

        # Vérifier les nœuds co-auteurs
        coauthor_nodes = [n for n in graph["nodes"] if "co_author" in n.get("role", [])]
        assert len(coauthor_nodes) == 2

        labels = {n["label"] for n in coauthor_nodes}
        assert "John Smith" in labels
        assert "Jane Doe" in labels

        # Vérifier les attributs d'un co-auteur
        john_node = [n for n in coauthor_nodes if n["label"] == "John Smith"][0]
        assert john_node["attributes"]["shared_pubs_count"] == 5
        assert john_node["attributes"]["last_shared_year"] == "2023"

        # Vérifier les arêtes co_author_with
        coauthor_edges = [e for e in graph["edges"] if e["type"] == "co_author_with"]
        assert len(coauthor_edges) == 2

        # Vérifier que le poids correspond au nombre de publications partagées
        john_edge = [e for e in coauthor_edges if "john_smith" in e["target"]][0]
        assert john_edge["weight"] == 5

    def test_build_graph_creates_publication_nodes(self):
        """
        Test: Créer des nœuds pour les publications.

        Les publications deviennent des nœuds avec une arête "authored_by"
        vers chacun de leurs auteurs.
        """
        pub1 = ScholarPublication(
            title="Microfluidics for microswimmers",
            link="https://scholar.google.com/paper1",
            cited_by=25,
            authors=["Alice Nedelec", "Priyanka Sharan", "Sasha Cai Lesher‐Pérez", "Juliane Simmchen"],
            year="2023"
        )
        pub2 = ScholarPublication(
            title="Another great paper",
            link="https://scholar.google.com/paper2",
            cited_by=10,
            authors=["Alice Nedelec", "John Smith"],
            year="2022"
        )

        scholar = ScholarData(
            name="Alice Nedelec",
            author_id="test123",
            affiliation="Université de Lyon",
            citations_total=500,
            h_index=12,
            publications_total=30,
            coauthors=[],
            top_publications=[pub1, pub2],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("Alice Nedelec", scholar, patents)

        # Vérifier les nœuds de publications
        pub_nodes = [n for n in graph["nodes"] if n["type"] == "publication"]
        assert len(pub_nodes) == 2

        labels = {n["label"] for n in pub_nodes}
        assert "Microfluidics for microswimmers" in labels
        assert "Another great paper" in labels

        # Vérifier les attributs d'une publication
        pub1_node = [n for n in pub_nodes if "Microfluidics" in n["label"]][0]
        assert pub1_node["attributes"]["year"] == "2023"
        assert pub1_node["attributes"]["cited_by"] == 25
        assert pub1_node["attributes"]["authors_count"] == 4

        # Vérifier les arêtes authored_by
        authored_edges = [e for e in graph["edges"] if e["type"] == "authored_by"]
        # pub1 a 4 auteurs, pub2 a 2 auteurs = 6 edges
        assert len(authored_edges) == 6

        # Vérifier qu'il y a des edges de pub1 vers tous ses auteurs
        pub1_id = pub1_node["id"]
        pub1_edges = [e for e in authored_edges if e["source"] == pub1_id]
        assert len(pub1_edges) == 4

        # Vérifier que les nœuds des auteurs existent
        author_nodes = [n for n in graph["nodes"] if n["type"] == "person"]
        author_labels = {n["label"] for n in author_nodes}
        assert "Alice Nedelec" in author_labels
        assert "Priyanka Sharan" in author_labels
        assert "Sasha Cai Lesher‐Pérez" in author_labels
        assert "Juliane Simmchen" in author_labels
        assert "John Smith" in author_labels

        # IMPORTANT: Vérifier que le chercheur principal est TOUJOURS lié à chaque publication
        seed_id = graph["meta"]["seed_person_id"]
        for pub_node in pub_nodes:
            pub_edges = [e for e in authored_edges if e["source"] == pub_node["id"]]
            seed_edges = [e for e in pub_edges if e["target"] == seed_id]
            assert len(seed_edges) == 1, f"Publication '{pub_node['label']}' must have exactly one edge to the seed person"

    def test_build_graph_publications_always_link_to_researcher(self):
        """
        Test: Les publications sont TOUJOURS liées au chercheur principal.

        Même si le chercheur n'apparaît pas dans la liste des auteurs
        (cas rare mais possible avec l'API), chaque publication doit
        avoir un lien vers le chercheur puisque ce sont SES publications.
        """
        pub1 = ScholarPublication(
            title="Paper without researcher in authors list",
            link="https://scholar.google.com/paper1",
            cited_by=10,
            authors=["Other Author 1", "Other Author 2"],  # Alice n'est PAS dans la liste
            year="2023"
        )

        scholar = ScholarData(
            name="Alice Nedelec",
            author_id="test123",
            affiliation="MIT",
            citations_total=100,
            h_index=10,
            publications_total=20,
            coauthors=[],
            top_publications=[pub1],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("Alice Nedelec", scholar, patents)

        # Vérifier qu'Alice est liée à la publication
        seed_id = graph["meta"]["seed_person_id"]
        pub_nodes = [n for n in graph["nodes"] if n["type"] == "publication"]
        assert len(pub_nodes) == 1

        authored_edges = [e for e in graph["edges"] if e["type"] == "authored_by"]
        seed_edges = [e for e in authored_edges if e["target"] == seed_id]
        assert len(seed_edges) == 1, "Publication must be linked to the seed person even if not in authors list"

    def test_build_graph_no_duplicate_for_abbreviated_names(self):
        """
        Test: Pas de nœud dupliqué quand l'auteur a un nom abrégé.

        Problème réel : Google Scholar renvoie des noms abrégés ("A Nedelec")
        qui créaient des nœuds séparés du chercheur principal ("Alice Nedelec").

        Solution : _is_same_person() détecte les abréviations et utilise
        l'ID du chercheur principal au lieu de créer un doublon.
        """
        pub1 = ScholarPublication(
            title="Paper with abbreviated author name",
            link="https://scholar.google.com/paper1",
            cited_by=10,
            authors=["A Nedelec", "John Smith"],  # "A Nedelec" est Alice Nedelec
            year="2023"
        )

        scholar = ScholarData(
            name="Alice Nedelec",
            author_id="test123",
            affiliation="MIT",
            citations_total=100,
            h_index=10,
            publications_total=20,
            coauthors=[],
            top_publications=[pub1],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("Alice Nedelec", scholar, patents)

        # Vérifier qu'il n'y a qu'UN SEUL nœud "Alice Nedelec"
        person_nodes = [n for n in graph["nodes"] if n["type"] == "person"]
        alice_nodes = [n for n in person_nodes if "nedelec" in n["label"].lower()]

        assert len(alice_nodes) == 1, "Should have exactly one node for the researcher (no duplicate for 'A Nedelec')"
        assert alice_nodes[0]["label"] == "Alice Nedelec", "Node should use full name, not abbreviated"

        # Vérifier qu'il y a bien 2 auteurs au total (Alice + John)
        assert len(person_nodes) == 2

        # Vérifier que la publication a bien 2 edges vers les auteurs
        pub_nodes = [n for n in graph["nodes"] if n["type"] == "publication"]
        assert len(pub_nodes) == 1

        authored_edges = [e for e in graph["edges"] if e["type"] == "authored_by"]
        pub_edges = [e for e in authored_edges if e["source"] == pub_nodes[0]["id"]]
        assert len(pub_edges) == 2, "Publication should have 2 edges (one to Alice, one to John)"


class TestBuildGraphDataCitations:
    """Tests pour build_graph_data - gestion des citations."""

    @patch('src.graph.builder._classify_org_type')
    @patch('src.graph.builder._classify_entity_type')
    @patch('src.graph.builder._same_org')
    def test_build_graph_filters_self_citations(self, mock_same_org, mock_entity, mock_org):
        """
        Test: Filtrer les auto-citations (forward citations).

        Auto-citation = quand une entreprise cite son propre brevet.
        Ces citations ne sont PAS intéressantes pour l'analyse de réseau.

        Exemple: Si Acme Corp possède le brevet ET cite le brevet,
        cette citation est ignorée.
        """
        mock_org.return_value = "corporate"
        mock_entity.return_value = "corporate"

        # Mock _same_org pour détecter l'auto-citation
        def same_org_side_effect(a, b):
            return (a == "Acme Corp" and b == "Acme Corp")

        mock_same_org.side_effect = same_org_side_effect

        scholar = ScholarData(
            name="Test",
            author_id="test",
            affiliation="",
            citations_total=0,
            h_index=0,
            publications_total=0,
            coauthors=[],
            top_publications=[],
        )

        patent = PatentItem(
            title="Test Patent",
            link="https://example.com",
            patent_id="patent/US999/en",
            current_assignee="Acme Corp",
            citing_patents=[
                {"assignee": "Acme Corp", "publication_date": "2022-01-01"},  # Auto-citation
                {"assignee": "Beta Inc", "publication_date": "2022-02-01"},   # Citation externe
            ],
            cited_assignees=[],
            citing_assignees=[],
            co_inventors=[],
        )

        patents = PatentsData(patents_total=1, top_patents=[patent])

        graph = build_graph_data("Test", scholar, patents)

        # Vérifier qu'on a SEULEMENT Beta Inc (Acme Corp filtré)
        citing_edges = [e for e in graph["edges"] if e["type"] == "cites_patent"]

        # Devrait avoir seulement 1 arête (Beta Inc, pas Acme Corp)
        assert len(citing_edges) == 1


class TestBuildGraphDataEdgeCases:
    """Tests pour build_graph_data - edge cases."""

    def test_build_graph_no_scholar_data(self):
        """
        Test: Construire le graphe sans données Scholar (seulement Patents).

        Cas où on n'a pas pu récupérer le profil Scholar.
        Le graphe doit quand même se construire avec les brevets.
        """
        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("Unknown Person", scholar=None, patents=patents)

        # Graphe valide créé
        assert "meta" in graph
        assert "nodes" in graph
        assert "edges" in graph

        # Nœud seed créé avec le nom fourni
        seed_nodes = [n for n in graph["nodes"] if n["type"] == "person"]
        assert len(seed_nodes) == 1
        assert seed_nodes[0]["label"] == "Unknown Person"

    @patch('src.graph.builder._classify_org_type')
    def test_build_graph_empty_patents(self, mock_classify):
        """
        Test: Construire le graphe sans brevets.

        Cas où le chercheur n'a pas de brevets.
        Le graphe contient juste le chercheur (+ affiliation si Scholar data).
        """
        mock_classify.return_value = "institution"

        scholar = ScholarData(
            name="No Patents Person",
            author_id="test",
            affiliation="Some University",
            citations_total=100,
            h_index=10,
            publications_total=20,
            coauthors=[],
            top_publications=[],
        )

        patents = PatentsData(patents_total=0, top_patents=[])

        graph = build_graph_data("No Patents Person", scholar, patents)

        # Pas de nœuds brevets
        patent_nodes = [n for n in graph["nodes"] if n["type"] == "patent"]
        assert len(patent_nodes) == 0

        # Mais nœud seed + affiliation présents
        assert len(graph["nodes"]) >= 2  # Seed + affiliation

    @patch('src.graph.builder._classify_org_type')
    @patch('src.graph.builder._classify_entity_type')
    def test_build_graph_respects_max_patents(self, mock_entity, mock_org):
        """
        Test: Respecter la limite max_patents.

        Si on a 10 brevets mais max_patents=3, seulement 3 brevets
        doivent être inclus dans le graphe (les plus pertinents).
        """
        mock_org.return_value = "corporate"
        mock_entity.return_value = "corporate"

        scholar = ScholarData(
            name="Test",
            author_id="test",
            affiliation="",
            citations_total=0,
            h_index=0,
            publications_total=0,
            coauthors=[],
            top_publications=[],
        )

        # Créer 5 brevets
        patents_list = [
            PatentItem(
                title=f"Patent {i}",
                link=f"https://example.com/{i}",
                patent_id=f"patent/US{i}/en",
                cited_assignees=[],
                citing_assignees=[],
                co_inventors=[],
            )
            for i in range(5)
        ]

        patents = PatentsData(patents_total=5, top_patents=patents_list)

        # Limiter à 3 brevets
        graph = build_graph_data("Test", scholar, patents, max_patents=3)

        # Vérifier qu'on a seulement 3 brevets
        patent_nodes = [n for n in graph["nodes"] if n["type"] == "patent"]
        assert len(patent_nodes) == 3


# =============================================================================
# Test Co-Inventor Edges - Hybrid Approach
# =============================================================================

class TestCoInventorHybridEdges:
    """Tests for hybrid co-inventor edges (aggregated + detailed)."""

    def test_co_inventor_has_both_aggregated_and_detailed_edges(self):
        """
        Test: Les co-inventeurs ont à la fois des edges agrégés (vers la personne)
        et des edges détaillés (vers les brevets spécifiques).
        """
        scholar = None
        patent1 = PatentItem(
            title="Patent 1",
            link="https://example.com/1",
            patent_id="patent/US111/en",
            co_inventors=["Alice Smith", "Bob Jones"],
            cited_assignees=[],
            citing_assignees=[],
        )
        patent2 = PatentItem(
            title="Patent 2",
            link="https://example.com/2",
            patent_id="patent/US222/en",
            co_inventors=["Alice Smith"],  # Alice sur les 2, Bob sur 1 seul
            cited_assignees=[],
            citing_assignees=[],
        )

        patents = PatentsData(patents_total=2, top_patents=[patent1, patent2])

        graph = build_graph_data("Jane Doe", scholar, patents)

        # Vérifier les edges agrégés (person -> co-inventor)
        co_invented_edges = [e for e in graph["edges"] if e["type"] == "co_invented"]
        assert len(co_invented_edges) == 2  # Jane -> Alice, Jane -> Bob

        alice_edge = [e for e in co_invented_edges if "alice_smith" in e["target"]][0]
        assert alice_edge["weight"] == 2  # Alice a collaboré sur 2 brevets

        bob_edge = [e for e in co_invented_edges if "bob_jones" in e["target"]][0]
        assert bob_edge["weight"] == 1  # Bob sur 1 brevet

        # Vérifier les edges détaillés (co-inventor -> patent)
        co_invented_on_edges = [e for e in graph["edges"] if e["type"] == "co_invented_on"]
        assert len(co_invented_on_edges) == 3  # Alice->Patent1, Alice->Patent2, Bob->Patent1

        # Alice doit avoir 2 edges vers les brevets
        alice_patent_edges = [e for e in co_invented_on_edges if "alice_smith" in e["source"]]
        assert len(alice_patent_edges) == 2

        # Bob doit avoir 1 edge vers le brevet
        bob_patent_edges = [e for e in co_invented_on_edges if "bob_jones" in e["source"]]
        assert len(bob_patent_edges) == 1
        assert "US111" in bob_patent_edges[0]["target"]

    def test_co_invented_on_edges_have_correct_attributes(self):
        """
        Test: Les edges co_invented_on ont les bons attributs (patent_id, evidence).
        """
        scholar = None
        patent = PatentItem(
            title="Test Patent",
            link="https://example.com/test",
            patent_id="patent/US12345/en",
            co_inventors=["Charlie Brown"],
            cited_assignees=[],
            citing_assignees=[],
        )

        patents = PatentsData(patents_total=1, top_patents=[patent])

        graph = build_graph_data("Test Person", scholar, patents)

        # Trouver l'edge co_invented_on
        co_invented_on_edges = [e for e in graph["edges"] if e["type"] == "co_invented_on"]
        assert len(co_invented_on_edges) == 1

        edge = co_invented_on_edges[0]

        # Vérifier les attributs
        assert "patent_id" in edge["attributes"]
        assert edge["attributes"]["patent_id"] == "patent/US12345/en"

        # Vérifier l'evidence
        assert len(edge["evidence"]) == 1
        assert edge["evidence"][0]["url"] == "https://example.com/test"

    def test_co_invented_on_targets_correct_patent(self):
        """
        Test: Chaque edge co_invented_on pointe vers le bon brevet.
        """
        scholar = None
        patent1 = PatentItem(
            title="Microfluidics Patent",
            link="https://example.com/micro",
            patent_id="patent/FR3134731A1/en",
            co_inventors=["Tristan GAUTHIER"],
            cited_assignees=[],
            citing_assignees=[],
        )
        patent2 = PatentItem(
            title="Mixing Module Patent",
            link="https://example.com/mixing",
            patent_id="patent/FR3158313A1/en",
            co_inventors=["Tristan GAUTHIER", "Remy OLLIVIER"],
            cited_assignees=[],
            citing_assignees=[],
        )

        patents = PatentsData(patents_total=2, top_patents=[patent1, patent2])

        graph = build_graph_data("Alice Nedelec", scholar, patents)

        # Trouver les edges co_invented_on
        co_invented_on_edges = [e for e in graph["edges"] if e["type"] == "co_invented_on"]

        # Tristan doit avoir 2 edges (vers les 2 brevets)
        tristan_edges = [e for e in co_invented_on_edges if "tristan_gauthier" in e["source"]]
        assert len(tristan_edges) == 2

        tristan_targets = [e["target"] for e in tristan_edges]
        assert "patent:FR3134731A1" in tristan_targets
        assert "patent:FR3158313A1" in tristan_targets

        # Remy doit avoir 1 edge (vers le 2ème brevet seulement)
        remy_edges = [e for e in co_invented_on_edges if "remy_ollivier" in e["source"]]
        assert len(remy_edges) == 1
        assert "patent:FR3158313A1" in remy_edges[0]["target"]

    def test_no_co_invented_on_edges_when_no_co_inventors(self):
        """
        Test: Pas d'edges co_invented_on quand il n'y a pas de co-inventeurs.
        """
        scholar = None
        patent = PatentItem(
            title="Solo Patent",
            link="https://example.com/solo",
            patent_id="patent/US999/en",
            co_inventors=[],  # Aucun co-inventeur
            cited_assignees=[],
            citing_assignees=[],
        )

        patents = PatentsData(patents_total=1, top_patents=[patent])

        graph = build_graph_data("Solo Inventor", scholar, patents)

        # Vérifier qu'il n'y a pas d'edges co_invented_on
        co_invented_on_edges = [e for e in graph["edges"] if e["type"] == "co_invented_on"]
        assert len(co_invented_on_edges) == 0

        # Vérifier qu'il n'y a pas non plus d'edges co_invented
        co_invented_edges = [e for e in graph["edges"] if e["type"] == "co_invented"]
        assert len(co_invented_edges) == 0
