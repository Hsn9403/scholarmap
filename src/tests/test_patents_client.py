#!/usr/bin/env python3
"""
Unit tests for Google Patents client.

Ces tests vérifient le client qui orchestre la recherche et l'enrichissement
des données de brevets (PatentsClient).
"""
from unittest.mock import Mock, patch

from src.patents.client import PatentsClient, fetch_patents_data
from src.models import PatentItem, PatentsData


# =============================================================================
# Test Helper Methods
# =============================================================================
# Ces méthodes utilitaires sont utilisées en interne par PatentsClient


class TestPatentsClientHelpers:
    """Tests for PatentsClient helper methods."""

    def test_extract_id_from_url_valid(self):
        """
        Test: Extraire l'ID d'un brevet depuis une URL Google Patents.

        Format URL: https://patents.google.com/patent/US10000000/en
        → Doit extraire "patent/US10000000/en"
        """
        client = PatentsClient(api_key="test")

        test_cases = [
            (
                "https://patents.google.com/patent/US10000000/en",
                "patent/US10000000/en"
            ),
            (
                "https://patents.google.com/patent/EP9999999B1/fr",
                "patent/EP9999999B1/en"  # Toujours /en à la fin
            ),
            (
                "/patent/WO2021012345/en",  # Path relatif
                "patent/WO2021012345/en"
            ),
        ]

        for url, expected in test_cases:
            result = client._extract_id_from_url(url)
            assert result == expected

    def test_extract_id_from_url_invalid(self):
        """Test: URL invalide ou vide → None."""
        client = PatentsClient(api_key="test")

        assert client._extract_id_from_url("") is None
        assert client._extract_id_from_url("https://example.com") is None
        assert client._extract_id_from_url(None) is None

    def test_dedup_preserves_order(self):
        """
        Test: Déduplication en préservant l'ordre de première apparition.

        ["A", "B", "A", "C"] → ["A", "B", "C"]
        L'ordre est important pour l'analyse (priorité aux premiers).
        """
        result = PatentsClient._dedup(["Alpha", "Beta", "Alpha", "Gamma"])

        assert result == ["Alpha", "Beta", "Gamma"]

    def test_dedup_handles_whitespace(self):
        """Test: Déduplication nettoie les espaces et ignore les vides."""
        result = PatentsClient._dedup([
            "  Alpha  ",
            "Beta",
            "",
            "  Alpha  ",  # Duplicate après trim
            "   ",        # Whitespace only
            "Gamma",
        ])

        assert result == ["Alpha", "Beta", "Gamma"]

    def test_normalize_id_from_full_path(self):
        """
        Test: Normaliser un ID complet vers le numéro de document.

        "patent/US10000000/en" → "US10000000"
        Utile pour comparer des IDs de différentes sources.
        """
        assert PatentsClient.normalize_id("patent/US10000000/en") == "US10000000"
        assert PatentsClient.normalize_id("patent/EP9999999B1/fr") == "EP9999999B1"

    def test_normalize_id_already_normalized(self):
        """Test: ID déjà normalisé → retourné tel quel."""
        assert PatentsClient.normalize_id("US10000000") == "US10000000"
        assert PatentsClient.normalize_id("") == ""


# =============================================================================
# Test Initialization
# =============================================================================


class TestPatentsClientInit:
    """Tests for PatentsClient initialization."""

    def test_init_with_api_key(self):
        """Test: Initialiser avec une API key."""
        client = PatentsClient(api_key="test_key")

        assert client.api_client is not None
        assert client.hl == "en"

    def test_init_with_existing_api_client(self):
        """
        Test: Initialiser avec un SerpAPIClient existant.

        Utile pour réutiliser un client déjà configuré
        (ex: avec cassette mode pour tests).
        """
        mock_api = Mock()
        client = PatentsClient(api_client=mock_api)

        assert client.api_client is mock_api

    def test_init_custom_language(self):
        """Test: Initialiser avec une langue personnalisée."""
        client = PatentsClient(api_key="test", hl="fr")

        assert client.hl == "fr"


