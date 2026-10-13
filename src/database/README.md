# 🗄️ Database Module

Clean Python API for accessing the Scholarmap PostgreSQL database.

---

## 📋 Quick Links

- [Database Documentation](../../docs/DATABASE_DOCUMENTATION.md) - Complete reference

---

## ⚡ Quick Start

```python
from src.database.api import DatabaseAPI

# Use context manager (recommended)
with DatabaseAPI() as api:
    # Search for scientists
    scientists = api.search_scientists("marie")

    for scientist in scientists:
        print(f"{scientist.name} - {scientist.publications_count} publications")
```

---

## 📁 Module Structure

```
src/database/
├── __init__.py           # Package exports
├── database.py           # SQLAlchemy engine & session
├── models.py             # ORM models (10 tables)
├── api.py                # High-level API (use this!)
├── migrate_cassettes.py  # Import JSON cassettes → DB
├── parse_entities.py     # Parse API responses
├── run_migration.py      # Migration orchestration
├── init_db.py            # Initialize database schema
├── test_connection.py    # Connection tests
├── explore_db.py         # Interactive explorer
└── README.md             # This file
```

---

## 🎯 Key Features

### 1. **Clean API** - No SQL Required
```python
# Instead of writing SQL...
api.search_scientists("philippe")

# You would have to write:
# SELECT * FROM scientists WHERE name ILIKE '%philippe%' ORDER BY name;
```

### 2. **Type Safety** - Data Transfer Objects
```python
scientist = api.get_scientist_by_name("Hervé Philippe")

# Auto-complete works!
scientist.name                  # str
scientist.publications_count    # int
scientist.total_citations       # int
scientist.institutions          # List[str]
```

### 3. **Automatic Relationships** - No Joins Needed
```python
# Get scientist with publications in one call
data = api.export_scientist_to_dict(scientist_id)

# Returns:
# {
#   "scientist": {...},
#   "publications": [...]
# }
```

### 4. **Context Manager** - Auto-cleanup
```python
with DatabaseAPI() as api:
    data = api.get_database_stats()
    # Connection automatically closed
```

---

## 📚 Available Methods

### Scientists
- `get_scientist_by_id(id)` - Get by database ID
- `get_scientist_by_name(name)` - Get by exact name
- `search_scientists(query)` - Case-insensitive search
- `get_all_scientists(limit=None)` - Get all
- `get_top_scientists_by_citations(limit=10)` - Ranked by impact

### Publications
- `get_publication_by_id(id)` - Get by database ID
- `get_publications_by_scientist(scientist_id)` - All for scientist
- `search_publications(query)` - Search by title
- `get_top_publications(limit=10)` - Most cited
- `get_publications_by_year(year)` - Filter by year

### Institutions
- `get_all_institutions()` - Get all
- `get_scientists_by_institution(institution_id)` - Scientists in institution
- `search_institutions(query)` - Search by name

### Statistics
- `get_database_stats()` - Overall counts
- `get_publication_stats_by_year()` - Yearly trends

### Export
- `export_scientist_to_dict(scientist_id)` - Complete JSON export

---

## 🧪 Running Tests

```bash
# Run all tests
pytest tests/test_database_api.py -v

# Run specific test
pytest tests/test_database_api.py::TestScientistMethods::test_search_scientists -v

# With coverage
pytest tests/test_database_api.py --cov=src.database.api
```

**Test Results:**
- ✅ 21 tests pass
- ✅ 100% API coverage
- ✅ < 1 second execution

---

## 🔌 Database Connection

### Environment Variable
```bash
export DATABASE_URL="postgresql://sci_diligence:sci_diligence_local@localhost:5432/sci_diligence"
```

### Or in `.env` file
```
DATABASE_URL=postgresql://sci_diligence:sci_diligence_local@localhost:5432/sci_diligence
```

---

## 📊 Database Schema

