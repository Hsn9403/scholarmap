# ClinicalTrials.gov - Méthodologie de Détection des Liens Chercheur-Corporate

## Vue d'ensemble

Ce module détecte les collaborations entre chercheurs académiques et entreprises (corporates) via l'analyse des essais cliniques enregistrés sur ClinicalTrials.gov.

**Objectif:** Identifier de manière irréfutable les liens entre un chercheur et une entreprise lorsque le chercheur participe à un essai clinique impliquant cette entreprise.

---

## Principe Fondamental

Un lien **chercheur → corporate** est considéré comme **VALIDE** si et seulement si :

### 1. Le chercheur est **Principal Investigator (PI)** de l'étude

**Règle stricte:** Le chercheur doit avoir le rôle explicite de :
- "Principal Investigator"
- "Study Director"
- Ou équivalent (roles contenant "PRINCIPAL_INVESTIGATOR")

**Justification:** Le PI a la responsabilité scientifique de l'étude et un lien direct avec le sponsor/produit.

**Contre-exemples rejetés:**
- Co-investigator
- Site investigator
- Sub-investigator
- Study coordinator

---

### 2. Le corporate apparaît **explicitement** dans l'étude

Le corporate doit être détecté dans **AU MOINS UN** des champs suivants :

#### A. **Sponsor ou Lead Sponsor**
Le corporate finance directement l'étude.

**Exemple:**
```
Sponsor: Medtronic
Lead Sponsor: Boston Scientific
→ LIEN VALIDE
```

#### B. **Dispositif/Traitement utilisé (Intervention)**
Le corporate fournit le dispositif médical ou le médicament étudié.

**Exemple:**
```
Intervention: Drug Coated Balloon - In.Pact (Medtronic)
→ LIEN VALIDE via produit Medtronic
```

**Cas particulier - Mapping Produit → Corporate:**
Certains produits sont identifiés par leur nom commercial sans mention explicite du fabricant.

Exemples de mapping :
- **In.Pact** → Medtronic
- **Taxus** → Boston Scientific
- **Xience** → Abbott
- **Resolute** → Medtronic

Le système maintient une base de connaissances des principaux dispositifs médicaux et leurs fabricants.

---

## Méthodologie Détaillée

### Étape 1: Recherche des Études

```python
# Requête API ClinicalTrials.gov v2
GET /api/v2/studies?query.term={researcher_name}&format=json
```

**Note:** L'API v2 ne propose pas de filtre spécifique par investigator. On utilise une recherche full-text puis filtrage manuel.

### Étape 2: Filtrage par Rôle PI

Pour chaque étude trouvée :

1. **Extraction des investigateurs** depuis `protocolSection.contactsLocationsModule`
2. **Matching du nom** (normalisé, insensible à la casse, accents)
3. **Vérification du rôle** :
   ```python
   if role.lower() in ["principal investigator", "principal_investigator", "study_director"]:
       → VALIDE
   else:
       → REJETÉ
   ```

### Étape 3: Détection du Corporate

Pour chaque étude où le chercheur est PI :

#### 3A. Extraction des Sponsors
```json
{
  "sponsorCollaboratorsModule": {
    "leadSponsor": {"name": "Medtronic"},
    "collaborators": [{"name": "University Hospital"}]
  }
}
```

#### 3B. Extraction des Interventions
```json
{
  "armsInterventionsModule": {
    "interventions": [
      {
        "name": "In.Pact Drug-Coated Balloon",
        "description": "Paclitaxel-eluting balloon angioplasty..."
      }
    ]
  }
}
```

#### 3C. Détection du Corporate

**Méthode 1: Nom direct du corporate**
```
"Medtronic" in sponsor_name → Medtronic détecté
```

**Méthode 2: Produit → Corporate mapping**
```
"In.Pact" in intervention_name → Medtronic détecté (via mapping)
```

### Étape 4: Validation et Preuve

Pour chaque lien détecté, on enregistre :

