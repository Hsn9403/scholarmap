#!/usr/bin/env python3
"""
Unit tests for HTML parsing utilities for Google Patents pages.

Ces tests vérifient que le parsing des pages HTML Google Patents fonctionne
correctement. IMPORTANT: Si Google change le format HTML, ces tests échoueront.
"""


from src.patents.parsers import (
    parse_cited_by_table,
    parse_current_assignee,
    parse_assignees_from_table,
    has_cited_by_section,
)


# =============================================================================
# Test parse_cited_by_table
# =============================================================================
# Cette fonction extrait les brevets qui citent le brevet actuel (forward citations)
# depuis la table HTML "Cited By" sur Google Patents

class TestParseCitedByTable:
    """Tests for parse_cited_by_table function."""

    def test_parse_complete_table(self):
        """
        Test: Parser une table complète "Cited By".
        Vérifie l'extraction de :
        - Numéros de publication (ex: US1234567)
        - Dates (priority, publication)
        - Assignees (entreprises propriétaires)
        - Liens (complétés avec https://patents.google.com)
        - Nettoyage des suffixes de langue (ex: "(en)")
        """
        html = """
        <html>
        <body>
            <h2>Cited By (2)</h2>
            <table>
                <tr>
                    <th>Publication number</th>
                    <th>Priority date</th>
                    <th>Assignee</th>
                </tr>
                <tr>
                    <td><a href="/patent/US1234567">US1234567</a></td>
                    <td>2020-01-15</td>
                    <td>Acme Corp</td>
                </tr>
                <tr>
                    <td><a href="/patent/EP9999999B1">EP9999999B1 (en)</a></td>
                    <td>2019-12-01</td>
                    <td>Beta Inc</td>
                </tr>
            </table>
        </body>
        </html>
        """

        result = parse_cited_by_table(html)

        assert len(result) == 2

        # Premier brevet
        assert result[0]["publication_number"] == "US1234567"
        assert result[0]["priority_date"] == "2020-01-15"
        assert result[0]["assignee"] == "Acme Corp"
        # Les liens relatifs doivent être complétés
        assert result[0]["link"] == "https://patents.google.com/patent/US1234567"

        # Deuxième brevet - vérifier nettoyage du suffixe "(en)"
        assert result[1]["publication_number"] == "EP9999999B1"
        assert "(en)" not in result[1]["publication_number"]

    def test_parse_no_cited_by_section(self):
        """
        Test: HTML sans section "Cited By" → liste vide.

        Si le brevet n'est cité par personne, pas de section "Cited By".
        """
        html = """
        <html>
        <body>
            <h2>Patent Citations (5)</h2>
            <p>Other content</p>
        </body>
        </html>
        """

        result = parse_cited_by_table(html)

        assert result == []

    def test_parse_missing_optional_columns(self):
        """
        Test: Table avec colonnes optionnelles manquantes.

        Certaines tables n'ont que publication_number et assignee.
        Les autres colonnes doivent être None.
        """
        html = """
        <html>
        <body>
            <h2>Cited By (1)</h2>
            <table>
                <tr>
                    <th>Publication number</th>
                    <th>Assignee</th>
                </tr>
                <tr>
                    <td><a href="/patent/US777777">US777777</a></td>
                    <td>Delta Corp</td>
                </tr>
            </table>
        </body>
        </html>
        """

        result = parse_cited_by_table(html)

        assert len(result) == 1
        assert result[0]["publication_number"] == "US777777"
        assert result[0]["assignee"] == "Delta Corp"
        # Colonnes manquantes = None
        assert result[0]["priority_date"] is None
        assert result[0]["title"] is None

    def test_parse_empty_and_none_inputs(self):
        """Test: Inputs vides/None → liste vide."""
        assert parse_cited_by_table("") == []
        assert parse_cited_by_table(None) == []

    def test_parse_case_insensitive_heading(self):
        """
        Test: Détection case-insensitive du heading "Cited By".

        "Cited By", "cited by", "CITED BY" → tous valides.
        """
        html = """
        <html>
        <body>
            <h2>cited by (1)</h2>
            <table>
                <tr><th>Publication number</th></tr>
                <tr><td><a href="/patent/US999">US999</a></td></tr>
            </table>
        </body>
        </html>
        """

        result = parse_cited_by_table(html)

        assert len(result) == 1
        assert result[0]["publication_number"] == "US999"


