"""
Deduplication utilities for database operations.

Provides functions to:
- Normalize text for matching
- Find or create entities without creating duplicates
- Update entities with new data while preserving existing data
"""
from typing import Optional, Type, TypeVar, Dict, Any
from sqlalchemy.orm import Session
from .models import Publication, Scientist, Corporate, Patent

T = TypeVar('T')


def normalize_text(text: str) -> str:
    """
    Normalize text for deduplication.

    Removes extra whitespace, converts to lowercase.

    Args:
        text: Text to normalize

    Returns:
        Normalized text

    Example:
        >>> normalize_text("  HELLO   World  ")
        'hello world'
    """
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


def find_or_create_publication(
    db: Session,
    title: str,
    **kwargs
) -> tuple[Publication, bool]:
    """
    Find existing publication or create new one.

    Uses source_id (if provided) or normalized_title to prevent duplicates.

    Args:
        db: Database session
        title: Publication title
        **kwargs: Additional publication fields (source_id, link, etc.)

    Returns:
        Tuple of (publication, created) where created is True if new

    Example:
        >>> pub, created = find_or_create_publication(
        ...     db,
        ...     title="My Paper",
        ...     source_id="abc123",
        ...     year=2021,
        ...     cited_by=10
        ... )
    """
    normalized_title = normalize_text(title)

    # Check by source_id first if provided
    source_id = kwargs.get('source_id')
    if source_id:
        existing = db.query(Publication).filter(
            Publication.source_id == source_id
        ).first()

        if existing:
            # Update with new data if better
            _update_if_better(existing, kwargs)
            db.flush()
            return existing, False

    # Check by normalized_title
    existing = db.query(Publication).filter(
        Publication.normalized_title == normalized_title
    ).first()

    if existing:
        # Update with new data if better
        _update_if_better(existing, kwargs)
        db.flush()
        return existing, False

    # Create new
    publication = Publication(
        title=title,
        normalized_title=normalized_title,
        **kwargs
    )
    db.add(publication)
    db.flush()
    return publication, True


def find_or_create_scientist(
    db: Session,
    name: str,
    **kwargs
) -> tuple[Scientist, bool]:
    """
    Find existing scientist or create new one.

    Uses normalized_name to prevent duplicates.

    Args:
        db: Database session
        name: Scientist name
        **kwargs: Additional scientist fields

    Returns:
        Tuple of (scientist, created) where created is True if new

    Example:
        >>> scientist, created = find_or_create_scientist(
        ...     db,
        ...     name="John Doe",
        ...     scholar_id="ABC123",
        ...     h_index=10
        ... )
    """
    normalized_name = normalize_text(name)

    # Check if exists by normalized name
    existing = db.query(Scientist).filter(
        Scientist.normalized_name == normalized_name
    ).first()

    if existing:
        # Update with new data if better
        _update_if_better(existing, kwargs)
        db.flush()
        return existing, False

    # Check if exists by scholar_id (if provided)
    scholar_id = kwargs.get('scholar_id')
    if scholar_id:
        existing = db.query(Scientist).filter(
            Scientist.scholar_id == scholar_id
        ).first()

        if existing:
            # Update name if this one is better (longer = more complete)
            if len(name) > len(existing.name or ""):
                existing.name = name
                existing.normalized_name = normalized_name
            _update_if_better(existing, kwargs)
            db.flush()
            return existing, False

    # Create new
    scientist = Scientist(
        name=name,
        normalized_name=normalized_name,
        **kwargs
    )
    db.add(scientist)
    db.flush()
    return scientist, True


def find_or_create_corporate(
    db: Session,
    name: str,
    **kwargs
) -> tuple[Corporate, bool]:
    """
    Find existing corporate or create new one.

    Uses normalized_name to prevent duplicates.

    Args:
        db: Database session
        name: Corporate name
        **kwargs: Additional corporate fields

    Returns:
        Tuple of (corporate, created) where created is True if new
    """
    normalized_name = normalize_text(name)

    # Check if exists
    existing = db.query(Corporate).filter(
        Corporate.normalized_name == normalized_name
    ).first()

    if existing:
        _update_if_better(existing, kwargs)
        db.flush()
        return existing, False

    # Create new
    corporate = Corporate(
        name=name,
        normalized_name=normalized_name,
        **kwargs
    )
    db.add(corporate)
    db.flush()
    return corporate, True


def find_or_create_patent(
    db: Session,
    title: str,
    **kwargs
) -> tuple[Patent, bool]:
    """
    Find existing patent or create new one.

    Uses both patent_id (if provided) and normalized_title to prevent duplicates.

    Args:
        db: Database session
        title: Patent title
        **kwargs: Additional patent fields (patent_id, link, etc.)

    Returns:
        Tuple of (patent, created) where created is True if new

    Example:
        >>> patent, created = find_or_create_patent(
        ...     db,
        ...     title="Method for microfluidic control",
        ...     patent_id="US1234567",
        ...     link="https://..."
        ... )
    """
    normalized_title = normalize_text(title)

    # Check by patent_id first if provided
    patent_id = kwargs.get('patent_id')
    if patent_id:
        existing = db.query(Patent).filter(
            Patent.patent_id == patent_id
        ).first()

        if existing:
            # Update with new data if better
            _update_if_better(existing, kwargs)
            db.flush()
            return existing, False

    # Check by normalized_title
    existing = db.query(Patent).filter(
        Patent.normalized_title == normalized_title
    ).first()

    if existing:
        # Update with new data if better
        _update_if_better(existing, kwargs)
        db.flush()
        return existing, False

    # Create new
    patent = Patent(
        title=title,
        normalized_title=normalized_title,
        **kwargs
    )
    db.add(patent)
    db.flush()
    return patent, True


def _update_if_better(entity: Any, new_data: Dict[str, Any]) -> bool:
    """
    Update entity with new data only if the new data is better.

    "Better" means:
    - Non-null vs null
    - Higher number (for citations, h-index)
    - Longer string (for names)

    Args:
        entity: Database entity to update
        new_data: Dictionary of new values

    Returns:
        True if entity was updated
    """
    updated = False

    for key, new_value in new_data.items():
        # Skip normalized fields (set automatically)
        if key.startswith('normalized_'):
            continue

        # Get current value
        current_value = getattr(entity, key, None)

        # Update if new value is better
        if _is_better(new_value, current_value):
            setattr(entity, key, new_value)
            updated = True

    return updated


def _is_better(new_value: Any, current_value: Any) -> bool:
    """
    Determine if new value is better than current value.

    Args:
        new_value: New value to compare
        current_value: Current value

    Returns:
        True if new value is better
    """
    # New value exists, current doesn't
    if new_value is not None and current_value is None:
        return True

    # Current value exists, new doesn't
    if new_value is None:
        return False

    # Both exist - compare based on type
    if isinstance(new_value, (int, float)):
        # For numbers, higher is better
        return new_value > current_value

    if isinstance(new_value, str):
        # For strings, longer is usually better (more complete)
        # But only if both are non-empty
        if current_value and new_value:
            return len(new_value) > len(current_value)
        return bool(new_value) and not bool(current_value)

    # For other types, keep current value
    return False
