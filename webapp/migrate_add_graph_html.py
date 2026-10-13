#!/usr/bin/env python3
"""
Migration : ajout de la colonne graph_html sur la table scientists.

A exécuter une seule fois sur la DB de production (Clever Cloud PostgreSQL).

Usage:
    python webapp/migrate_add_graph_html.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'webapp'))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / '.env')
except ImportError:
    pass

from src.database.database import engine

with engine.connect() as conn:
    conn.execute(
        __import__('sqlalchemy').text(
            "ALTER TABLE scientists ADD COLUMN IF NOT EXISTS graph_html TEXT;"
        )
    )
    conn.commit()
    print("✓ Colonne graph_html ajoutée (ou déjà présente) sur la table scientists.")
