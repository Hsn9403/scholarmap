#!/usr/bin/env python3
"""
Named Entity Recognition module for Scholarmap.

This module provides entity extraction with automatic classification:
- PER: Persons
- INS: Institutions (universities, research centers, government agencies)
- COR: Corporates (companies, commercial entities)

The module uses Davlan/xlm-roberta-base-ner-hrl as the base NER model,
with additional heuristics to subdivide ORG into INS/COR.

Basic usage:
    >>> from src.ner import extract_entities
    >>> result = extract_entities("John Smith works at MIT and Google Inc.")
    >>> result.persons[0].text
    'John Smith'
    >>> result.institutions[0].text
    'MIT'
    >>> result.corporates[0].text
    'Google Inc.'

Simple dict output:
    >>> from src.ner import extract_entities_simple
    >>> extract_entities_simple("John Smith works at MIT")
    {'PER': ['John Smith'], 'INS': ['MIT'], 'COR': [], 'ORG': []}

Managing classifications:
    >>> from src.ner import get_ambiguous_entities, add_known_entity
    >>> # After extraction, check what couldn't be classified
    >>> ambiguous = get_ambiguous_entities()
    >>> # Add a classification for future use
    >>> add_known_entity("EPFL", "INS")
"""
from .extractor import (
    Entity,
    ExtractionResult,
    extract_entities,
    extract_entities_simple,
)
from .classifier import (
    classify_organization,
    classify_entity,
    get_ambiguous_entities,
    clear_ambiguous_entities,
    add_known_entity,
)
from .patterns import (
    INS_PATTERNS,
    COR_PATTERNS,
    KNOWN_ENTITIES,
)

__all__ = [
    # Main functions
    "extract_entities",
    "extract_entities_simple",
    # Data classes
    "Entity",
    "ExtractionResult",
    # Classification utilities
    "classify_organization",
    "classify_entity",  # Uses HuggingFace for PER detection
    "get_ambiguous_entities",
    "clear_ambiguous_entities",
    "add_known_entity",
    # Patterns (for inspection/modification)
    "INS_PATTERNS",
    "COR_PATTERNS",
    "KNOWN_ENTITIES",
]