# =============================================================================
# Test parse_current_assignee
# =============================================================================
# Cette fonction extrait l'assignee actuel (entreprise propriétaire du brevet)
# depuis une definition list HTML (<dl><dt><dd>)

class TestParseCurrentAssignee:
    """Tests for parse_current_assignee function."""

    def test_parse_current_assignee_with_country_code(self):
        """
        Test: Extraire "Current Assignee" et enlever le code pays.

        Format Google Patents : <dt>Current Assignee</dt><dd>Company Name, US</dd>
        La fonction doit enlever ", US" (ou FR, JP, etc.)
        """
        html = """
        <html>
        <body>
            <dl>
                <dt>Current Assignee</dt>
                <dd>Acme Corporation, US</dd>
            </dl>
        </body>
        </html>
        """

        result = parse_current_assignee(html)

        assert result == "Acme Corporation"
        assert ", US" not in result

    def test_parse_assignee_fallback(self):
        """
        Test: Fallback sur "Assignee" si "Current Assignee" absent.

        Préfère "Current Assignee" mais accepte "Assignee" en fallback.
        """
        html = """
        <html>
        <body>
            <dl>
                <dt>Assignee</dt>
                <dd>Beta Inc, FR</dd>
            </dl>
        </body>
        </html>
        """

        result = parse_current_assignee(html)

        assert result == "Beta Inc"

    def test_parse_no_assignee_found(self):
        """Test: Pas d'assignee → string vide."""
        html = """
        <html>
        <body>
            <dl>
                <dt>Inventors</dt>
                <dd>John Smith</dd>
            </dl>
        </body>
        </html>
        """

        result = parse_current_assignee(html)

        assert result == ""

    def test_parse_empty_and_none_inputs(self):
        """Test: Inputs vides/None → string vide."""
        assert parse_current_assignee("") == ""
        assert parse_current_assignee(None) == ""

    def test_parse_case_insensitive(self):
        """Test: Matching case-insensitive pour "assignee"."""
        html = """
        <html>
        <body>
            <dl>
                <dt>current assignee</dt>
                <dd>Lowercase Corp</dd>
            </dl>
        </body>
        </html>
        """

        result = parse_current_assignee(html)

        assert result == "Lowercase Corp"


# =============================================================================
# Test parse_assignees_from_table
# =============================================================================
# Cette fonction extrait les assignees depuis une table HTML sous un heading
# spécifique (ex: "Patent Citations" pour les citations backward)