# =============================================================================
# Test Search Methods
# =============================================================================
# Ces méthodes font des appels API via SerpAPIClient


class TestPatentsClientSearch:
    """Tests for PatentsClient search methods."""

    def test_search_builds_correct_params(self):
        """
        Test: search() construit les bons paramètres pour l'API.

        Vérifie que les paramètres SerpAPI sont correctement formatés :
        - engine: "google_patents"
        - q: la query de recherche
        - num: nombre de résultats
        """
        mock_api = Mock()
        mock_api.search.return_value = {"organic_results": []}

        client = PatentsClient(api_client=mock_api)
        client.search("inventor:John Smith", num=20)

        # Vérifier que l'API a été appelée avec les bons params
        mock_api.search.assert_called_once()
        call_args = mock_api.search.call_args[0][0]
        assert call_args["engine"] == "google_patents"
        assert call_args["q"] == "inventor:John Smith"
        assert call_args["num"] == 20

    def test_get_details_normalizes_patent_id(self):
        """
        Test: get_details() normalise l'ID du brevet.

        Si on passe "US10000000", doit le convertir en "patent/US10000000/en"
        pour l'API Google Patents.
        """
        mock_api = Mock()
        mock_api.search.return_value = {}

        client = PatentsClient(api_client=mock_api)
        client.get_details("US10000000")

        # Vérifier la normalisation de l'ID
        call_args = mock_api.search.call_args[0][0]
        assert call_args["engine"] == "google_patents_details"
        assert call_args["patent_id"] == "patent/US10000000/en"

    def test_get_details_keeps_full_id(self):
        """Test: get_details() garde l'ID s'il est déjà au format complet."""
        mock_api = Mock()
        mock_api.search.return_value = {}

        client = PatentsClient(api_client=mock_api)
        client.get_details("patent/US10000000/en")

        call_args = mock_api.search.call_args[0][0]
        assert call_args["patent_id"] == "patent/US10000000/en"


# =============================================================================
# Test get_html Method
# =============================================================================
# Cette méthode récupère le HTML complet d'une page brevet
# Elle a plusieurs fallbacks en cas d'échec


class TestPatentsClientGetHtml:
    """Tests for PatentsClient.get_html method."""

    def test_get_html_direct_response(self):
        """
        Test: HTML retourné directement dans la réponse API.

        Cas nominal : SerpAPI retourne le HTML dans response["html"]
        (fichier > 50KB pour être considéré valide).
        """
        mock_api = Mock()
        large_html = "x" * 60000  # > 50KB
        mock_api.search.return_value = {"html": large_html}

        client = PatentsClient(api_client=mock_api)
        result = client.get_html("US10000000")

        assert result == large_html

    @patch('src.patents.client.requests.get')
    def test_get_html_fallback_to_raw_url(self, mock_get):
        """
        Test: Fallback vers raw_html_file si HTML direct trop petit.

        Si response["html"] est trop petit (< 50KB), essayer de télécharger
        depuis l'URL fournie dans response["search_metadata"]["raw_html_file"].
        """
        # Setup: API retourne un HTML trop petit + une URL de fallback
        mock_api = Mock()
        mock_api.search.return_value = {
            "html": "small",
            "search_metadata": {
                "raw_html_file": "https://serpapi.com/raw/12345"
            }
        }

        # Setup: requests.get retourne un gros HTML
        mock_response = Mock()
        large_html = "y" * 60000
        mock_response.status_code = 200
        mock_response.text = large_html
        mock_get.return_value = mock_response

        client = PatentsClient(api_client=mock_api)
        result = client.get_html("US10000000")

        # Doit utiliser le HTML téléchargé
        assert result == large_html
        mock_get.assert_called_once()

    @patch('src.patents.client.requests.get')
    def test_get_html_fallback_fails_returns_original(self, mock_get):
        """
        Test: Si le fallback échoue, retourner le HTML original.

        Si requests.get échoue (timeout, erreur réseau, etc.),
        retourner quand même le petit HTML plutôt que rien.
        """
        mock_api = Mock()
        small_html = "small html"
        mock_api.search.return_value = {
            "html": small_html,
            "search_metadata": {"raw_html_file": "https://example.com/raw"}
        }

        # Simuler échec de requests.get
        mock_get.side_effect = Exception("Network error")

        client = PatentsClient(api_client=mock_api)
        result = client.get_html("US10000000")

        # Doit retourner le petit HTML malgré l'échec
        assert result == small_html

    def test_get_html_empty_patent_id(self):
        """Test: Patent ID vide → retourner string vide."""
        client = PatentsClient(api_key="test")
        result = client.get_html("")

        assert result == ""