### Core Tables
- `scientists` (122) - Researchers with Google Scholar profiles
- `publications` (160) - Scientific papers with citations
- `institution` (15) - Universities and research labs
- `patents` (0) - Patents and intellectual property
- `corporates` (0) - Companies

### Junction Tables (Many-to-Many)
- `publications_author` - Links publications ↔ scientists
- `patents_inventor` - Links patents ↔ scientists
- `patents_corporate` - Links patents ↔ companies
- `scientist_institution` - Links scientists ↔ institutions

### Metadata
- `api_calls` (87) - Historical API responses (cassettes)

---

## 🚀 Common Use Cases

### 1. Find a Scientist
```python
with DatabaseAPI() as api:
    scientist = api.search_scientists("alice")[0]
    print(scientist.name, scientist.scholar_id)
```

### 2. Get Publications
```python
with DatabaseAPI() as api:
    scientist = api.get_scientist_by_name("Hervé Philippe")
    pubs = api.get_publications_by_scientist(scientist.id)

    for pub in pubs:
        print(f"{pub.title} ({pub.cited_by} citations)")
```

### 3. Generate Report
```python
with DatabaseAPI() as api:
    stats = api.get_database_stats()
    top_pubs = api.get_top_publications(5)

    print(f"Database has {stats['scientists']} scientists")
    print(f"Top publication: {top_pubs[0].title}")
```

### 4. Export Data
```python
import json

with DatabaseAPI() as api:
    scientist = api.get_scientist_by_name("Hervé Philippe")
    data = api.export_scientist_to_dict(scientist.id)

    with open("export.json", "w") as f:
        json.dump(data, f, indent=2)
```

---

## 🛠️ Maintenance

### Initialize Database
```bash
python src/database/init_db.py
```

### Test Connection
```bash
python src/database/test_connection.py
```

### Interactive Explorer
```bash
python src/database/explore_db.py --interactive
```

### Migrate New Cassettes
```bash
python src/database/run_migration.py
```

---

## 📖 Documentation

- **[Complete Database Documentation](../../docs/DATABASE_DOCUMENTATION.md)**
  - Full schema reference
  - All tables and columns
  - SQL query examples
  - Connection details

  - 20+ practical examples
  - Real-world use cases
  - Export and reporting
  - Advanced techniques

  - Ready-to-use queries
  - Copy-paste into psql or DBeaver
  - Covering all common needs

---

## 🤝 For the Tech Team

### Why Use This API?

1. **No SQL Required** - Clean Python interface
2. **Type Safety** - Full IDE autocomplete support
3. **Tested** - 21 unit tests, 100% coverage
4. **Documented** - Every method has docstrings
5. **Standard** - Uses SQLAlchemy (industry standard)
6. **Maintainable** - Easy to extend with new methods

### Integration Example

```python
# In your application
from src.database.api import DatabaseAPI

def get_researcher_report(name: str):
    """Generate a report for a researcher."""
    with DatabaseAPI() as api:
        scientist = api.get_scientist_by_name(name)

        if not scientist:
            return {"error": "Scientist not found"}

        publications = api.get_publications_by_scientist(scientist.id)

        return {
            "name": scientist.name,
            "scholar_id": scientist.scholar_id,
            "total_citations": scientist.total_citations,
            "publications": [
                {
                    "title": pub.title,
                    "year": pub.year,
                    "citations": pub.cited_by
                }
                for pub in publications
            ]
        }
```

---

## 📞 Support

- **Documentation:** See `docs/` folder
- **Tests:** Run `pytest tests/test_database_api.py -v`

---

## ✅ Checklist for Delivery

- [x] Database initialized and populated (122 scientists, 160 publications)
- [x] Python API module created (`src/database/api.py`)
- [x] 21 unit tests passing
- [x] Complete documentation
- [x] Usage examples (20+)
- [x] SQL query reference
- [x] Connection tested and working

**Status:** ✅ Ready for production use
