"""
Database API - Clean interface for accessing scientific diligence data.

This module provides a high-level API for the tech team to access data
from the PostgreSQL database without worrying about SQL details.

Example:
    >>> from src.database.api import DatabaseAPI
    >>> api = DatabaseAPI()
    >>> scientist = api.get_scientist_by_name("Hervé Philippe")
    >>> print(scientist.name, scientist.publications_count)
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import (
    Scientist,
    Publication,
    Patent,
    Institution,
    Corporate,
    APICall,
    PublicationAuthor,
    PatentInventor,
    ScientistInstitution,
)


class ScientistData:
    """Data Transfer Object for Scientist information."""

    def __init__(self, scientist: Scientist, db: Session):
        self.id = scientist.id
        self.name = scientist.name
        self.scholar_id = scientist.scholar_id
        self.scholar_url = scientist.scholar_url
        self.h_index = scientist.h_index
        self.affiliation = scientist.affiliation
        self.created_at = scientist.created_at

        # Compute statistics
        self.publications_count = (
            db.query(PublicationAuthor)
            .filter_by(author_id=scientist.id)
            .count()
        )

        self.total_citations = (
            db.query(func.sum(Publication.cited_by))
            .join(PublicationAuthor)
            .filter(PublicationAuthor.author_id == scientist.id)
            .scalar()
            or 0
        )

        self.institutions = [
            inst.name
            for inst in db.query(Institution)
            .join(ScientistInstitution)
            .filter(ScientistInstitution.scientist_id == scientist.id)
            .all()
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "scholar_id": self.scholar_id,
            "scholar_url": self.scholar_url,
            "h_index": self.h_index,
            "affiliation": self.affiliation,
            "publications_count": self.publications_count,
            "total_citations": self.total_citations,
            "institutions": self.institutions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PublicationData:
    """Data Transfer Object for Publication information."""

    def __init__(self, publication: Publication, db: Session):
        self.id = publication.id
        self.source_id = publication.source_id
        self.title = publication.title
        self.link = publication.link
        self.cited_by = publication.cited_by
        self.year = publication.year
        self.source = publication.source
        self.abstract = publication.abstract
        self.authors_raw = publication.authors_raw
        self.created_at = publication.created_at

        # Get authors
        self.authors = [
            sci.name
            for sci in db.query(Scientist)
            .join(PublicationAuthor)
            .filter(PublicationAuthor.publication_id == publication.id)
            .all()
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "title": self.title,
            "link": self.link,
            "cited_by": self.cited_by,
            "year": self.year,
            "source": self.source,
            "abstract": self.abstract,
            "authors": self.authors,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatabaseAPI:
    """
    High-level API for accessing scientific diligence data.

    This class provides clean methods for the tech team to query
    the database without writing SQL.

    Example:
        >>> api = DatabaseAPI()
        >>> scientists = api.search_scientists("philippe")
        >>> for scientist in scientists:
        ...     print(scientist.name, scientist.publications_count)
    """

    def __init__(self):
        """Initialize the API with a database session."""
        self.db = SessionLocal()

    def close(self):
        """Close the database session."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # =========================================================================
    # SCIENTIST METHODS
    # =========================================================================

    def get_scientist_by_id(self, scientist_id: int) -> Optional[ScientistData]:
        """
        Get a scientist by their ID.

        Args:
            scientist_id: The scientist's database ID

        Returns:
            ScientistData object or None if not found

        Example:
            >>> api = DatabaseAPI()
            >>> scientist = api.get_scientist_by_id(1)
            >>> print(scientist.name)
        """
        scientist = self.db.query(Scientist).filter_by(id=scientist_id).first()
        return ScientistData(scientist, self.db) if scientist else None

    def get_scientist_by_name(self, name: str) -> Optional[ScientistData]:
        """
        Get a scientist by exact name.

        Args:
            name: The scientist's full name

        Returns:
            ScientistData object or None if not found

        Example:
            >>> api = DatabaseAPI()
            >>> scientist = api.get_scientist_by_name("Hervé Philippe")
        """
        scientist = self.db.query(Scientist).filter_by(name=name).first()
        return ScientistData(scientist, self.db) if scientist else None

    def search_scientists(
        self,
        query: str = None,
        scholar_id: str = None
    ) -> List[ScientistData]:
        """
        Search for scientists by name or scholar_id.

        Args:
            query: Search string (will match anywhere in the name)
            scholar_id: Google Scholar ID for exact match (more precise)

        Returns:
            List of ScientistData objects

        Example:
            >>> api = DatabaseAPI()
            >>> # Search by name
            >>> scientists = api.search_scientists(query="marie")
            >>> # Search by scholar_id (precise)
            >>> scientists = api.search_scientists(scholar_id="xJaxiEEAAAAJ")
        """
        # Search by scholar_id (most precise)
        if scholar_id:
            scientists = (
                self.db.query(Scientist)
                .filter(Scientist.scholar_id == scholar_id)
                .all()
            )
        # Search by name
        elif query:
            scientists = (
                self.db.query(Scientist)
                .filter(Scientist.name.ilike(f"%{query}%"))
                .order_by(Scientist.name)
                .all()
            )
        else:
            # No search criteria provided
            return []
        return [ScientistData(s, self.db) for s in scientists]

    def get_all_scientists(self, limit: Optional[int] = None) -> List[ScientistData]:
        """
        Get all scientists.

        Args:
            limit: Optional maximum number of results

        Returns:
            List of ScientistData objects

        Example:
            >>> api = DatabaseAPI()
            >>> scientists = api.get_all_scientists(limit=10)
        """
        query = self.db.query(Scientist).order_by(Scientist.name)
        if limit:
            query = query.limit(limit)
        scientists = query.all()
        return [ScientistData(s, self.db) for s in scientists]

    def get_top_scientists_by_citations(
        self, limit: int = 10
    ) -> List[ScientistData]:
        """
        Get top scientists ranked by total citations.

        Args:
            limit: Maximum number of results (default: 10)

        Returns:
            List of ScientistData objects ordered by citations

        Example:
            >>> api = DatabaseAPI()
            >>> top = api.get_top_scientists_by_citations(5)
            >>> for scientist in top:
            ...     print(f"{scientist.name}: {scientist.total_citations} citations")
        """
        scientists = (
            self.db.query(Scientist)
            .join(PublicationAuthor)
            .join(Publication)
            .filter(Publication.cited_by.isnot(None))
            .group_by(Scientist.id)
            .order_by(desc(func.sum(Publication.cited_by)))
            .limit(limit)
            .all()
        )
        return [ScientistData(s, self.db) for s in scientists]

    # =========================================================================
    # PUBLICATION METHODS
    # =========================================================================

    def get_publication_by_id(self, publication_id: int) -> Optional[PublicationData]:
        """
        Get a publication by its ID.

        Args:
            publication_id: The publication's database ID

        Returns:
            PublicationData object or None if not found
        """
        publication = (
            self.db.query(Publication).filter_by(id=publication_id).first()
        )
        return PublicationData(publication, self.db) if publication else None

    def get_publications_by_scientist(
        self, scientist_id: int, order_by_citations: bool = True
    ) -> List[PublicationData]:
        """
        Get all publications for a scientist.

        Args:
            scientist_id: The scientist's database ID
            order_by_citations: Sort by citations descending (default: True)

        Returns:
            List of PublicationData objects

        Example:
            >>> api = DatabaseAPI()
            >>> scientist = api.get_scientist_by_name("Hervé Philippe")
            >>> pubs = api.get_publications_by_scientist(scientist.id)
            >>> for pub in pubs:
            ...     print(f"{pub.title} ({pub.cited_by} citations)")
        """
        query = (
            self.db.query(Publication)
            .join(PublicationAuthor)
            .filter(PublicationAuthor.author_id == scientist_id)
        )

        if order_by_citations:
            query = query.order_by(desc(Publication.cited_by).nullslast())

        publications = query.all()
        return [PublicationData(p, self.db) for p in publications]

    def search_publications(self, query: str) -> List[PublicationData]:
        """
        Search for publications by title (case-insensitive, partial match).

        Args:
            query: Search string

        Returns:
            List of PublicationData objects

        Example:
            >>> api = DatabaseAPI()
            >>> pubs = api.search_publications("muscle")
        """
        publications = (
            self.db.query(Publication)
            .filter(Publication.title.ilike(f"%{query}%"))
            .order_by(desc(Publication.cited_by).nullslast())
            .all()
        )
        return [PublicationData(p, self.db) for p in publications]

    def get_top_publications(self, limit: int = 10) -> List[PublicationData]:
        """
        Get top publications by citations.

        Args:
            limit: Maximum number of results (default: 10)

        Returns:
            List of PublicationData objects ordered by citations

        Example:
            >>> api = DatabaseAPI()
            >>> top_pubs = api.get_top_publications(5)
        """
        publications = (
            self.db.query(Publication)
            .filter(Publication.cited_by.isnot(None))
            .order_by(desc(Publication.cited_by))
            .limit(limit)
            .all()
        )
        return [PublicationData(p, self.db) for p in publications]

    def get_publications_by_year(
        self, year: int, order_by_citations: bool = True
    ) -> List[PublicationData]:
        """
        Get all publications for a specific year.

        Args:
            year: Publication year
            order_by_citations: Sort by citations descending (default: True)

        Returns:
            List of PublicationData objects
        """
        query = self.db.query(Publication).filter(Publication.year == year)

        if order_by_citations:
            query = query.order_by(desc(Publication.cited_by).nullslast())

        publications = query.all()
        return [PublicationData(p, self.db) for p in publications]

    # =========================================================================
    # INSTITUTION METHODS
    # =========================================================================

    def get_all_institutions(self) -> List[Institution]:
        """
        Get all institutions.

        Returns:
            List of Institution objects

        Example:
            >>> api = DatabaseAPI()
            >>> institutions = api.get_all_institutions()
            >>> for inst in institutions:
            ...     print(inst.name)
        """
        return self.db.query(Institution).order_by(Institution.name).all()

    def get_scientists_by_institution(
        self, institution_id: int
    ) -> List[ScientistData]:
        """
        Get all scientists affiliated with an institution.

        Args:
            institution_id: The institution's database ID

        Returns:
            List of ScientistData objects
        """
        scientists = (
            self.db.query(Scientist)
            .join(ScientistInstitution)
            .filter(ScientistInstitution.institution_id == institution_id)
            .order_by(Scientist.name)
            .all()
        )
        return [ScientistData(s, self.db) for s in scientists]

    def search_institutions(self, query: str) -> List[Institution]:
        """
        Search for institutions by name.

        Args:
            query: Search string

        Returns:
            List of Institution objects
        """
        return (
            self.db.query(Institution)
            .filter(Institution.name.ilike(f"%{query}%"))
            .order_by(Institution.name)
            .all()
        )

    # =========================================================================
    # STATISTICS METHODS
    # =========================================================================

    def get_database_stats(self) -> Dict[str, int]:
        """
        Get overall database statistics.

        Returns:
            Dictionary with counts for each entity type

        Example:
            >>> api = DatabaseAPI()
            >>> stats = api.get_database_stats()
            >>> print(f"Total scientists: {stats['scientists']}")
        """
        return {
            "scientists": self.db.query(Scientist).count(),
            "publications": self.db.query(Publication).count(),
            "institutions": self.db.query(Institution).count(),
            "patents": self.db.query(Patent).count(),
            "api_calls": self.db.query(APICall).count(),
        }

    def get_publication_stats_by_year(self) -> List[Dict[str, Any]]:
        """
        Get publication statistics grouped by year.

        Returns:
            List of dictionaries with year, count, and average citations

        Example:
            >>> api = DatabaseAPI()
            >>> stats = api.get_publication_stats_by_year()
            >>> for stat in stats:
            ...     print(f"{stat['year']}: {stat['count']} publications")
        """
        results = (
            self.db.query(
                Publication.year,
                func.count(Publication.id).label("count"),
                func.avg(Publication.cited_by).label("avg_citations"),
            )
            .filter(Publication.year.isnot(None))
            .group_by(Publication.year)
            .order_by(desc(Publication.year))
            .all()
        )

        return [
            {
                "year": year,
                "count": count,
                "avg_citations": float(avg_citations) if avg_citations else 0,
            }
            for year, count, avg_citations in results
        ]

    # =========================================================================
    # PATENT METHODS
    # =========================================================================

    def get_all_patents(self, limit: Optional[int] = None) -> List[Patent]:
        """
        Get all patents.

        Args:
            limit: Optional maximum number of results

        Returns:
            List of Patent objects

        Example:
            >>> api = DatabaseAPI()
            >>> patents = api.get_all_patents(limit=10)
        """
        query = self.db.query(Patent).order_by(Patent.created_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_patent_by_id(self, patent_id: int) -> Optional[Patent]:
        """
        Get a patent by its database ID.

        Args:
            patent_id: The patent's database ID

        Returns:
            Patent object or None if not found
        """
        return self.db.query(Patent).filter_by(id=patent_id).first()

    def get_patents_by_scientist(self, scientist_id: int) -> List[Patent]:
        """
        Get all patents for a scientist (as inventor).

        Args:
            scientist_id: The scientist's database ID

        Returns:
            List of Patent objects

        Example:
            >>> api = DatabaseAPI()
            >>> scientist = api.get_scientist_by_name("Alice Nedelec")
            >>> patents = api.get_patents_by_scientist(scientist.id)
            >>> for patent in patents:
            ...     print(f"{patent.patent_id}: {patent.title}")
        """
        patents = (
            self.db.query(Patent)
            .join(PatentInventor)
            .filter(PatentInventor.scientist_id == scientist_id)
            .order_by(Patent.created_at.desc())
            .all()
        )
        return patents

    def search_patents(self, query: str) -> List[Patent]:
        """
        Search for patents by title (case-insensitive, partial match).

        Args:
            query: Search string

        Returns:
            List of Patent objects

        Example:
            >>> api = DatabaseAPI()
            >>> patents = api.search_patents("microfluidic")
        """
        patents = (
            self.db.query(Patent)
            .filter(Patent.title.ilike(f"%{query}%"))
            .order_by(Patent.created_at.desc())
            .all()
        )
        return patents

    def get_patent_inventors(self, patent_id: int) -> List[ScientistData]:
        """
        Get all inventors for a patent.

        Args:
            patent_id: The patent's database ID

        Returns:
            List of ScientistData objects
        """
        scientists = (
            self.db.query(Scientist)
            .join(PatentInventor)
            .filter(PatentInventor.patent_id == patent_id)
            .all()
        )
        return [ScientistData(s, self.db) for s in scientists]

    # =========================================================================
    # EXPORT METHODS
    # =========================================================================

    def export_scientist_to_dict(self, scientist_id: int) -> Dict[str, Any]:
        """
        Export complete scientist data including publications.

        Args:
            scientist_id: The scientist's database ID

        Returns:
            Complete dictionary with all scientist data

        Example:
            >>> api = DatabaseAPI()
            >>> data = api.export_scientist_to_dict(1)
            >>> import json
            >>> print(json.dumps(data, indent=2))
        """
        scientist_data = self.get_scientist_by_id(scientist_id)
        if not scientist_data:
            return {}

        publications = self.get_publications_by_scientist(scientist_id)

        return {
            "scientist": scientist_data.to_dict(),
            "publications": [p.to_dict() for p in publications],
        }
