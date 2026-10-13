# Guide de Déduplication

## Contraintes UNIQUE ajoutées

Les contraintes suivantes ont été ajoutées pour **empêcher les duplicates**:

- `publications.normalized_title` → UNIQUE
- `scientists.normalized_name` → UNIQUE
- `corporates.normalized_name` → UNIQUE

## Comment utiliser

### **AVANT** (créait des duplicates)

```python
# MAUVAIS - Ne vérifie que source_id, pas le titre
existing = db.query(Publication).filter_by(source_id=citation_id).first()

if not existing:
    publication = Publication(
        title=title,
        year=year,
        cited_by=cited_by
    )
    db.add(publication)
```

**Problème:** Si `source_id` est None ou différent, créait un duplicate même si le titre est identique.

### **APRÈS** (évite les duplicates)

```python
from src.database.deduplication import find_or_create_publication

# BIEN - Utilise normalized_title pour déduplication
publication, created = find_or_create_publication(
    db,
    title=title,
    source_id=citation_id,
    year=year,
    cited_by=cited_by,
    source=source,
    link=link
)

if created:
    logger.info(f" Created publication: {title[:50]}...")
else:
    logger.debug(f"→ Updated existing publication: {title[:50]}...")
```

**Avantages:**
- Pas de duplicates (contrainte UNIQUE sur normalized_title)
- Met à jour automatiquement avec de meilleures données
- Plus simple et lisible

## Exemples pour chaque type d'entité

### Publications

```python
from src.database.deduplication import find_or_create_publication

pub, created = find_or_create_publication(
    db,
    title="Microfluidics for microswimmers",
    year=2021,
    cited_by=59,
    source="Small 17 (26), 2007403, 2021",
    link="https://...",
    abstract="...",
    authors_raw="P Sharan, A Nedelec, J Simmchen"
)
```

### Scientists

```python
from src.database.deduplication import find_or_create_scientist

scientist, created = find_or_create_scientist(
    db,
    name="Alice Nedelec",
    scholar_id="iQOY4mUAAAAJ",
    scholar_url="https://scholar.google.com/citations?user=iQOY4mUAAAAJ",
    h_index=6,
    affiliation="Elvesys"
)
```

**Note:** Vérifie à la fois `normalized_name` ET `scholar_id` pour éviter les duplicates.

### Corporates

```python
from src.database.deduplication import find_or_create_corporate

corporate, created = find_or_create_corporate(
    db,
    name="Inside Therapeutics",
    country="France"
)
```

## Mise à jour automatique

Les fonctions `find_or_create_*` **mettent à jour automatiquement** avec de meilleures données:

```python
# Première insertion
scientist, created = find_or_create_scientist(
    db,
    name="A Nedelec",
    h_index=5
)
# created = True, scientist.h_index = 5

# Deuxième insertion (même scientifique, données meilleures)
scientist, created = find_or_create_scientist(
    db,
    name="Alice Nedelec",  # Nom plus complet
    h_index=6,  # H-index plus élevé
    scholar_id="iQOY4mUAAAAJ"  # Nouvelle donnée
)
# created = False (même scientist retourné)
# scientist.name = "Alice Nedelec" (plus long)
# scientist.h_index = 6 (plus élevé)
# scientist.scholar_id = "iQOY4mUAAAAJ" (ajouté)
```

## Règles de "meilleure donnée"

La fonction `_update_if_better()` utilise ces règles:

1. **Non-null > null**
   ```python
   current: None → new: "value"  UPDATE
   current: "value" → new: None  SKIP
   ```

2. **Pour les nombres: plus élevé > plus bas**
   ```python
   h_index: 5 → 6  UPDATE
   h_index: 6 → 5  SKIP
   cited_by: 50 → 59  UPDATE
   ```

3. **Pour les strings: plus long > plus court**
   ```python
   name: "A Nedelec" → "Alice Nedelec"  UPDATE
   name: "Alice Nedelec" → "A Nedelec"  SKIP
   ```

## Migration du code existant

### 1. Identifier les endroits à risque

Cherchez dans le code:
```bash
grep -r "Publication(" src/database/parse_entities.py
grep -r "Scientist(" src/database/parse_entities.py
grep -r "Corporate(" src/database/parse_entities.py
```

### 2. Remplacer par find_or_create_*

**Avant:**
```python
existing = db.query(Publication).filter_by(title=title).first()
if not existing:
    pub = Publication(title=title, year=year)
    db.add(pub)
```

**Après:**
```python
from src.database.deduplication import find_or_create_publication

pub, created = find_or_create_publication(db, title=title, year=year)
```

### 3. Tester

```bash
# Tester avec un chercheur déjà dans la DB
python src/script.py "Alice Nedelec" --use-database

# Vérifier qu'il n'y a pas de nouveaux duplicates
python -c "
from src.database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Check duplicates
result = db.execute(text('''
    SELECT normalized_title, COUNT(*) as count
    FROM publications
    GROUP BY normalized_title
    HAVING COUNT(*) > 1
''')).fetchall()

print(f'Duplicate publications: {len(result)}')
assert len(result) == 0, 'Found duplicates!'
print(' No duplicates!')
"
```

## Important

1. **Toujours utiliser `find_or_create_*`** au lieu de créer directement des entités
2. **Toujours appeler `db.flush()`** après `find_or_create_*` pour obtenir l'ID
3. **Ne jamais modifier `normalized_*`** manuellement - c'est automatique
4. **Les contraintes UNIQUE vont lever une erreur** si vous essayez de créer un duplicate manuellement

## Tests

Pour vérifier que la déduplication fonctionne:

```python
from src.database.deduplication import find_or_create_scientist
from src.database.database import SessionLocal

db = SessionLocal()

# Insertion 1
s1, created1 = find_or_create_scientist(db, name="ALICE NEDELEC", h_index=5)
assert created1 == True

# Insertion 2 (même nom, casse différente)
s2, created2 = find_or_create_scientist(db, name="alice nedelec", h_index=6)
assert created2 == False  # Pas créé
assert s1.id == s2.id  # Même scientifique
assert s2.h_index == 6  # Mis à jour

db.rollback()  # Rollback du test
```

## TODO

Fichiers à migrer vers `find_or_create_*`:

- [ ] `src/database/parse_entities.py` (parse_scholar_author_results)
- [ ] `src/database/parse_entities.py` (parse_google_patents_results)
- [ ] Tous les scripts d'extraction one-off

Une fois migré, vous pourrez faire de nouvelles requêtes API sans créer de duplicates! 
