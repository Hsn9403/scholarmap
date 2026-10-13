#!/usr/bin/env python3
"""
Organization classifier for distinguishing INS (institutions) from COR (corporates).

This module provides the logic to classify ORG entities detected by NER
into more specific categories: INS (institutions) or COR (corporates).

The classification uses a priority-based approach:
1. Check KNOWN_ENTITIES for exact matches
2. Check INS_PATTERNS first (academic signals like "student", "university")
3. Check COR_PATTERNS (legal suffixes)
4. Default to ORG (unknown) and flag for review
"""
from typing import Literal, Optional, List, Any
import threading

from .patterns import (
    INS_PATTERNS,
    COR_PATTERNS,
    KNOWN_ENTITIES,
    AMBIGUOUS_ENTITIES,
)


EntityType = Literal["INS", "COR", "ORG"]


class NERManager:
    """
    Thread-safe singleton manager for NER pipeline and ambiguous entities tracking.

    This class ensures that:
    - Only one NER pipeline instance is created (lazy-loaded)
    - Ambiguous entities tracking is thread-safe
    - Resources are properly managed for web app usage
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._ner_pipeline = None
        self._ambiguous_entities: List[str] = []
        self._ambiguous_lock = threading.Lock()
        self._initialized = True

    def get_pipeline(self) -> Any:
        """Get or create the HuggingFace NER pipeline (thread-safe)."""
        if self._ner_pipeline is None:
            with self._lock:
                if self._ner_pipeline is None:
                    from transformers import pipeline
                    self._ner_pipeline = pipeline(
                        "ner",
                        model="Davlan/xlm-roberta-base-ner-hrl",
                        aggregation_strategy="simple",
                    )
        return self._ner_pipeline

    def add_ambiguous_entity(self, entity: str) -> None:
        """Add an entity to the ambiguous list (thread-safe)."""
        with self._ambiguous_lock:
            if entity not in self._ambiguous_entities:
                self._ambiguous_entities.append(entity)

    def get_ambiguous_entities(self) -> List[str]:
        """Get a copy of ambiguous entities list (thread-safe)."""
        with self._ambiguous_lock:
            return self._ambiguous_entities.copy()

    def clear_ambiguous_entities(self) -> None:
        """Clear the ambiguous entities list (thread-safe)."""
        with self._ambiguous_lock:
            self._ambiguous_entities.clear()


# Global singleton instance
_ner_manager = NERManager()


def classify_organization(entity: str) -> tuple[EntityType, float]:
    """
    Classify an organization entity as INS, COR, or ORG (unknown).

    Args:
        entity: The organization name to classify.

    Returns:
        Tuple of (classification, confidence):
        - classification: "INS", "COR", or "ORG" (unknown)
        - confidence: 0.0 to 1.0, where 1.0 = certain (known entity)

    Example:
        >>> classify_organization("MIT")
        ('INS', 1.0)
        >>> classify_organization("Google Inc.")
        ('COR', 0.9)
        >>> classify_organization("Some Random Org")
        ('ORG', 0.0)
    """
    entity_lower = entity.lower().strip()

    # 1. Check known entities (highest confidence)
    if entity_lower in KNOWN_ENTITIES:
        return KNOWN_ENTITIES[entity_lower], 1.0

    # 2. Check INS patterns first (academic signals are strong)
    for pattern in INS_PATTERNS:
        if _pattern_matches(entity_lower, pattern):
            return "INS", 0.9

    # 3. Check COR patterns
    for pattern in COR_PATTERNS:
        if _pattern_matches(entity_lower, pattern):
            return "COR", 0.85

    # 4. Unknown - flag for review
    _ner_manager.add_ambiguous_entity(entity)

    return "ORG", 0.0


def _pattern_matches(entity: str, pattern: str) -> bool:
    """
    Check if a pattern matches an entity.

    Handles both:
    - Word boundary matches (e.g., "university" in "MIT University")
    - Suffix matches (e.g., "inc." at end of "Google Inc.")
    """
    # For short patterns like "sa", "ag", etc., require word boundary or end
    if len(pattern) <= 3:
        words = entity.split()
        return pattern in words or entity.endswith(pattern)

    # For longer patterns, simple containment is fine
    return pattern in entity


def get_ambiguous_entities() -> list[str]:
    """
    Get list of entities that couldn't be classified.

    Use this to review and add to KNOWN_ENTITIES in patterns.py.

    Returns:
        List of entity names that were classified as ORG (unknown).
    """
    return _ner_manager.get_ambiguous_entities()


def clear_ambiguous_entities() -> None:
    """Clear the list of ambiguous entities."""
    _ner_manager.clear_ambiguous_entities()


def add_known_entity(entity: str, classification: EntityType) -> None:
    """
    Add a new known entity classification.

    This updates KNOWN_ENTITIES at runtime. For persistent changes,
    also update patterns.py manually.

    Args:
        entity: The entity name (will be lowercased).
        classification: "INS" or "COR".
    """
    if classification not in ("INS", "COR"):
        raise ValueError(f"Classification must be 'INS' or 'COR', got '{classification}'")

    KNOWN_ENTITIES[entity.lower().strip()] = classification

    # Note: Ambiguous entities are managed by NERManager now
    # No need to manually remove from ambiguous list


def classify_entity(text: str) -> tuple[str, float]:
    """
    Classify an entity as PER, INS, COR, or ORG using HuggingFace NER.

    This function first uses the NER model to detect if the text is a person.
    If not a person, it falls back to classify_organization for INS/COR.

    Args:
        text: The entity text to classify.

    Returns:
        Tuple of (classification, confidence):
        - classification: "PER", "INS", "COR", or "ORG"
        - confidence: 0.0 to 1.0

    Example:
        >>> classify_entity("Nicolas Paul")
        ('PER', 0.95)
        >>> classify_entity("Harvard University")
        ('INS', 0.85)
    """
    if not text or not text.strip():
        return "ORG", 0.0

    text = text.strip()

    # Use HuggingFace NER to detect persons
    try:
        pipe = _ner_manager.get_pipeline()
        entities = pipe(text)

        # Check if the dominant entity is a person
        for ent in entities:
            if ent["entity_group"] == "PER" and ent["score"] > 0.7:
                # Check if the PER entity covers most of the text
                coverage = (ent["end"] - ent["start"]) / len(text)
                if coverage > 0.5:
                    return "PER", ent["score"]

    except Exception:
        # If HuggingFace fails, fall back to pattern-based classification
        pass

    # Not a person - use pattern-based classification for ORG
    return classify_organization(text)