# =============================================================================
# Test resolve_patent_assignee Method
# =============================================================================

class TestPatentsClientResolvePatentAssignee:
    """Tests for PatentsClient.resolve_patent_assignee method."""

    def test_resolve_patent_assignee_from_api_details(self):
        """Test resolution of patent assignee from API details."""
        api_mock = Mock()
        api_mock.search.return_value = {
            "assignee": "Caliper Life Sciences Inc",
            "publication_date": "2002-01-03",
        }

        client = PatentsClient(api_client=api_mock)
        result = client.resolve_patent_assignee("US2002001856A1")

        assert result == "Caliper Life Sciences Inc"
        api_mock.search.assert_called_once()

    def test_resolve_patent_assignee_from_html_fallback(self):
        """Test resolution fallback to HTML parsing when API returns no assignee."""
        api_mock = Mock()
        api_mock.search.side_effect = [
            {},  # First call (get_details) returns no assignee
            {"html": "<html><dt>Current Assignee</dt><dd>Acme Corporation</dd></html>"}  # Second call (get_html)
        ]

        client = PatentsClient(api_client=api_mock)
        result = client.resolve_patent_assignee("US10000000")

        assert result == "Acme Corporation"
        assert api_mock.search.call_count == 2

    def test_resolve_patent_assignee_normalizes_patent_id(self):
        """Test that patent ID is normalized to patent/ID/en format."""
        api_mock = Mock()
        api_mock.search.return_value = {"assignee": "Test Corp"}

        client = PatentsClient(api_client=api_mock)
        client.resolve_patent_assignee("US12345")

        call_args = api_mock.search.call_args[0][0]
        assert call_args["patent_id"] == "patent/US12345/en"

    def test_resolve_patent_assignee_with_empty_publication_number(self):
        """Test resolution with empty publication number returns empty string."""
        api_mock = Mock()
        client = PatentsClient(api_client=api_mock)

        result = client.resolve_patent_assignee("")

        assert result == ""
        api_mock.search.assert_not_called()

    def test_resolve_patent_assignee_with_whitespace_only(self):
        """Test resolution with whitespace-only publication number returns empty string."""
        api_mock = Mock()
        client = PatentsClient(api_client=api_mock)

        result = client.resolve_patent_assignee("   ")

        assert result == ""
        api_mock.search.assert_not_called()

    def test_resolve_patent_assignee_handles_exception(self):
        """Test that exceptions are caught and logged, returning empty string."""
        api_mock = Mock()
        api_mock.search.side_effect = Exception("API error")

        client = PatentsClient(api_client=api_mock)
        result = client.resolve_patent_assignee("US10000000")

        assert result == ""

    def test_resolve_patent_assignee_with_already_formatted_id(self):
        """Test resolution with patent ID already in patent/ID/en format."""
        api_mock = Mock()
        api_mock.search.return_value = {"assignee": "Beta Inc"}

        client = PatentsClient(api_client=api_mock)
        result = client.resolve_patent_assignee("patent/US67890/en")

        assert result == "Beta Inc"
        call_args = api_mock.search.call_args[0][0]
        assert call_args["patent_id"] == "patent/US67890/en"

    def test_resolve_patent_assignee_returns_empty_when_not_found(self):
        """Test that empty string is returned when assignee cannot be found."""
        api_mock = Mock()
        api_mock.search.side_effect = [
            {},  # get_details returns nothing
            {"html": "<html><body>No assignee info</body></html>"}  # get_html has no assignee
        ]

        client = PatentsClient(api_client=api_mock)
        result = client.resolve_patent_assignee("US99999")

        assert result == ""