class TestParseAssigneesFromTable:
    """Tests for parse_assignees_from_table function."""

    def test_parse_assignees_with_deduplication(self):
        """
        Test: Extraire assignees et dédupliquer en préservant l'ordre.

        Si "Alpha Corp" apparaît 2 fois, ne le garder qu'une fois
        (à sa position de première apparition).
        """
        html = """
        <html>
        <body>
            <h2>Patent Citations (3)</h2>
            <table>
                <tr>
                    <th>Publication number</th>
                    <th>Assignee</th>
                </tr>
                <tr>
                    <td>US1111</td>
                    <td>Alpha Corp</td>
                </tr>
                <tr>
                    <td>US2222</td>
                    <td>Beta Inc</td>
                </tr>
                <tr>
                    <td>US3333</td>
                    <td>Alpha Corp</td>
                </tr>
            </table>
        </body>
        </html>
        """

        result = parse_assignees_from_table(html, "Patent Citations")

        # 2 assignees uniques
        assert len(result) == 2
        # Ordre de première apparition préservé
        assert result[0] == "Alpha Corp"
        assert result[1] == "Beta Inc"

    def test_parse_no_heading_found(self):
        """Test: Heading non trouvé → liste vide."""
        html = """
        <html>
        <body>
            <h2>Other Section</h2>
            <table>
                <tr><th>Assignee</th></tr>
                <tr><td>Some Corp</td></tr>
            </table>
        </body>
        </html>
        """

        result = parse_assignees_from_table(html, "Patent Citations")

        assert result == []

    def test_parse_no_assignee_column(self):
        """Test: Table sans colonne "Assignee" → liste vide."""
        html = """
        <html>
        <body>
            <h2>Patent Citations</h2>
            <table>
                <tr>
                    <th>Publication number</th>
                    <th>Title</th>
                </tr>
                <tr>
                    <td>US123</td>
                    <td>Some title</td>
                </tr>
            </table>
        </body>
        </html>
        """

        result = parse_assignees_from_table(html, "Patent Citations")

        assert result == []

    def test_parse_whitespace_normalization(self):
        """
        Test: Normaliser les espaces dans les noms d'assignees.

        Le HTML peut avoir des espaces multiples/tabs/newlines.
        La fonction doit les normaliser en un seul espace.
        """
        html = """
        <html>
        <body>
            <h2>Patent Citations</h2>
            <table>
                <tr>
                    <th>Assignee</th>
                </tr>
                <tr>
                    <td>  Company   With    Spaces  </td>
                </tr>
            </table>
        </body>
        </html>
        """

        result = parse_assignees_from_table(html, "Patent Citations")

        assert len(result) == 1
        assert result[0] == "Company With Spaces"

    def test_parse_case_insensitive_heading(self):
        """Test: Matching case-insensitive et partiel du heading."""
        html = """
        <html>
        <body>
            <h2>PATENT CITATIONS</h2>
            <table>
                <tr><th>Assignee</th></tr>
                <tr><td>Test Corp</td></tr>
            </table>
        </body>
        </html>
        """

        # Matching partiel "Citations" dans "PATENT CITATIONS"
        result = parse_assignees_from_table(html, "citations")

        assert len(result) == 1
        assert result[0] == "Test Corp"


# =============================================================================
# Test has_cited_by_section
# =============================================================================
# Cette fonction vérifie si le HTML contient une section "Cited By"
# (indique que le brevet est cité par d'autres = signe d'impact)

class TestHasCitedBySection:
    """Tests for has_cited_by_section function."""

    def test_has_cited_by_section_true(self):
        """
        Test: Heading "Cited By" présent → True.

        Format: <h2>Cited By (5)</h2> ou <h2>Cited By</h2>
        """
        test_cases = [
            "<h2>Cited By (5)</h2>",
            "<h2>Cited By</h2>",
            "<h1>cited by (10)</h1>",  # Case-insensitive + h1
        ]

        for html in test_cases:
            result = has_cited_by_section(html)
            assert result is True

    def test_has_cited_by_section_false(self):
        """Test: Pas de heading "Cited By" → False."""
        html = """
        <html>
        <body>
            <h2>Patent Citations (5)</h2>
            <p>Other content</p>
        </body>
        </html>
        """

        result = has_cited_by_section(html)

        assert result is False

    def test_has_cited_by_false_positives(self):
        """
        Test: IMPORTANT - Éviter les faux positifs.

        Le texte "cited by" dans un paragraphe ou caption
        ne doit PAS être détecté (seulement les vrais headings h1-h4).
        """
        html = """
        <html>
        <body>
            <p>This patent was cited by examiner</p>
            <caption>Cited by the inventor</caption>
            <div>Cited By</div>
        </body>
        </html>
        """

        result = has_cited_by_section(html)

        # Ne doit PAS détecter ces faux positifs
        assert result is False

    def test_has_cited_by_empty_and_none_inputs(self):
        """Test: Inputs vides/None → False."""
        assert has_cited_by_section("") is False
        assert has_cited_by_section(None) is False

    def test_has_cited_by_different_heading_levels(self):
        """Test: Détection dans h1, h2, h3, h4."""
        for level in [1, 2, 3, 4]:
            html = f"<h{level}>Cited By (5)</h{level}>"
            result = has_cited_by_section(html)
            assert result is True
