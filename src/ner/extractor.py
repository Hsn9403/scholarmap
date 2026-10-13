#!/usr/bin/env python3
"""
Named Entity Recognition extractor using HuggingFace transformers.

This module wraps the Davlan/xlm-roberta-base-ner-hrl model to extract
named entities and classify them into PER, INS, and COR categories.

The model natively supports: LOC, PER, ORG
We transform this to: PER, INS, COR (ignoring LOC)
"""
from dataclasses import dataclass
from typing import Optional

from .classifier import classify_organization, EntityType


# Lazy loading to avoid import overhead when not needed
_pipeline = None
_model_name = "Davlan/xlm-roberta-base-ner-hrl"


@dataclass
class Entity:
    """
    A named entity extracted from text.

    Attributes:
        text: The entity text as found in the source.
        label: Entity type: "PER", "INS", "COR", or "ORG" (unclassified).
        confidence: Model confidence (0.0 to 1.0).
        start: Start character position in source text.
        end: End character position in source text.
    """
    text: str
    label: str
    confidence: float
    start: int
    end: int


@dataclass
class ExtractionResult:
    """
    Result of entity extraction from text.

    Attributes:
        persons: List of PER entities.
        institutions: List of INS entities.
        corporates: List of COR entities.
        unclassified: List of ORG entities that couldn't be classified.
        all_entities: All entities in order of appearance.
    """
    persons: list[Entity]
    institutions: list[Entity]
    corporates: list[Entity]
    unclassified: list[Entity]
    all_entities: list[Entity]


def _get_pipeline():
    """Lazy-load the NER pipeline."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline
        _pipeline = pipeline(
            "ner",
            model=_model_name,
            aggregation_strategy="simple",  # Merge B-/I- tags
        )
    return _pipeline


def extract_entities(
    text: str,
    include_locations: bool = False,
    min_confidence: float = 0.5,
) -> ExtractionResult:
    """
    Extract named entities from text.

    Args:
        text: Input text to analyze.
        include_locations: If True, include LOC entities in unclassified.
                          Default False (locations are ignored).
        min_confidence: Minimum confidence threshold (0.0-1.0).
                       Entities below this threshold are ignored.

    Returns:
        ExtractionResult with categorized entities.

    Example:
        >>> result = extract_entities("John Smith works at MIT and Google Inc.")
        >>> print([e.text for e in result.persons])
        ['John Smith']
        >>> print([e.text for e in result.institutions])
        ['MIT']
        >>> print([e.text for e in result.corporates])
        ['Google Inc.']
    """
    pipe = _get_pipeline()
    raw_entities = pipe(text)

    persons = []
    institutions = []
    corporates = []
    unclassified = []
    all_entities = []

    for ent in raw_entities:
        # Skip low confidence
        if ent["score"] < min_confidence:
            continue

        entity_group = ent["entity_group"]
        entity_text = ent["word"].strip()

        # Skip locations unless explicitly requested
        if entity_group == "LOC":
            if not include_locations:
                continue
            entity = Entity(
                text=entity_text,
                label="LOC",
                confidence=ent["score"],
                start=ent["start"],
                end=ent["end"],
            )
            unclassified.append(entity)
            all_entities.append(entity)
            continue

        # Handle PER entities
        if entity_group == "PER":
            entity = Entity(
                text=entity_text,
                label="PER",
                confidence=ent["score"],
                start=ent["start"],
                end=ent["end"],
            )
            persons.append(entity)
            all_entities.append(entity)
            continue

        # Handle ORG entities - classify as INS or COR
        if entity_group == "ORG":
            org_type, type_confidence = classify_organization(entity_text)

            # Combine NER confidence with classification confidence
            combined_confidence = ent["score"] * type_confidence if type_confidence > 0 else ent["score"]

            entity = Entity(
                text=entity_text,
                label=org_type,
                confidence=combined_confidence,
                start=ent["start"],
                end=ent["end"],
            )

            if org_type == "INS":
                institutions.append(entity)
            elif org_type == "COR":
                corporates.append(entity)
            else:
                unclassified.append(entity)

            all_entities.append(entity)

    return ExtractionResult(
        persons=persons,
        institutions=institutions,
        corporates=corporates,
        unclassified=unclassified,
        all_entities=all_entities,
    )


def extract_entities_simple(text: str) -> dict[str, list[str]]:
    """
    Simplified entity extraction returning just entity texts.

    Args:
        text: Input text to analyze.

    Returns:
        Dict with keys "PER", "INS", "COR", "ORG" containing lists of entity texts.

    Example:
        >>> extract_entities_simple("John Smith works at MIT")
        {'PER': ['John Smith'], 'INS': ['MIT'], 'COR': [], 'ORG': []}
    """
    result = extract_entities(text)
    return {
        "PER": [e.text for e in result.persons],
        "INS": [e.text for e in result.institutions],
        "COR": [e.text for e in result.corporates],
        "ORG": [e.text for e in result.unclassified],
    }