# =============================================================================
# Test fetch_patents_data Method
# =============================================================================
# Méthode principale qui orchestre tout le workflow d'enrichissement


class TestPatentsClientFetchPatentsData:
    """Tests for PatentsClient.fetch_patents_data method."""

    def test_fetch_patents_data_basic_flow(self):
        """
        Test: Workflow complet de fetch_patents_data.

        Ce test vérifie que :
        1. La recherche est effectuée avec la bonne query
        2. Les résultats sont transformés en PatentItem
        3. Le total est extrait correctement
        4. PatentsData est retourné avec les bonnes données
        """
        mock_api = Mock()
        # Simuler une réponse de recherche SerpAPI
        mock_api.search.return_value = {
            "search_information": {"total_results": 42},
            "organic_results": [
                {
                    "title": "Method for testing",
                    "link": "https://patents.google.com/patent/US1234567/en",
                    "publication_number": "US1234567",
                },
                {
                    "title": "System for analysis",
                    "link": "https://patents.google.com/patent/US9999999/en",
                }
            ]
        }

        client = PatentsClient(api_client=mock_api)

        # Mock _enrich_patent pour éviter les appels API réels
        client._enrich_patent = Mock()

        result = client.fetch_patents_data("John Smith", max_patents=10)

        # Vérifications
        assert isinstance(result, PatentsData)
        assert result.patents_total == 42
        assert len(result.top_patents) == 2

        # Vérifier premier brevet
        assert result.top_patents[0].title == "Method for testing"
        assert result.top_patents[0].patent_id == "patent/US1234567/en"

        # Vérifier que _enrich_patent a été appelé 2 fois
        assert client._enrich_patent.call_count == 2

    def test_fetch_patents_data_handles_large_total(self):
        """
        Test: Total > 100 → retourner "≥100".

        Google Patents limite les totaux affichés.
        Si > 100, on affiche "≥100" au lieu du nombre exact.
        """
        mock_api = Mock()
        mock_api.search.return_value = {
            "search_information": {"total_results": 150},
            "organic_results": []
        }

        client = PatentsClient(api_client=mock_api)
        client._enrich_patent = Mock()

        result = client.fetch_patents_data("Famous Inventor")

        assert result.patents_total == "≥100"

    def test_fetch_patents_data_no_results(self):
        """Test: Pas de résultats → liste vide."""
        mock_api = Mock()
        mock_api.search.return_value = {
            "search_information": {"total_results": 0},
            "organic_results": []
        }

        client = PatentsClient(api_client=mock_api)
        result = client.fetch_patents_data("Unknown Person")

        assert result.patents_total == 0
        assert result.top_patents == []

    def test_fetch_patents_data_missing_link_generates_fallback(self):
        """
        Test: Résultat sans lien → générer un lien de fallback.

        Si SerpAPI ne retourne pas de lien pour un brevet,
        construire un lien à partir du publication_number.
        """
        mock_api = Mock()
        mock_api.search.return_value = {
            "search_information": {"total_results": 1},
            "organic_results": [
                {
                    "title": "No link patent",
                    # Pas de "link" dans la réponse
                    "publication_number": "US5555555",
                }
            ]
        }

        client = PatentsClient(api_client=mock_api)
        client._enrich_patent = Mock()

        result = client.fetch_patents_data("Test")

        # Vérifier que le lien a été généré
        assert "US5555555" in result.top_patents[0].link


# =============================================================================
# Test _enrich_patent Method
# =============================================================================
# Cette méthode enrichit un brevet avec citations, co-inventors, etc.


