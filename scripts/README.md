# Scripts d'Exécution - Scholarmap

Ce dossier contient **tous les scripts d'exécution** du projet, organisés par fonction.

---

## Script Principal (RECOMMANDÉ)

### `build_ultra_complete_graph.py`
**Le script tout-en-un qui fait TOUT automatiquement**

**Ce qu'il fait :**
1. Scholar : Publications + Co-auteurs
2. Patents : Brevets + Assignees
3. Clinical Trials : Co-auteurs → Corporates (sponsors)
4. Transparence Santé : Co-auteurs → Corporates (paiements)
5. Base de données : Stockage de tous les corporates
6. Graphe : Génération HTML interactive

**Usage :**
```bash
# Analyse complète avec paramètres par défaut
python3 scripts/build_ultra_complete_graph.py "Researcher Name"

# Avec options personnalisées
python3 scripts/build_ultra_complete_graph.py "Edgar Duval" \
  --max-publications 150 \
  --max-coauthors-ct 50 \
  --min-amount-ts 20000

# Sauter certaines sources
python3 scripts/build_ultra_complete_graph.py "Andre Imbert" \
  --skip-clinical-trials \
  --skip-transparence-sante
```

---

## Scripts de Génération de Graphe

### `build_complete_graph.py`
Graphe complet avec Scholar + Patents + Industry (depuis DB uniquement)

**Usage :**
```bash
python3 scripts/build_complete_graph.py "Researcher Name"
python3 scripts/build_complete_graph.py "Name" --max-publications 100
```

**Note :** Ne cherche PAS Clinical Trials ni Transparence Santé, récupère uniquement les corporates déjà en DB.

---

## Scripts de Découverte de Corporates

### `discover_corporates_from_clinical_trials.py`
Cherche les corporates via Clinical Trials (co-auteurs comme PIs)

**Usage :**
```bash
# Sans sauvegarder en DB
python3 scripts/discover_corporates_from_clinical_trials.py "Name" --include-coauthors

# Sauvegarder en DB
python3 scripts/discover_corporates_from_clinical_trials.py "Name" \
  --include-coauthors \
  --add-to-db
```

---

### `discover_corporates_from_transparence_sante.py`
Cherche les paiements > 10k€ dans Transparence Santé

**Usage :**
```bash
# Sans sauvegarder
python3 scripts/discover_corporates_from_transparence_sante.py "Edgar Duval"

# Avec options
python3 scripts/discover_corporates_from_transparence_sante.py "Name" \
  --max-coauthors 50 \
  --min-amount 15000 \
  --add-to-db
```

---

### `discover_corporates_from_patents.py`
Cherche les corporates via assignees de brevets

**Usage :**
```bash
python3 scripts/discover_corporates_from_patents.py "Name" --add-to-db
```

---

### `example_complete_corporate_discovery.py`
Clinical Trials + Transparence Santé combinés

**Usage :**
```bash
python3 scripts/example_complete_corporate_discovery.py "Name" --add-to-db
```

---

## Scripts Utilitaires

### `add_edgar_duval_standalone.py`
Script standalone pour ajouter Edgar Duval et ses déclarations Transparence Santé en DB

**Usage :**
```bash
python3 scripts/add_edgar_duval_standalone.py
```

---

## Architecture Modulaire

```
scripts/
├── README.md                                    # Ce fichier
├── build_ultra_complete_graph.py               #  SCRIPT PRINCIPAL
├── build_complete_graph.py                     # Graphe (Scholar + Patents + DB)
├── discover_corporates_from_clinical_trials.py # Clinical Trials
├── discover_corporates_from_transparence_sante.py # Transparence Santé
├── discover_corporates_from_patents.py         # Patents → Corporates
├── example_complete_corporate_discovery.py     # CT + TS combinés
├── add_edgar_duval_standalone.py              # Utilitaire
└── modules/                                     # Modules internes
    ├── __init__.py
    ├── phase1_data_collection.py               # Collecte de données
    ├── phase2_database_storage.py              # Stockage en DB
    └── phase3_graph_generation.py              # Génération graphe
```

---

## Workflow Recommandé

### Pour une analyse complète (RECOMMANDÉ)

```bash
# Tout en un seul script !
python3 scripts/build_ultra_complete_graph.py "Researcher Name"
```

### Pour une analyse étape par étape

```bash
# 1. Découvrir les corporates et les sauvegarder
python3 scripts/example_complete_corporate_discovery.py "Name" --add-to-db

# 2. Générer le graphe (récupère les corporates de la DB)
python3 scripts/build_complete_graph.py "Name"
```

---

## Conseils

- **Utilisez `build_ultra_complete_graph.py` pour tout avoir** d'un coup
- Pour les chercheurs médicaux : laissez Transparence Santé activé
- Pour les chercheurs académiques : utilisez `--skip-transparence-sante`
- Pour économiser l'API SerpAPI : utilisez `--skip-patents`

---

## Paramètres Importants

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `--max-publications` | 100 | Nb de publications Scholar |
| `--max-coauthors-ct` | 30 | Nb de co-auteurs pour Clinical Trials |
| `--max-coauthors-ts` | 50 | Nb de co-auteurs pour Transparence Santé |
| `--min-amount-ts` | 10000 | Montant min en € pour Transparence Santé |
| `--skip-clinical-trials` | false | Sauter Clinical Trials |
| `--skip-transparence-sante` | false | Sauter Transparence Santé |
| `--skip-patents` | false | Sauter Patents |

---

**Tout est maintenant centralisé dans `scripts/` !** 