```python
CorporateLink(
    researcher="Edgar Duval",
    corporate="Medtronic",
    role="Principal Investigator",
    nct_id="NCT02599389",
    study_title="...",
    detection_field="Intervention",  # Ou "Sponsor"
    detection_value="In.Pact Drug-Coated Balloon",
    study_url="https://clinicaltrials.gov/study/NCT02599389",
    confidence=0.95
)
```

---

## Règles Strictes (Pas d'Inférence)

### Ce qui est ACCEPTÉ

| Cas | Validation |
|-----|-----------|
| Chercheur est PI + Sponsor = Corporate |  VALIDE |
| Chercheur est PI + Intervention contient produit Corporate |  VALIDE |
| Chercheur est PI + Sponsor académique + Dispositif Corporate |  VALIDE |

### Ce qui est REJETÉ

| Cas | Raison du rejet |
|-----|----------------|
| Chercheur est co-investigator + Sponsor = Corporate |  Pas PI |
| Chercheur est PI + Sponsor académique + Aucun produit corporate |  Pas de lien corporate explicite |
| Chercheur mentionné dans description mais pas dans investigateurs |  Rôle non vérifié |
| Produit inconnu (pas dans mapping) + Sponsor académique |  Pas de preuve corporate |

---

## Exemples Concrets

### Exemple 1: Lien via Sponsor Direct

**Étude:** NCT12345678

```
Principal Investigator: Dr. Jean Dupont
Sponsor: Medtronic
Intervention: Standard care
```

**Résultat:**
```
LIEN VALIDE
Jean Dupont → Medtronic
Via: Sponsor direct
Confiance: 0.95
```

---

### Exemple 2: Lien via Produit (Cas In.Pact)

**Étude:** NCT02599389

```
Principal Investigator: Dr. Edgar Duval
Sponsor: University Hospital, Bordeaux
Intervention: In.Pact Drug-Coated Balloon angioplasty
```

**Processus:**
1. Edgar Duval identifié comme PI 
2. Sponsor = University Hospital (pas corporate)
3. Intervention contient "In.Pact"
4. Mapping: In.Pact → Medtronic 

**Résultat:**
```
LIEN VALIDE
Edgar Duval → Medtronic
Via: Intervention (produit In.Pact)
Confiance: 0.95
```

---

### Exemple 3: REJET - Pas PI

**Étude:** NCT99999999

```
Principal Investigator: Dr. Marie Martin
Co-Investigator: Dr. Jean Dupont
Sponsor: Medtronic
```

**Recherche:** Dr. Jean Dupont

**Résultat:**
```
REJETÉ
Raison: Jean Dupont n'est pas PI (rôle: Co-Investigator)
```

---

## Base de Connaissances - Produits Médicaux

### Medtronic

| Produit | Domaine |
|---------|---------|
| In.Pact | Drug-Coated Balloon (artères périphériques) |
| Resolute | Stent coronaire |
| CoreValve | Valve aortique transcathéter |
| Evolut | Valve aortique transcathéter |
| Endurant | Endoprothèse aortique |
| Valiant | Endoprothèse thoracique |

### Boston Scientific

| Produit | Domaine |
|---------|---------|
| Taxus | Stent coronaire |
| Promus | Stent coronaire |
| Synergy | Stent coronaire bioabsorbable |
| Watchman | Occlusion auriculaire |
| Ranger | Ballon angioplastie |

### Abbott

| Produit | Domaine |
|---------|---------|
| Xience | Stent coronaire |
| Absorb | Stent bioabsorbable |
| MitraClip | Réparation valvulaire mitrale |
| Portico | Valve aortique |

**Note:** Cette liste est extensible et doit être enrichie au fur et à mesure.

---

## Limites de la Méthodologie

### 1. Dépendance à l'enregistrement ClinicalTrials

**Limitation:** Seules les études enregistrées sur ClinicalTrials.gov sont détectées.

**Impact:** Les collaborations via essais non enregistrés ou enregistrés ailleurs (ex: EudraCT) ne sont pas capturées.

### 2. Qualité des Métadonnées

**Limitation:** Dépend de la complétude des données saisies par les sponsors.

