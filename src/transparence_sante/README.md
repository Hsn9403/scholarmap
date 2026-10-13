# Module Transparence Santé

## Vue d'ensemble

Ce module interroge l'API publique française **Transparence Santé** pour détecter les liens financiers entre professionnels de santé et entreprises pharmaceutiques/dispositifs médicaux.

## Architecture

```
src/transparence_sante/
├── __init__.py           # Exports publics
├── client.py             # Client API Transparence Santé
└── README.md            # Cette documentation

discover_corporates_from_transparence_sante.py  # Script principal
```

## Fonctionnalités

### 1. Recherche par nom complet
- Recherche les déclarations financières pour une personne (prénom + nom)
- Filtre par montant minimum (par défaut : 10 000 €)
- Retourne toutes les entreprises ayant versé des paiements au-dessus du seuil

### 2. Désambiguisation automatique des co-auteurs
- Utilise les mêmes stratégies que Clinical Trials :
  - Résolution via publications (la plus fiable)
  - Résolution via API externes (Scholar, OpenAlex)
- Skip automatique des co-auteurs avec initiales seulement

### 3. Stockage en base de données
- Crée des liens `Scientist → Corporate` via la table `scientist_corporate`
- Type d'affiliation : `transparence_sante`
- Stocke les preuves dans `evidence_data` (JSON) :
  - ID de la déclaration
  - Date du paiement
  - Montant
  - Raison (formation, contrat, etc.)
  - SIREN de l'entreprise

## Utilisation

### Ligne de commande

```bash
# Recherche simple (sans ajout en base)
python3 discover_corporates_from_transparence_sante.py "Andre Imbert"

# Avec paramètres
python3 discover_corporates_from_transparence_sante.py "Andre Imbert" \
  --max-coauthors 50 \
  --min-amount 10000 \
  --add-to-db

# Inclure les co-auteurs avec initiales
python3 discover_corporates_from_transparence_sante.py "Andre Imbert" \
  --no-skip-initials
```

### Paramètres

- `researcher` : Nom du chercheur principal
- `--max-coauthors` : Nombre max de co-auteurs à scanner (défaut: 50)
- `--min-amount` : Montant minimum en euros (défaut: 10,000)
- `--no-skip-initials` : Inclure co-auteurs avec initiales uniquement
- `--add-to-db` : Persister les résultats en base de données

### Intégration dans un script Python

```python
from discover_corporates_from_transparence_sante import (
    discover_corporates_from_transparence_sante,
    add_transparence_sante_to_database
)

# Rechercher les liens financiers
coauthor_companies, coauthor_declarations = discover_corporates_from_transparence_sante(
    researcher_name="Andre Imbert",
    max_coauthors=50,
    min_amount=10000.0
)

# Ajouter à la base de données
add_transparence_sante_to_database(
    researcher_name="Andre Imbert",
    coauthor_companies=coauthor_companies,
    coauthor_declarations=coauthor_declarations
)
```

## Intégration dans le workflow existant

Pour intégrer ce module **après** Clinical Trials dans votre script principal :

```python
# 1. D'abord : Clinical Trials
from discover_corporates_from_clinical_trials import (
    discover_corporates_from_coauthors_clinical_trials,
    add_clinical_trials_corporates_to_database
)

ct_coauthor_corps, ct_coauthor_links = discover_corporates_from_coauthors_clinical_trials(
    researcher_name,
    max_coauthors=20
)

# 2. Ensuite : Transparence Santé
from discover_corporates_from_transparence_sante import (
    discover_corporates_from_transparence_sante,
    add_transparence_sante_to_database
)

ts_coauthor_companies, ts_coauthor_declarations = discover_corporates_from_transparence_sante(
    researcher_name,
    max_coauthors=50,
    min_amount=10000.0
)

# 3. Ajouter les deux à la base de données
if ct_coauthor_corps:
    # Ajouter Clinical Trials
    for coauthor, corps in ct_coauthor_corps.items():
        add_clinical_trials_corporates_to_database(
            coauthor,
            corps,
            ct_coauthor_links.get(coauthor, [])
        )

if ts_coauthor_companies:
    # Ajouter Transparence Santé
    add_transparence_sante_to_database(
        researcher_name,
        ts_coauthor_companies,
        ts_coauthor_declarations
    )
```

## Base de données

### Table scientist_corporate

