# 📚 Database Documentation - Scholarmap

**Version:** 1.0
**Date:** 2026-02-03
**Database:** PostgreSQL 16

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Connection](#connection)
3. [Database Schema](#database-schema)
4. [Tables Reference](#tables-reference)
5. [Relationships](#relationships)
6. [Using the Python API](#using-the-python-api)
7. [SQL Query Examples](#sql-query-examples)

---

## 🔍 Overview

The Scholarmap database stores structured scientific data including:
- **Scientists** (researchers with Google Scholar profiles)
- **Publications** (scientific papers with citations)
- **Institutions** (universities, research labs)
- **Patents** (intellectual property)
- **Corporates** (companies)
- **API Calls** (historical cache of API responses)

**Database Stats:**
- 122 Scientists
- 160 Publications
- 15 Institutions
- 87 API Calls (cassettes)

---

## 🔌 Connection

### Connection String
```
postgresql://sci_diligence:sci_diligence_local@localhost:5432/sci_diligence
```

### Connection Details
| Parameter | Value |
|-----------|-------|
| **Host** | localhost |
| **Port** | 5432 |
| **Database** | sci_diligence |
| **Username** | sci_diligence |
| **Password** | sci_diligence_local |

### Connect via psql
```bash
psql -U sci_diligence -d sci_diligence -h localhost -p 5432
```

### Connect via Python
```python
from src.database.api import DatabaseAPI

# Method 1: Using context manager (recommended)
with DatabaseAPI() as api:
    scientists = api.get_all_scientists()

# Method 2: Manual connection
api = DatabaseAPI()
scientists = api.get_all_scientists()
api.close()
```

---

## 📊 Database Schema

### Entity-Relationship Overview

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────┐
│  Scientist  │──────▶│ publications_    │◀──────│ Publication  │
│             │       │     author       │       │              │
│  - id       │       └──────────────────┘       │  - id        │
│  - name     │                                  │  - title     │
│  - scholar  │       ┌──────────────────┐       │  - cited_by  │
│  - affil.   │──────▶│  patents_        │       │  - year      │
└─────────────┘       │   inventor       │       └──────────────┘
       │              └──────────────────┘
       │
       │              ┌──────────────────┐       ┌──────────────┐
       └─────────────▶│  scientist_      │◀──────│ Institution  │
                      │  institution     │       │              │
                      └──────────────────┘       │  - id        │
                                                 │  - name      │
                                                 │  - country   │
                                                 └──────────────┘
```

---

## 📋 Tables Reference

### 1. **scientists**

Stores information about researchers and scientists.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | VARCHAR(255) | Full name of the scientist |
| `scholar_id` | VARCHAR(100) | Google Scholar ID (unique) |
| `affiliation` | TEXT | Current affiliation/institution |
| `created_at` | TIMESTAMP | Record creation timestamp |

**Indexes:**
- Primary key on `id`
- Unique index on `scholar_id`
- Index on `name`

**Example:**
```sql
SELECT * FROM scientists WHERE name = 'Hervé Philippe';
```

---

### 2. **publications**

Stores scientific publications and papers.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `source_id` | VARCHAR(255) | External ID (e.g., Google Scholar citation ID) |
| `title` | TEXT | Publication title |
| `link` | TEXT | URL to the publication |
| `cited_by` | INTEGER | Number of citations |
| `year` | INTEGER | Publication year |
| `created_at` | TIMESTAMP | Record creation timestamp |

**Indexes:**
- Primary key on `id`
- Unique index on `source_id`
- Index on `year`

**Example:**
```sql
SELECT title, year, cited_by
FROM publications
WHERE cited_by > 1000
ORDER BY cited_by DESC;
```

---

### 3. **patents**

Stores patent information.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `patent_id` | VARCHAR(100) | Official patent number (unique) |
| `title` | TEXT | Patent title |
| `link` | TEXT | URL to patent document |
| `claims_excerpt` | TEXT | Excerpt from patent claims |
| `created_at` | TIMESTAMP | Record creation timestamp |

---

### 4. **institution**

Stores universities, research labs, and academic institutions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | VARCHAR(255) | Institution name |
| `normalized_name` | VARCHAR(255) | Normalized name (for deduplication) |
| `country` | VARCHAR(100) | Country |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `notes` | TEXT | Optional notes |

**Indexes:**
- Primary key on `id`
- Index on `normalized_name`

**Example:**
```sql
SELECT name, country FROM institution
WHERE name ILIKE '%university%';
```

---

### 5. **corporates**

Stores companies and corporations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | VARCHAR(255) | Company name |
| `normalized_name` | VARCHAR(255) | Normalized name |
| `country` | VARCHAR(100) | Country |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `notes` | TEXT | Optional notes |

---

### 6. **api_calls**

Historical cache of API responses (cassettes).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `scientist_id` | INTEGER | Foreign key to scientists (nullable) |
| `engine` | VARCHAR(50) | API engine used (e.g., "google") |
| `request_json` | JSON | Request parameters |
| `response_json` | JSON | API response |
| `request_hash` | VARCHAR(64) | SHA256 hash of request (unique) |
| `created_at` | TIMESTAMP | API call timestamp |

**Indexes:**
- Primary key on `id`
- Unique index on `request_hash`
- Index on `scientist_id`
- Index on `engine`
- Index on `created_at`

---

### 7. **publications_author** (Junction Table)

Links publications to their authors (scientists).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `publication_id` | INTEGER | Foreign key to publications |
| `author_id` | INTEGER | Foreign key to scientists |

**Composite Index:** `(publication_id, author_id)`

---

### 8. **patents_inventor** (Junction Table)

Links patents to their inventors (scientists).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `patent_id` | INTEGER | Foreign key to patents |
| `scientist_id` | INTEGER | Foreign key to scientists |

---

### 9. **patents_corporate** (Junction Table)

Links patents to companies (assignee or cited).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `patent_id` | INTEGER | Foreign key to patents |
| `corporate_id` | INTEGER | Foreign key to corporates |
| `role` | VARCHAR(50) | "assignee" or "cited" |

---

### 10. **scientist_institution** (Junction Table)

Links scientists to their affiliated institutions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `scientist_id` | INTEGER | Foreign key to scientists |
| `institution_id` | INTEGER | Foreign key to institution |

---

## 🔗 Relationships

### One-to-Many
- `scientists` → `api_calls` (one scientist, many API calls)

### Many-to-Many
- `scientists` ↔ `publications` (via `publications_author`)
- `scientists` ↔ `patents` (via `patents_inventor`)
- `scientists` ↔ `institution` (via `scientist_institution`)
- `patents` ↔ `corporates` (via `patents_corporate`)

---

## 🐍 Using the Python API

### Quick Start

```python
from src.database.api import DatabaseAPI

# Initialize API
with DatabaseAPI() as api:
    # Get database stats
    stats = api.get_database_stats()
    print(f"Total scientists: {stats['scientists']}")

    # Search for a scientist
    scientists = api.search_scientists("marie")
    for scientist in scientists:
        print(f"{scientist.name} - {scientist.publications_count} publications")

    # Get top publications
    top_pubs = api.get_top_publications(limit=5)
    for pub in top_pubs:
        print(f"{pub.title} ({pub.cited_by} citations)")
```

### Available Methods

#### Scientist Methods
- `get_scientist_by_id(scientist_id)` - Get by ID
- `get_scientist_by_name(name)` - Get by exact name
- `search_scientists(query)` - Search by partial name
- `get_all_scientists(limit=None)` - Get all
- `get_top_scientists_by_citations(limit=10)` - Top by citations

#### Publication Methods
- `get_publication_by_id(publication_id)` - Get by ID
- `get_publications_by_scientist(scientist_id)` - All for scientist
- `search_publications(query)` - Search by title
- `get_top_publications(limit=10)` - Top by citations
- `get_publications_by_year(year)` - Filter by year

#### Institution Methods
- `get_all_institutions()` - Get all
- `get_scientists_by_institution(institution_id)` - Scientists in institution
- `search_institutions(query)` - Search by name

#### Statistics Methods
- `get_database_stats()` - Overall stats
- `get_publication_stats_by_year()` - Yearly publication stats

#### Export Methods
- `export_scientist_to_dict(scientist_id)` - Complete export

---

## 📝 SQL Query Examples

### Find a scientist
```sql
SELECT * FROM scientists
WHERE name ILIKE '%alice%';
```

### Top 10 most cited publications
```sql
SELECT title, year, cited_by
FROM publications
WHERE cited_by IS NOT NULL
ORDER BY cited_by DESC
LIMIT 10;
```

### Publications by scientist
```sql
SELECT p.title, p.year, p.cited_by
FROM publications p
JOIN publications_author pa ON p.id = pa.publication_id
JOIN scientists s ON pa.author_id = s.id
WHERE s.name = 'Hervé Philippe'
ORDER BY p.cited_by DESC NULLS LAST;
```

### Scientists by institution
```sql
SELECT s.name, i.name as institution
FROM scientists s
JOIN scientist_institution si ON s.id = si.scientist_id
JOIN institution i ON si.institution_id = i.id
ORDER BY i.name, s.name;
```

### Institution statistics
```sql
SELECT
    i.name as institution,
    COUNT(DISTINCT si.scientist_id) as scientist_count
FROM institution i
LEFT JOIN scientist_institution si ON i.id = si.institution_id
GROUP BY i.id, i.name
ORDER BY scientist_count DESC;
```

### Publication statistics by year
```sql
SELECT
    year,
    COUNT(*) as publication_count,
    AVG(cited_by) as avg_citations,
    MAX(cited_by) as max_citations
FROM publications
WHERE year IS NOT NULL AND cited_by IS NOT NULL
GROUP BY year
ORDER BY year DESC;
```

### Co-authors of a publication
```sql
SELECT
    p.title,
    STRING_AGG(s.name, ', ') as authors
FROM publications p
JOIN publications_author pa ON p.id = pa.publication_id
JOIN scientists s ON pa.author_id = s.id
GROUP BY p.id, p.title
HAVING COUNT(s.id) > 1
ORDER BY COUNT(s.id) DESC
LIMIT 10;
```

### Scientists with most impact (total citations)
```sql
SELECT
    s.name,
    COUNT(DISTINCT p.id) as publication_count,
    SUM(p.cited_by) as total_citations,
    AVG(p.cited_by) as avg_citations_per_paper
FROM scientists s
JOIN publications_author pa ON s.id = pa.author_id
JOIN publications p ON pa.publication_id = p.id
WHERE p.cited_by IS NOT NULL
GROUP BY s.id, s.name
ORDER BY total_citations DESC
LIMIT 10;
```

---

## 🔧 Maintenance

### Backup Database
```bash
pg_dump -U sci_diligence sci_diligence > backup_$(date +%Y%m%d).sql
```

### Restore Database
```bash
psql -U sci_diligence sci_diligence < backup_20260203.sql
```

### Check Database Size
```sql
SELECT pg_size_pretty(pg_database_size('sci_diligence'));
```

### Vacuum and Analyze
```sql
VACUUM ANALYZE;
```

---

## 📞 Support

For questions or issues:
- Check this documentation first
- Review `useful_queries.sql` for more examples
- Run tests: `pytest tests/test_database_api.py -v`