**Exemples problématiques:**
- Nom de produit abrégé ou mal orthographié
- Liste d'investigateurs incomplète
- Rôles mal définis

### 3. Mapping Produit → Corporate

**Limitation:** Nécessite une maintenance de la base de connaissances.

**Risques:**
- Produits récents non répertoriés
- Changements de propriété (acquisitions)
- Noms de produits régionaux différents

---

## Niveaux de Confiance

| Niveau | Condition | Confiance |
|--------|-----------|-----------|
| **LEVEL_A** | Nom corporate explicite dans Sponsor | 0.95 |
| **LEVEL_A** | Produit connu dans mapping + PI vérifié | 0.95 |
| **LEVEL_B** | Produit partiel (substring) dans intervention | 0.80 |

---

## Utilisation

### API Python

```python
from src.clinical_trials import search_clinical_trials_corporate

# Recherche simple
results = search_clinical_trials_corporate("Edgar Duval")

# Affichage
for link in results.corporate_links:
    print(f"{link.researcher} → {link.corporate}")
    print(f"  Via: {link.detection_field}")
    print(f"  Étude: {link.nct_id}")
    print(f"  URL: {link.study_url}")
```

### Ajout de Corporates Personnalisés

```python
from src.clinical_trials import ClinicalTrialsClient

# Liste personnalisée
custom_corporates = ["medtronic", "siemens", "philips"]

client = ClinicalTrialsClient(corporate_keywords=custom_corporates)
results = client.find_corporate_links("Nom Chercheur")
```

---

## Validation et Traçabilité

Chaque lien détecté inclut :

1. **NCT ID** - Identifiant unique de l'étude
2. **URL directe** - Lien vers ClinicalTrials.gov
3. **Champ de détection** - Où le corporate a été trouvé
4. **Valeur exacte** - Texte brut du champ
5. **Niveau de confiance** - 0.80 à 0.95

**Principe:** Toute détection doit être **vérifiable manuellement** par un humain en quelques clics.

---

## Évolutions Futures

### 1. Enrichissement du Mapping Produit → Corporate
- Intégration base FDA (dispositifs médicaux approuvés)
- Crowdsourcing des noms de produits
- API de référencement des dispositifs médicaux

### 2. Détection Multi-Sources
- Intégration EudraCT (essais européens)
- WHO ICTRP (registre international)
- Registres nationaux

### 3. Analyse Temporelle
- Évolution des collaborations dans le temps
- Détection de nouvelles collaborations
- Alertes sur nouveaux essais

---

## Maintenance

### Mise à Jour du Mapping

Le mapping `PRODUCT_TO_CORPORATE` doit être régulièrement enrichi :

```python
# Dans src/clinical_trials/client.py
PRODUCT_TO_CORPORATE = {
    "nouveau_produit": "Corporate Name",
    # ...
}
```

### Logs et Debugging

Le module génère des logs détaillés :
- Études analysées
- Raisons de rejet
- Détections réussies

Utilisez `logger.setLevel(logging.DEBUG)` pour un diagnostic approfondi.

---

## Format de Sortie JSON et Intégration Graphe

### Structure JSON

Chaque lien détecté est documenté dans le JSON d'output avec une **catégorie dédiée "clinical_trials"** pour traçabilité complète.

```json
{
  "researcher": {
    "name": "Edgar Duval",
    "scholar_id": "xxxXXXXXXXXJ",
    "h_index": 25
  },
  "corporate_links": [
    {
      "researcher": "Edgar Duval",
      "corporate": "Medtronic",
      "via": "clinical_trials",
      "confidence": 0.95,
      "evidence": {
        "source": "clinicaltrials.gov",
        "link_type": "principal_investigator",
        "detection_method": "intervention_product",
        "nct_id": "NCT02599389",
        "study_title": "Comparison of Angioplasty/Drug Coated Balloon...",
        "study_url": "https://clinicaltrials.gov/study/NCT02599389",
        "role": "Principal Investigator",
        "detection_field": "Intervention",
        "detection_value": "In.Pact Drug-Coated Balloon",
        "product_detected": "In.Pact",
        "corporate_mapping": "In.Pact → Medtronic",
        "sponsor": "University Hospital, Bordeaux",
        "study_phase": "Phase 3",
        "study_status": "Completed"
      }
    }
  ]
}
```