| Colonne | Type | Description |
|---------|------|-------------|
| scientist_id | INTEGER | ID du scientifique (co-auteur) |
| corporate_id | INTEGER | ID de l'entreprise |
| affiliation_type | VARCHAR(50) | Type : `transparence_sante` |
| notes | TEXT | Résumé : nb de paiements, total |
| evidence_data | JSON | Preuves détaillées (voir ci-dessous) |

### Structure de evidence_data

```json
{
  "evidence": [
    {
      "declaration_id": "20266833",
      "date": "2020-09-11",
      "amount": 50000.0,
      "reason": "Formation",
      "reason_detail": null,
      "declaration_type": "avantage",
      "sector": "Dispositifs médicaux",
      "siren": "329938245",
      "status": "Publié",
      "publication_date": "2021-03-01"
    }
  ]
}
```

## API Transparence Santé

### Caractéristiques
- **Gratuite** : Aucune clé API requise
- **Publique** : Données ouvertes du gouvernement français
- **Exhaustive** : 9,5+ millions de déclarations
- **À jour** : Données récentes (2017-2025)
- **Limite par requête** : 100 résultats maximum

### Gestion de la limite de 100 résultats

Si un professionnel a plus de 100 déclarations > seuil, plusieurs options :

1. **Augmenter le seuil** (recommandé pour ce projet)
   ```python
   # Au lieu de 10,000€, utiliser 20,000€ ou plus
   result = client.search_by_name("Duval", "Edgar", min_amount=20000.0)
   ```

2. **Implémenter la pagination** (si vraiment nécessaire)
   - Utiliser `offset` dans l'API
   - Faire plusieurs requêtes avec offset croissant
   - Non implémenté actuellement

3. **Filtrer par année/période**
   - Ajouter des filtres temporels dans la clause `where`
   - Faire plusieurs requêtes par période

### Endpoints utilisés

```
BASE: https://www.transparence.sante.gouv.fr/api/explore/v2.1

GET /catalog/datasets/declarations/records
  ?where=identite='DUVAL' AND prenom='EDGAR' AND montant>10000
  &limit=500
  &order_by=montant desc
```

### Limites
- **Limite de résultats : 100 par requête maximum** (contrainte de l'API)
- Recherche par nom exact (prénom + nom)
- Nécessite une désambiguisation préalable
- Pas de recherche floue
- Pas de pagination automatique (à implémenter si besoin)

## Types de déclarations

Le module détecte plusieurs types de liens financiers :

- **Formation** : Sessions de formation médicale
- **Autres prestations de services** : Consulting, expertise
- **Contrat d'intervenant** : Speaker fees, conférences
- **Contrat d'expert scientifique** : Advisory boards
- **Location d'espaces** : Organisation d'événements
- **Don de fonctionnement** : Dons aux services/laboratoires
- **Frais de transport** : Déplacements
- **Hospitalité** : Repas, hébergement

## Exemple de résultat

```
================================================================================
DISCOVERING CORPORATES FROM TRANSPARENCE SANTÉ
Main Researcher: Edgar Duval
Payment threshold: ≥10,000 €
================================================================================

[1] Scanning: Jean-Paul Martin
  ✓ Found 3 company(ies): MEDTRONIC FRANCE, COOK FRANCE, BOSTON SCIENTIFIC
    Total amount: 142,500.00 €

[2] Scanning: Marie Dupont
  → No declarations ≥10,000€ found

================================================================================
SUMMARY
================================================================================
Co-authors processed: 15
Co-authors with declarations: 3
Total unique companies: 8
Companies: BARD FRANCE, BOSTON SCIENTIFIC, COOK FRANCE, GETINGE, MEDTRONIC...
```

## Migration base de données

Une migration a été créée pour ajouter la colonne `evidence_data` :

```bash
python3 src/database/migrate_add_metadata_to_scientist_corporate.py
```

Cette migration :
- Ajoute `evidence_data JSON` à `scientist_corporate`
- Compatible PostgreSQL
- Idempotente (peut être exécutée plusieurs fois)

## Notes importantes

1. **Nom réservé** : `metadata` est réservé par SQLAlchemy → utilisez `evidence_data`
2. **Montants** : Convertis en entiers pour l'API (pas de décimales)
3. **Noms** : Convertis en MAJUSCULES pour la recherche
4. **Désambiguisation** : Essentielle - les initiales seules donnent des faux positifs

## Dépendances

- `requests` : Appels API HTTP
- `sqlalchemy` : ORM base de données
- Modules existants :
  - `src.scholar` : Recherche co-auteurs
  - `src.utils` : Résolution de noms
  - `src.database` : Accès base de données
