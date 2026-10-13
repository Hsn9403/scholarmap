"""Database connection and session management."""

import os
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# Load environment variables from .env file (chemin absolu + override pour garantir le bon .env)
from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent.parent / ".env", override=True)

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sci_diligence:sci_diligence_local@localhost:5432/sci_diligence"
)

# Create SQLAlchemy engine
# QueuePool : connexions réutilisées entre les requêtes.
# pool_size=2 : 2 connexions permanentes (Clever Cloud DEV = 5 max).
# max_overflow=2 : 2 connexions temporaires en pic → 4 max total.
# pool_recycle=3600 : recycle les connexions > 1h pour éviter les timeouts Clever Cloud.
# pool_pre_ping=True : vérifie la connexion avant usage (évite les "connection closed" après idle).
if DATABASE_URL.startswith("sqlite"):
    # Mode local (CLI) : un fichier, partagé entre les threads du pipeline
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for declarative models
Base = declarative_base()


def get_db() -> Generator:
    """
    Dependency function to get database session.

    Yields:
        Database session that will be automatically closed after use.

    Example:
        >>> with get_db() as session:
        ...     scientists = session.query(Scientist).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """
    Create every table the pipeline uses.

    Some tables are declared outside models.py (scientist_corporate, *_enriched),
    so their modules must be imported before create_all or they are silently skipped.
    """
    import src.database.models  # noqa: F401
    import src.database.add_coauthor_industry_connections  # noqa: F401  scientist_corporate
    import src.database.migrate_add_enriched_nodes  # noqa: F401  persons/publications_enriched
    import src.database.migrate_add_patent_enriched  # noqa: F401  patents_enriched

    Base.metadata.create_all(bind=engine)