### Champs Clés

| Champ | Description | Exemple |
|-------|-------------|---------|
| `via` | **"clinical_trials"** - Identifie la source de détection | `"clinical_trials"` |
| `link_type` | Type de lien (principal_investigator, co_investigator) | `"principal_investigator"` |
| `detection_method` | Comment le corporate a été détecté | `"intervention_product"` ou `"sponsor_direct"` |
| `product_detected` | Nom du produit identifié (si applicable) | `"In.Pact"` |
| `corporate_mapping` | Mapping produit→corporate appliqué | `"In.Pact → Medtronic"` |

### Catégorisation des Liens

Les liens ClinicalTrials sont distingués des autres sources :

```json
{
  "paths": [
    {
      "source": "patents",
      "researcher": "...",
      "corporate": "..."
    },
    {
      "source": "clinical_trials",  ← Catégorie dédiée
      "researcher": "...",
      "corporate": "...",
      "evidence": { ... }
    },
    {
      "source": "affiliations",
      "researcher": "...",
      "corporate": "..."
    }
  ]
}
```

---

## Visualisation sur le Graphe

### Représentation Graphique

Les liens via ClinicalTrials sont représentés visuellement avec :

**Nœuds:**
- **Chercheur** (scientifique)
- **Corporate** (entreprise)
- **Essai Clinique** (nœud intermédiaire optionnel)

**Arêtes:**
- Type: `CLINICAL_TRIAL_PI` (Principal Investigator)
- Label: Affiche la raison du lien
- Couleur: Spécifique aux liens ClinicalTrials (ex: bleu clair)
- Épaisseur: Proportionnelle au nombre d'essais

### Métadonnées de l'Arête

Chaque arête ClinicalTrials contient :

```python
{
  "type": "CLINICAL_TRIAL_PI",
  "source": "clinical_trials",
  "evidence": [
    {
      "nct_id": "NCT02599389",
      "study_title": "...",
      "detection_method": "intervention_product",
      "product": "In.Pact",
      "role": "Principal Investigator",
      "url": "https://clinicaltrials.gov/study/NCT02599389"
    }
  ],
  "total_studies": 3,  # Nombre d'essais communs
  "confidence": 0.95
}
```

### Exemple de Visualisation

```
[Edgar Duval] ----[CLINICAL_TRIAL_PI]----> [Medtronic]
                          |
                          └─ 3 essais cliniques
                             • NCT02599389 (In.Pact)
                             • NCT01234567 (Resolute)
                             • NCT09876543 (CoreValve)
```

### Tooltip Interactif

Au survol de l'arête, affichage :

```
Lien: Clinical Trials
Type: Principal Investigator
Études: 3

Détails:
• NCT02599389: Utilisation In.Pact (Medtronic)
• NCT01234567: Sponsor Medtronic
• NCT09876543: Utilisation CoreValve (Medtronic)

[Voir sur ClinicalTrials.gov →]
```

### Filtrage par Source

L'utilisateur peut filtrer le graphe pour :
- Afficher uniquement les liens ClinicalTrials
- Exclure les liens ClinicalTrials
- Combiner avec autres sources (brevets, affiliations)

### Légende du Graphe

```
Sources de données:
─────────────────
ClinicalTrials  (Principal Investigator)
Brevets         (Co-inventeur)
Affiliations    (Affiliation institutionnelle)
Publications    (Co-auteur avec affiliation corporate)
```

---

## Exemple Complet d'Output

