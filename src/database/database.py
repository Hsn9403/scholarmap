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
