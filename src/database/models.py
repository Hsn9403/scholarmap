"""SQLAlchemy models for the Scholarmap database."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Boolean,
    Float,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .database import Base


class Scientist(Base):
    """Scientists/researchers table."""

    __tablename__ = "scientists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)  # For deduplication
    scholar_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    scholar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    h_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affiliation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graph_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # HTML graph stored in DB (persistent, survives container restarts)
    openalex_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # OpenAlex author ID for disambiguation
    specialty_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Comma-separated tags generated from OpenAlex topics via GPT
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    api_calls: Mapped[List["APICall"]] = relationship(
        "APICall", back_populates="scientist"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication",
        secondary="publications_author",
        back_populates="authors",
        overlaps="publication_authors",
    )
    patents: Mapped[List["Patent"]] = relationship(
        "Patent",
        secondary="patents_inventor",
        back_populates="inventors",
        overlaps="patent_inventors",
    )
    institutions: Mapped[List["Institution"]] = relationship(
        "Institution",
        secondary="scientist_institution",
        back_populates="scientists",
        overlaps="scientist_institutions",
    )

    def __repr__(self) -> str:
        return f"<Scientist(id={self.id}, name='{self.name}', scholar_id='{self.scholar_id}')>"


class Publication(Base):
    """Publications (articles, papers) table."""

    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True, index=True)  # For deduplication
    link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Journal/venue info
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Publication abstract
    authors_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Raw authors string from API
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    authors: Mapped[List["Scientist"]] = relationship(
        "Scientist",
        secondary="publications_author",
        back_populates="publications",
        overlaps="publication_authors",
    )

    def __repr__(self) -> str:
        return f"<Publication(id={self.id}, title='{self.title[:50]}...', year={self.year})>"


class Patent(Base):
    """Patents table."""

    __tablename__ = "patents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patent_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True, index=True)  # For deduplication
    link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claims_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publication_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g. "Jun 10, 2022"
    filing_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g. "Oct 15, 2020"
    priority_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g. "Oct 15, 2019"
    assignee: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Current assignee (company/entity holding the patent)
    cited_by_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of patents citing this one
    cited_patents_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Patents cited by this one
    citing_patents_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Patents citing this one
    inventors_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # All inventors (raw list from patent)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    inventors: Mapped[List["Scientist"]] = relationship(
        "Scientist",
        secondary="patents_inventor",
        back_populates="patents",
        overlaps="patent_inventors",
    )
    corporates: Mapped[List["Corporate"]] = relationship(
        "Corporate",
        secondary="patents_corporate",
        back_populates="patents",
        overlaps="patent_corporates",
    )

    def __repr__(self) -> str:
        return f"<Patent(id={self.id}, patent_id='{self.patent_id}', title='{self.title[:50]}...')>"


class Institution(Base):
    """Institutions (universities, research labs) table."""

    __tablename__ = "institution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    scientists: Mapped[List["Scientist"]] = relationship(
        "Scientist",
        secondary="scientist_institution",
        back_populates="institutions",
        overlaps="scientist_institutions",
    )

    def __repr__(self) -> str:
        return f"<Institution(id={self.id}, name='{self.name}', country='{self.country}')>"


class Corporate(Base):
    """Corporates (companies) table."""

    __tablename__ = "corporates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    patents: Mapped[List["Patent"]] = relationship(
        "Patent",
        secondary="patents_corporate",
        back_populates="corporates",
        overlaps="patent_corporates",
    )

    def __repr__(self) -> str:
        return f"<Corporate(id={self.id}, name='{self.name}', country='{self.country}')>"


class APICall(Base):
    """API calls tracking table (stores cassettes)."""

    __tablename__ = "api_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scientist_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=True, index=True
    )
    engine: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # Relationships
    scientist: Mapped[Optional["Scientist"]] = relationship(
        "Scientist", back_populates="api_calls"
    )

    def __repr__(self) -> str:
        return f"<APICall(id={self.id}, engine='{self.engine}', hash='{self.request_hash[:8]}...')>"


# Junction tables (many-to-many relationships)


class PublicationAuthor(Base):
    """Junction table linking publications to authors (scientists)."""

    __tablename__ = "publications_author"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    publication_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publications.id"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_publications_author_pub_auth", "publication_id", "author_id"),
    )

    def __repr__(self) -> str:
        return f"<PublicationAuthor(publication_id={self.publication_id}, author_id={self.author_id})>"


class PatentInventor(Base):
    """Junction table linking patents to inventors (scientists)."""

    __tablename__ = "patents_inventor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patents.id"), nullable=False, index=True
    )
    scientist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_patents_inventor_pat_sci", "patent_id", "scientist_id"),
    )

    def __repr__(self) -> str:
        return f"<PatentInventor(patent_id={self.patent_id}, scientist_id={self.scientist_id})>"


class PatentCorporate(Base):
    """
    Junction table linking patents to corporates.

    Role can be:
    - 'assignee': company owns/assigned the patent
    - 'citing': company cites this patent
    - 'cited': company cited in the patent
    """

    __tablename__ = "patents_corporate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patents.id"), nullable=False, index=True
    )
    corporate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("corporates.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="assignee", index=True
    )
    weight: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # Number of citations/relations
    citation_context: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., 'background', 'claims', etc.

    __table_args__ = (
        Index("ix_patents_corporate_pat_corp", "patent_id", "corporate_id"),
    )

    def __repr__(self) -> str:
        return f"<PatentCorporate(patent_id={self.patent_id}, corporate_id={self.corporate_id}, role='{self.role}', weight={self.weight})>"


class ScientistInstitution(Base):
    """Junction table linking scientists to institutions (affiliations)."""

    __tablename__ = "scientist_institution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scientist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id"), nullable=False, index=True
    )
    institution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("institution.id"), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_scientist_institution_sci_inst", "scientist_id", "institution_id"),
    )

    def __repr__(self) -> str:
        return f"<ScientistInstitution(scientist_id={self.scientist_id}, institution_id={self.institution_id})>"


class PatentCitation(Base):
    """
    Patent citation relationships.

    Tracks which patents cite which other patents.
    Replaces the JSON fields in Patent model for better queryability.
    """

    __tablename__ = "patent_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    citing_patent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cited_patent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    citation_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'forward' or 'backward'
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_patent_citation_pair", "citing_patent_id", "cited_patent_id"),
        Index("ix_patent_citation_cited", "cited_patent_id"),
    )

    def __repr__(self) -> str:
        return f"<PatentCitation(citing={self.citing_patent_id}, cited={self.cited_patent_id}, type='{self.citation_type}')>"


class Collaboration(Base):
    """
    Pre-calculated collaborations between scientists.

    Stores the weight (number of co-authored publications or co-invented patents)
    and temporal information about collaborations.
    """

    __tablename__ = "collaborations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scientist1_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scientist2_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collaboration_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'publication' or 'patent'
    weight: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, index=True
    )  # Number of collaborations
    first_collaboration_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    last_collaboration_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_collaboration_sci1_sci2", "scientist1_id", "scientist2_id"),
        Index("ix_collaboration_type_weight", "collaboration_type", "weight"),
        # Ensure scientist1_id < scientist2_id to avoid duplicates (A-B and B-A)
        # This will be enforced in application logic
    )

    def __repr__(self) -> str:
        return f"<Collaboration(sci1={self.scientist1_id}, sci2={self.scientist2_id}, type='{self.collaboration_type}', weight={self.weight})>"


class TaskStatus(Base):
    """
    Background task status tracking table.

    Replaces the in-memory _task_store dict so that task status
    survives worker restarts and is shared across multiple processes.
    """

    __tablename__ = "task_status"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # processing, completed, error
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<TaskStatus(task_id='{self.task_id}', status='{self.status}', progress={self.progress})>"


class SearchHistory(Base):
    """
    Search history tracking table.

    Records each analysis actually run, so a known researcher can be offered for reuse.
    Unlike the Scientist table which stores all scientists in the database,
    this table only tracks searches that were actually performed.
    """

    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scientist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scientists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    searched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Relationships
    scientist: Mapped["Scientist"] = relationship("Scientist")

    def __repr__(self) -> str:
        return f"<SearchHistory(id={self.id}, scientist_id={self.scientist_id}, searched_at='{self.searched_at}')>"