class TestPatentsClientEnrichPatent:
    """Tests for PatentsClient._enrich_patent method."""

    def test_enrich_patent_extracts_all_fields(self):
        """
        Test: _enrich_patent extrait tous les champs d'un brevet.

        Vérifie que l'enrichissement extrait :
        - Current assignee (entreprise actuelle)
        - Dates (publication, filing, priority)
        - Claims (revendications du brevet)
        - Cited by count (nombre de citations)
        - Co-inventors (collaborateurs)
        - Citing assignees (entreprises qui citent)
        """
        mock_api = Mock()
        # Simuler une réponse complète de get_details
        mock_api.search.return_value = {
            "assignee": "Acme Corp, US",
            "publication_date": "2021-01-15",
            "filing_date": "2019-06-10",
            "priority_date": "2018-12-01",
            "claims": ["Claim 1", "Claim 2", "Claim 3"],
            "patent_citations": {"total": 42},
            "inventors": [
                {"name": "John Smith"},
                {"name": "Jane Doe"},  # Co-inventor
            ],
            "cited_by": [
                {
                    "publication_number": "US9999999",
                    "assignee": "Beta Inc",
                }
            ]
        }

        client = PatentsClient(api_client=mock_api)
        patent = PatentItem(
            title="Test Patent",
            link="https://patents.google.com/patent/US1234567/en",
            patent_id="patent/US1234567/en",
        )

        client._enrich_patent(patent, inventor_name="John Smith")

        # Vérifications
        # Note: extract_current_assignee() ne nettoie PAS le code pays
        # Seul parse_current_assignee() (depuis HTML) le fait
        assert patent.current_assignee == "Acme Corp, US"
        assert patent.publication_date == "2021-01-15"
        assert patent.filing_date == "2019-06-10"
        assert patent.priority_date == "2018-12-01"
        assert len(patent.claims_top3) == 3
        assert patent.cited_by == 42
        assert "Jane Doe" in patent.co_inventors  # John Smith exclu
        assert "John Smith" not in patent.co_inventors
        assert "Beta Inc" in patent.citing_assignees

    def test_enrich_patent_no_patent_id(self):
        """
        Test: Brevet sans ID → message d'erreur spécial.

        Si on ne peut pas extraire l'ID du brevet,
        impossible de l'enrichir → mettre un message explicite.
        """
        client = PatentsClient(api_key="test")
        patent = PatentItem(
            title="No ID Patent",
            link="https://example.com",
            patent_id=None,  # Pas d'ID extrait
        )

        client._enrich_patent(patent, inventor_name="Test")

        assert patent.citing_assignees == ["no corporate has cited this patent"]

    def test_enrich_patent_handles_errors(self):
        """
        Test: Erreur durant l'enrichissement → valeurs par défaut.

        Si get_details échoue (API error, timeout, etc.),
        ne pas crash mais mettre des valeurs par défaut.
        """
        mock_api = Mock()
        # Simuler une erreur API
        mock_api.search.side_effect = Exception("API Error")

        client = PatentsClient(api_client=mock_api)
        patent = PatentItem(
            title="Error Patent",
            link="https://patents.google.com/patent/US1234567/en",
            patent_id="patent/US1234567/en",
        )

        client._enrich_patent(patent, inventor_name="Test")

        # Vérifier les valeurs par défaut après erreur
        assert patent.claims_top3 == []
        assert patent.cited_by is None
        assert patent.citing_assignees == ["no corporate has cited this patent"]
        assert patent.co_inventors == []


# =============================================================================
# Test Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Tests for backward compatibility functions."""

    def test_fetch_patents_data_function(self):
        """
        Test: La fonction deprecated fetch_patents_data() fonctionne encore.

        Cette fonction existe pour compatibilité avec l'ancien code.
        Elle doit créer un PatentsClient et appeler la méthode.
        """
        with patch.object(PatentsClient, 'fetch_patents_data') as mock_method:
            mock_method.return_value = PatentsData(
                patents_total=10,
                top_patents=[]
            )

            result = fetch_patents_data("Test", api_key="test_key")

            assert isinstance(result, PatentsData)
            mock_method.assert_called_once_with("Test")
