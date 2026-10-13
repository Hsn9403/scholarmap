#!/usr/bin/env python3
"""
Classification patterns for distinguishing INS (institutions) from COR (corporates).

This file contains the heuristic rules used to classify ORG entities.
Patterns are organized by category and can be easily extended.

Usage:
    Modify INS_PATTERNS or COR_PATTERNS to improve classification accuracy.
    Each pattern is a lowercase string that will be matched against entity text.

Note:
    - Patterns are matched case-insensitively
    - More specific patterns should be added as edge cases are discovered
    - When unsure about a classification, add it to AMBIGUOUS_ENTITIES for review
"""

# Institution patterns - academic, research, government entities
INS_PATTERNS = [
    # Academic
    "university",
    "université",
    "universite",  # without accent
    "universität",
    "universidad",
    "college",
    "student",  # PhD student, student at...
    "school of",
    "faculty of",
    "department of",
    "academy",
    "académie",
    "polytechnic",
    "polytechnique",

    # Research
    "institute",
    "institut",
    "laboratory",
    "laboratoire",
    "research center",
    "research centre",
    "centre de recherche",
    "cnrs",
    "inserm",
    "inria",
    "inrae",
    "cea",
    "nih",
    "nasa",
    "max planck",
    "fraunhofer",

    # Healthcare/Medical
    "hospital",
    "hôpital",
    "clinic",
    "clinique",
    "medical center",
    "centre hospitalier",
    "chu",

    # Government
    "ministry",
    "ministère",
    "agency",
    "agence",
    "national",
    "federal",
    "government",
    "gouvernement",

    # Non-profit/Foundation
    "foundation",
    "fondation",
    "association",
    "organization",
    "organisation",
    "society",
    "société savante",
]

# Corporate patterns - commercial, for-profit entities
COR_PATTERNS = [
    # Legal suffixes - English
    "inc.",
    "inc",
    "incorporated",
    "corp.",
    "corp",
    "corporation",
    "ltd.",
    "ltd",
    "limited",
    "llc",
    "l.l.c.",
    "llp",
    "plc",
    "co.",

    # Legal suffixes - French
    "sa",
    "s.a.",
    "sas",
    "s.a.s.",
    "sarl",
    "s.a.r.l.",
    "eurl",
    "sasu",

    # Legal suffixes - German
    "gmbh",
    "g.m.b.h.",
    "ag",
    "a.g.",
    "kg",
    "ohg",

    # Legal suffixes - Other
    "bv",
    "nv",
    "pty",
    "pvt",
    "pte",

    # Industry keywords
    "technologies",
    "technology",
    "tech",
    "software",
    "systems",
    "solutions",
    "services",
    "consulting",
    "partners",
    "group",
    "holdings",
    "ventures",
    "capital",
    "investments",

    # Pharma/Biotech (commercial)
    "pharma",
    "pharmaceutical",
    "pharmaceuticals",
    "therapeutics",
    "biosciences",
    "biotechnology",
    "biotech",
    "labs",  # commercial labs (not "laboratory")
    "diagnostics",

    # Other commercial
    "company",
    "enterprises",
    "industries",
    "international",
    "worldwide",
    "global",
]

# Known ambiguous entities - require explicit classification
# Format: {"entity_name": "INS" or "COR"}
# Add entities here when classification is uncertain
KNOWN_ENTITIES = {
    # Universities with non-obvious names
    "mit": "INS",
    "caltech": "INS",
    "eth zurich": "INS",
    "epfl": "INS",
    "eth": "INS",
    "stanford": "INS",
    "harvard": "INS",
    "oxford": "INS",
    "cambridge": "INS",
    "berkeley": "INS",
    "yale": "INS",
    "princeton": "INS",
    "columbia": "INS",

    # Research institutions
    "cern": "INS",
    "who": "INS",
    "unesco": "INS",

    # Add more as discovered...
}

# Known corporates without obvious legal suffixes
KNOWN_CORPORATES = {
    "apple": "COR",
    "google": "COR",
    "microsoft": "COR",
    "amazon": "COR",
    "meta": "COR",
    "nvidia": "COR",
    "intel": "COR",
    "ibm": "COR",
    "oracle": "COR",
    "samsung": "COR",
    "sony": "COR",
    "nokia": "COR",
    "huawei": "COR",
    "qualcomm": "COR",
    "broadcom": "COR",
}

# Merge into KNOWN_ENTITIES
KNOWN_ENTITIES.update(KNOWN_CORPORATES)

# Entities that couldn't be classified - for review
# This list is populated during runtime and can be exported for manual review
AMBIGUOUS_ENTITIES: list[str] = []