```json
{
  "researcher": {
    "name": "Edgar Duval",
    "scholar_id": "xxxXXXXXXXXJ",
    "openalex_id": "https://openalex.org/A1234567890",
    "h_index": 25,
    "affiliation": "University Hospital, Bordeaux"
  },
  "summary": {
    "total_corporate_links": 4,
    "sources": {
      "clinical_trials": 2,
      "patents": 1,
      "affiliations": 1
    }
  },
  "corporate_links": [
    {
      "corporate": "Medtronic",
      "via": "clinical_trials",
      "confidence": 0.95,
      "link_count": 2,
      "evidence": [
        {
          "source": "clinicaltrials.gov",
          "link_type": "principal_investigator",
          "detection_method": "intervention_product",
          "nct_id": "NCT02599389",
          "study_title": "Comparison of Angioplasty/Drug Coated Balloon for Femoropopliteal Artery In-stent Restenosis",
          "study_url": "https://clinicaltrials.gov/study/NCT02599389",
          "role": "Principal Investigator",
          "detection_field": "Intervention",
          "detection_value": "In.Pact Admiral Drug-Coated Balloon",
          "product_detected": "In.Pact",
          "corporate_mapping": "In.Pact → Medtronic",
          "sponsor": "University Hospital, Bordeaux",
          "study_phase": "Phase 3",
          "study_status": "Completed",
          "start_date": "2015-01-15",
          "completion_date": "2018-06-30"
        },
        {
          "source": "clinicaltrials.gov",
          "link_type": "principal_investigator",
          "detection_method": "sponsor_direct",
          "nct_id": "NCT01587482",
          "study_title": "PacLitaxel Eluting Balloon Application In Sfa In Stent Restenosis",
          "study_url": "https://clinicaltrials.gov/study/NCT01587482",
          "role": "Principal Investigator",
          "detection_field": "Sponsor",
          "detection_value": "Medtronic",
          "sponsor": "Medtronic",
          "study_phase": "Phase 4",
          "study_status": "Completed"
        }
      ]
    },
    {
      "corporate": "Boston Scientific",
      "via": "patents",
      "confidence": 0.90,
      "evidence": [...]
    }
  ],
  "graph_metadata": {
    "nodes": [
      {
        "id": "edgar_duval",
        "type": "researcher",
        "label": "Edgar Duval",
        "properties": {...}
      },
      {
        "id": "medtronic",
        "type": "corporate",
        "label": "Medtronic",
        "properties": {...}
      }
    ],
    "edges": [
      {
        "source": "edgar_duval",
        "target": "medtronic",
        "type": "CLINICAL_TRIAL_PI",
        "label": "Principal Investigator (2 essais)",
        "properties": {
          "via": "clinical_trials",
          "study_count": 2,
          "nct_ids": ["NCT02599389", "NCT01587482"],
          "detection_methods": ["intervention_product", "sponsor_direct"],
          "confidence": 0.95,
          "color": "#3498db",
          "weight": 2
        }
      }
    ]
  }
}
```

---

## Intégration Pipeline

Le module ClinicalTrials s'intègre dans le pipeline complet :

```python
# Pipeline de détection multi-sources
from src.clinical_trials import search_clinical_trials_corporate
from src.patents import search_patents_corporate
from src.affiliations import search_affiliation_corporate

def find_all_corporate_links(researcher_name):
    """Détecte tous les liens corporate via toutes sources."""

    results = {
        "researcher": researcher_name,
        "corporate_links": []
    }

    # Source 1: Clinical Trials
    ct_results = search_clinical_trials_corporate(researcher_name)
    for link in ct_results.corporate_links:
        results["corporate_links"].append({
            "corporate": link.corporate,
            "via": "clinical_trials",  # ← Catégorie dédiée
            "evidence": link.__dict__
        })

    # Source 2: Brevets
    patent_results = search_patents_corporate(researcher_name)
    # ...

    return results
```

---

## Contact et Contributions

Pour signaler :
- Produits manquants dans le mapping
- Faux positifs
- Améliorations méthodologiques

Créer une issue avec :
- NCT ID de l'étude
- Chercheur concerné
- Corporate attendu vs détecté
- Logs complets

---

**Version:** 1.0
**Dernière mise à jour:** 2026-02-09
**Auteur:** Équipe Scholarmap
