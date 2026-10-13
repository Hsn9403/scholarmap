# Tests Scholarmap

Suite de tests complète pour le projet Scholarmap.

## Structure des tests

```
tests/
├── conftest.py                      # Configuration pytest (fixtures globales)
├── test_helpers.py                  # Tests des fonctions utilitaires (normalization, dates, etc.)
├── test_utils_graph.py              # Tests des fonctions de graphe (nodes, edges, dedup)
├── test_utils_patents.py            # Tests des fonctions brevets (parsing, matching)
├── test_utils_scholar.py            # Tests des fonctions Scholar (disambiguation, scoring)
├── test_api_client.py               # Tests du client API avec gestion d'erreurs
├── test_models.py                   # Tests des modèles de données (dataclasses)
├── test_serpapi_google.py           # Tests d'intégration SerpAPI (existant)
└── test_find_scholar_candidates.py  # Tests de recherche Scholar (existant)
```

## Exécution des tests

### Tous les tests
```bash
pytest src/tests -v
```
ou
```bash
./run_tests.sh
```

### Tests unitaires uniquement (rapides)
```bash
pytest src/tests -m "not integration" -v
```
ou
```bash
./run_tests.sh unit
```

### Tests d'intégration (nécessite SERPAPI_KEY)
```bash
pytest src/tests -m integration -v
```
ou
```bash
./run_tests.sh integration
```

### Tests avec couverture de code
```bash
pytest src/tests --cov=src --cov-report=html
```
ou
```bash
./run_tests.sh coverage
```

### Tests rapides uniquement
```bash
./run_tests.sh fast
```

## Organisation des tests

### Tests unitaires (`test_helpers.py`, `test_utils_*.py`, `test_models.py`)
- **Rapides** : Pas de dépendances externes
- **Isolés** : Utilisent des mocks pour les dépendances
- **Complets** : Couvrent les cas normaux, limites et erreurs

### Tests d'intégration (`test_serpapi_google.py`, `test_find_scholar_candidates.py`)
- **Utilisent VCR** : Enregistrent les réponses API pour replay
- **Nécessitent API key** : Seulement pour le premier run (enregistrement)
- **Marqués** : `@pytest.mark.integration`

## Couverture des fonctions critiques

### Helpers (`test_helpers.py`)
- `strip_accents_basic()` - Suppression d'accents
- `_safe_int()` - Conversion sécurisée en entier
- `_slug()` - Génération de slugs
- `parse_yyyy_mm_dd()` - Parsing de dates
- `normalize_for_match()` - Normalisation de noms

### Graph (`test_utils_graph.py`)
- `_node_id()` - Génération d'IDs de nœuds
- `_patent_node_id()` - IDs de brevets
- `_dedup_preserve()` - Déduplication avec ordre
- `_is_placeholder_company()` - Détection de placeholders
- `norm_org_tokens()` - Normalisation d'organisations
- `same_org_strong()` - Matching d'organisations

### Patents (`test_utils_patents.py`)
- `normalize_patent_id_for_html()` - Normalisation d'IDs brevets
- `split_name_parts()` - Découpage de noms
- `same_person()` - Matching de personnes
- `remove_input_name_from_inventors()` - Filtrage d'inventeurs

### Scholar (`test_utils_scholar.py`)
- `_name_matches_query()` - Matching de noms Scholar
- `_score_candidate()` - Scoring pour disambiguation
- `extract_metric_from_cited_by_table()` - Extraction de métriques

### API Client (`test_api_client.py`)
- `get_serpapi_key()` - Récupération de clé API
- `serp_search()` - Recherche avec gestion d'erreurs
- `serp_search_html()` - Recherche HTML

### Models (`test_models.py`)
- Tous les dataclasses (ScholarData, PatentItem, etc.)
- Validation des champs obligatoires/optionnels

## Ajouter de nouveaux tests

### Template pour un test unitaire
```python
class TestMyFunction:
    """Tests for my_function()."""

    def test_normal_case(self):
        """Test the normal/happy path."""
        result = my_function("input")
        assert result == "expected"

    def test_edge_case(self):
        """Test boundary conditions."""
        result = my_function("")
        assert result == "default"

    def test_error_case(self):
        """Test error handling."""
        with pytest.raises(ValueError):
            my_function(None)
```

### Template pour un test avec mock
```python
@patch('src.module.external_dependency')
def test_with_mock(self, mock_dep):
    """Test with mocked dependency."""
    mock_dep.return_value = "fake_value"

    result = my_function()

    assert result == "expected"
    mock_dep.assert_called_once()
```

## Bonnes pratiques

1. **Un test = une assertion principale** (ou un groupe cohérent)
2. **Noms descriptifs** : `test_removes_duplicates_while_preserving_order`
3. **AAA pattern** : Arrange (setup) → Act (execute) → Assert (verify)
4. **Isoler les tests** : Pas de dépendances entre tests
5. **Mock les I/O** : API calls, file system, database

## Dépendances de test

```bash
pip install pytest pytest-cov pytest-mock python-vcrpy
```

## CI/CD

Les tests peuvent être intégrés dans un pipeline CI/CD :

```yaml
# Exemple GitHub Actions
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest src/tests --cov=src --cov-report=xml
```

## Métriques de couverture

Objectif : **>80%** de couverture de code

Pour voir le rapport détaillé :
```bash
./run_tests.sh coverage
open htmlcov/index.html  # macOS
```
