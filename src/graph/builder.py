#!/usr/bin/env python3
"""
Network graph builder for KOL (Key Opinion Leader) networks.

This module builds a graph data structure from Scholar and Patent data,
representing relationships between researchers, patents, and organizations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from src.models import ScholarData, PatentsData
from src.helpers import (
    strip_accents_basic,
    slug,
    dedup_preserve_order,
    parse_yyyy_mm_dd,
)
from src.ner import classify_organization, classify_entity


def _node_id(node_type: str, label: str) -> str:
    """Generate unique node ID."""
    return f"{node_type}:{slug(label)}"


# Legal form suffixes to strip when normalizing corporate names.
# Ordered longest-first so e.g. "SARL" matches before "SA".
_CORP_SUFFIX_RE = re.compile(
    r'[\s,]+'
    r'(?:S\.?A\.?S\.?U?\.?|S\.?A\.?R\.?L?\.?|S\.?N\.?C\.?|S\.?C\.?I\.?|E\.?U\.?R\.?L\.?'
    r'|Incorporated|Corporation|Limited|Holdings|Company|Group'
    r'|Inc\.?|Corp\.?|Ltd\.?|L\.?L\.?C\.?|L\.?L\.?P\.?|P\.?L\.?C\.?|L\.?P\.?'
    r'|G\.?m\.?b\.?H\.?|S\.?p\.?A\.?|S\.?r\.?l\.?'
    r'|B\.?V\.?|N\.?V\.?|A\.?G\.?|A\.?B\.?|O\.?y\.?'
    r'|S\.?A\.?'
    r'|Co\.?)'
    r'\.?\s*$',
    re.IGNORECASE,
)


def _normalize_corp_name(name: str) -> str:
    """Strip trailing legal form suffixes for canonical corporate name.

    'Cherry Biotech SAS' → 'Cherry Biotech'
    'Cherry Biotech S.A.S.' → 'Cherry Biotech'
    'Acme, Inc.' → 'Acme'
    'Some GmbH' → 'Some'
    Returns the original name unchanged if nothing was stripped.
    """
    if not name:
        return name
    cleaned = _CORP_SUFFIX_RE.sub('', name.strip()).strip(' ,')
    return cleaned if cleaned else name


def _patent_node_id(publication_or_pid: str) -> str:
    """Generate unique patent node ID."""
    x = (publication_or_pid or "").strip()
    x = x.replace("patent/", "").replace("/en", "")
    return f"patent:{x}" if x else "patent:unknown"


def _publication_node_id(title: str) -> str:
    """Generate unique publication node ID."""
    return f"publication:{slug(title)}"


def _normalize_patent_id(patent_id: str) -> str:
    """Normalize patent ID to document number."""
    if not patent_id:
        return patent_id
    m = re.search(r"patent/([^/]+)/", patent_id)
    return m.group(1) if m else patent_id


def _normalize_person_name(name: str) -> str:
    """
    Normalize a person name for comparison.

    Converts to lowercase, removes accents, and keeps only alphanumeric + spaces.
    """
    import unicodedata
    # NFD decomposition + remove combining characters (accents)
    normalized = unicodedata.normalize("NFD", name.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    # Replace hyphens and dashes with spaces BEFORE removing non-alphanumeric
    # This handles "Garcia‐Zintzun" → "Garcia Zintzun" (not "GarciaZintzun")
    normalized = re.sub(r"[-‐–—]", " ", normalized)
    # Keep only alphanumeric and spaces
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_same_person(name1: str, name2: str) -> bool:
    """
    Check if two names likely refer to the same person.

    Handles:
    - Abbreviated first names: "A Nedelec" matches "Alice Nedelec"
    - Partial surnames: "A Nedelec Mercier" matches "Alice Nedelec"

    Args:
        name1: First name (can be abbreviated).
        name2: Second name (can be abbreviated).

    Returns:
        True if names likely match, False otherwise.

    Example:
        >>> _is_same_person("A Nedelec", "Alice Nedelec")
        True
        >>> _is_same_person("A Nedelec Mercier", "Alice Nedelec")
        True
        >>> _is_same_person("John Smith", "Jane Smith")
        False
    """
    norm1 = _normalize_person_name(name1)
    norm2 = _normalize_person_name(name2)

    if norm1 == norm2:
        return True

    parts1 = norm1.split()
    parts2 = norm2.split()

    if not parts1 or not parts2:
        return False

    # Check first name/initial (must match)
    first1 = parts1[0]
    first2 = parts2[0]

    first_name_matches = False
    if len(first1) == 1 and first2.startswith(first1):
        first_name_matches = True
    elif len(first2) == 1 and first1.startswith(first2):
        first_name_matches = True
    elif first1 == first2:
        first_name_matches = True

    if not first_name_matches:
        return False

    # Check if surnames overlap (handles partial surnames)
    # e.g., "nedelec mercier" and "nedelec" share "nedelec"
    surnames1 = set(parts1[1:])  # All parts after first name
    surnames2 = set(parts2[1:])

    # If there's any overlap in surnames, consider it a match
    if surnames1 & surnames2:  # Set intersection
        return True

    return False


def _is_placeholder(x: str) -> bool:
    """Check if company name is a placeholder."""
    return (x or "").strip().lower() == "no corporate has cited this patent"


def _classify_entity_type(name: str) -> str:
    """
    Classify an entity name as 'person', 'institution', or 'corporate' using NER.

    Uses HuggingFace model to detect persons, then falls back to patterns.

    Returns:
        'person' for PER, 'institution' for INS, 'corporate' for COR/ORG.
    """
    entity_type, confidence = classify_entity(name)
    if entity_type == "PER":
        return "person"
    if entity_type == "INS":
        return "institution"
    # COR or unknown ORG -> corporate (default)
    return "corporate"


def _classify_org_type(name: str) -> str:
    """
    Classify an organization name as 'institution' or 'corporate' using patterns only.

    This is the fast version without HuggingFace (for affiliations).

    Returns:
        'institution' for INS, 'corporate' for COR, 'corporate' for unknown ORG.
    """
    org_type, confidence = classify_organization(name)
    if org_type == "INS":
        return "institution"
    # COR or unknown ORG -> corporate (default)
    return "corporate"


def _same_org(a: str, b: str) -> bool:
    """Check if two org names are the same (fuzzy)."""
    def norm_org(s):
        s = strip_accents_basic((s or "").lower())
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(
            r"\b(inc|corp|corporation|ltd|limited|llc|gmbh|sas|sarl|sa|spa|ag|bv|nv|oy|ab|co|company|group|holdings)\b",
            " ", s
        )
        return re.sub(r"\s+", " ", s).strip()

    aa, bb = norm_org(a), norm_org(b)
    if not aa or not bb:
        return False
    return aa == bb or aa in bb or bb in aa


def _validate_scholar_match(searched_name: str, found_name: str) -> bool:
    """
    Validate that a Scholar profile candidate matches the searched name.

    Uses strict criteria to avoid false positives:
    - Last name must match exactly (normalized)
    - First name/initial must match (if present in both)

    Args:
        searched_name: Original name being searched (e.g., "R Ollivier")
        found_name: Name from Scholar candidate (e.g., "Ryan U Olivares")

    Returns:
        True if names match, False otherwise.

    Examples:
        >>> _validate_scholar_match("R Ollivier", "Remy Ollivier")
        True  # Same last name, R matches Remy
        >>> _validate_scholar_match("R Ollivier", "Ryan U Olivares")
        False  # Different last name (Ollivier vs Olivares)
        >>> _validate_scholar_match("J Simmchen", "Juliane Simmchen")
        True  # Same last name, J matches Juliane
    """
    # Normalize both names
    searched_normalized = _normalize_person_name(searched_name)
    found_normalized = _normalize_person_name(found_name)

    searched_parts = searched_normalized.split()
    found_parts = found_normalized.split()

    if not searched_parts or not found_parts:
        return False

    # Check last name (must match exactly)
    searched_last = searched_parts[-1]
    found_last = found_parts[-1]

    if searched_last != found_last:
        return False

    # Check first name/initial
    if len(searched_parts) > 1 and len(found_parts) > 1:
        searched_first = searched_parts[0]
        found_first = found_parts[0]

        # If searched is an initial, check if it matches the found first name
        if len(searched_first) == 1:
            if not found_first.startswith(searched_first):
                return False
        # If found is an initial, check if it matches the searched first name
        elif len(found_first) == 1:
            if not searched_first.startswith(found_first):
                return False
        # Both are full names, must match exactly
        else:
            if searched_first != found_first:
                return False

    return True


def _resolve_coauthor_name_via_publications(
    abbreviated_name: str,
    example_titles: list,
    top_publications: list,
) -> Optional[str]:
    """
    Resolve a Scholar co-author abbreviated name to a full name.

    Scholar's co-author list often has abbreviated names (e.g., "L Wang").
    The example_titles field lists publications where this co-author appears.
    By checking the actual author lists of those publications we can find
    the full name (e.g., "Lu Wang") with high confidence — without extra API calls.

    Args:
        abbreviated_name: Abbreviated co-author name (e.g., "L Wang").
        example_titles: Publication titles where Scholar confirms this co-author.
        top_publications: Main researcher's publications (with full author lists).

    Returns:
        Full resolved name if unambiguous, None otherwise.
    """
    if not example_titles or not top_publications:
        return None

    # Only resolve abbreviated names (single-letter first name)
    parts = abbreviated_name.strip().split()
    if len(parts) < 2:
        return None
    first = parts[0].replace(".", "").strip()
    if len(first) > 1:
        return None  # Already a full name

    # Build normalized title → publication lookup
    pub_lookup = {}
    for pub in top_publications:
        if pub.title:
            pub_lookup[_normalize_person_name(pub.title)] = pub

    # Collect full-name candidates across all example_title publications
    candidates: set = set()
    for title in example_titles:
        pub = pub_lookup.get(_normalize_person_name(title))
        if not pub:
            continue
        for author in (pub.authors or []):
            author = author.strip()
            if not author or author == abbreviated_name:
                continue
            if _is_same_person(author, abbreviated_name):
                a_parts = author.strip().split()
                if len(a_parts) >= 2:
                    a_first = a_parts[0].replace(".", "").strip()
                    if len(a_first) > 1:  # Must be a full first name, not another initial
                        candidates.add(author)

    if len(candidates) == 1:
        return next(iter(candidates))
    # Multiple distinct full names → ambiguous, keep abbreviated
    return None


def _enrich_person_with_scholar(
    person_name: str,
    scholar_client: Optional[Any]
) -> Dict[str, Any]:
    """
    Enrich a person node with Scholar profile data.

    Uses strict matching to avoid false positives. If no good match is found,
    returns empty result rather than risking incorrect attribution.

    Args:
        person_name: Name of the person to enrich.
        scholar_client: ScholarClient instance.

    Returns:
        Dict with keys: h_index, scholar_profile_url.
    """
    result = {"h_index": None, "scholar_profile_url": None}

    if not scholar_client:
        return result

    try:
        # Find Scholar profile candidates
        candidates = scholar_client.find_candidates(person_name, num=5)

        if not candidates:
            return result

        # Find the first candidate that matches our strict criteria
        matched_candidate = None
        for candidate in candidates:
            # Get the candidate's name from the title
            # Title format is usually "Name - Google Scholar"
            candidate_title = candidate.title or ""
            candidate_name = candidate_title.replace(" - Google Scholar", "").strip()

            if not candidate_name:
                continue

            # Validate the match
            if _validate_scholar_match(person_name, candidate_name):
                matched_candidate = candidate
                break

        if not matched_candidate:
            from src.logger import logger
            logger.debug(
                f"No strict match found for '{person_name}' "
                f"(found {len(candidates)} candidates but none matched)"
            )
            return result

        # Fetch author data to get H-index
        author_id = matched_candidate.author_id
        author_data = scholar_client.fetch_author_data(author_id, num_articles=1)

        result["h_index"] = author_data.h_index
        result["scholar_profile_url"] = (
            f"https://scholar.google.com/citations?user={author_id}"
            if author_id else None
        )

        from src.logger import logger
        logger.debug(
            f"Matched '{person_name}' to '{author_data.name}' "
            f"(H-index: {author_data.h_index})"
        )

    except Exception as e:
        # Silently fail if Scholar profile not found
        from src.logger import logger
        logger.debug(f"Could not enrich Scholar profile for '{person_name}': {e}")

    return result


@dataclass
class GraphBuilder:
    """
    Helper class to build graph nodes and edges.

    Attributes:
        nodes: Dict mapping node ID to node data.
        edges: Dict mapping edge key to edge data.
    """
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_node(self, node: Dict[str, Any]) -> None:
        """Add a node to the graph."""
        self.nodes[node["id"]] = node

    def add_edge(self, key: str, edge: Dict[str, Any]) -> None:
        """Add or increment an edge."""
        if key not in self.edges:
            edge = dict(edge)
            edge["id"] = key
            edge.setdefault("weight", 1)
            self.edges[key] = edge
        else:
            self.edges[key]["weight"] = self.edges[key].get("weight", 1) + edge.get("weight", 1)
            if edge.get("evidence"):
                self.edges[key].setdefault("evidence", []).extend(edge["evidence"][:1])


def _is_likely_same_person_for_merge(name1: str, name2: str) -> bool:
    """
    Check if two names likely refer to the same person (for merging purposes).

    More permissive than _is_same_person to handle complex initials cases.

    Rules:
    - Same last name (exact match, normalized)
    - At least one first initial matches OR one has full first name

    Args:
        name1: First name.
        name2: Second name.

    Returns:
        True if names likely match for merging.

    Examples:
        >>> _is_likely_same_person_for_merge("J Simmchen", "LPJ Simmchen")
        True  # Same last name, J is in LPJ
        >>> _is_likely_same_person_for_merge("GV Carpentier", "Gaspard Velve Carpentier")
        True  # Same last name, G matches Gaspard
    """
    norm1 = _normalize_person_name(name1)
    norm2 = _normalize_person_name(name2)

    parts1 = norm1.split()
    parts2 = norm2.split()

    if not parts1 or not parts2:
        return False

    # Check last name (must match exactly)
    if parts1[-1] != parts2[-1]:
        return False

    # Extract all initials and full names
    def extract_initials_and_names(parts):
        """Extract all initials from parts (including multi-letter initials like lpj)."""
        initials = set()
        full_names = set()

        for part in parts:
            if len(part) == 1:
                # Single initial
                initials.add(part)
            elif len(part) <= 4:
                # Short part: could be initials sequence ("lpj", "gv") OR a short name ("lu", "li")
                # Heuristic: no vowels → initials sequence (explode); has vowels → short name
                has_vowel = any(c in 'aeiouy' for c in part)
                if has_vowel:
                    # Short name like "Lu", "Li", "Ana", "Jean" — treat as a full name
                    full_names.add(part)
                    initials.add(part[0])
                else:
                    # Initials sequence like "LPJ", "GV" — explode each letter
                    for letter in part:
                        initials.add(letter)
            else:
                # Full name (5+ letters)
                full_names.add(part)
                initials.add(part[0])  # Also add first letter as initial

        return initials, full_names

    initials1, full_names1 = extract_initials_and_names(parts1[:-1])
    initials2, full_names2 = extract_initials_and_names(parts2[:-1])

    # Check if there's any overlap in initials or full names
    if initials1 & initials2:  # At least one initial in common
        # Extra guard: if BOTH sides have full name representations, require
        # them to be compatible (one starts with the other).
        # This prevents merging distinct names like "Linlin Wang" + "Lu Wang"
        # that share only the first letter but are clearly different people.
        if full_names1 and full_names2:
            for fn1 in full_names1:
                for fn2 in full_names2:
                    if fn1.startswith(fn2) or fn2.startswith(fn1):
                        return True
            return False  # Both have full names but none are prefixes of each other
        return True

    if full_names1 & full_names2:  # At least one full name in common
        return True

    return False


def _merge_duplicate_persons(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge duplicate person nodes in the graph.

    Identifies persons with the same name (using _is_same_person logic),
    then merges them into a single node, keeping the best version.

    Priority for keeping a node:
    1. Has Scholar profile (h_index not None)
    2. More collaborations with seed
    3. Full name (not just initials)

    Args:
        graph: Graph dict with keys: meta, nodes, edges.

    Returns:
        Graph dict with merged person nodes.
    """
    from src.logger import logger

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Get all persons (except seed)
    seed_id = graph["meta"]["seed_person_id"]
    persons = [n for n in nodes if n["type"] == "person" and n["id"] != seed_id]

    # Group duplicates using _is_same_person
    # Build clusters of persons that are the same
    clusters = []
    processed = set()

    for i, person1 in enumerate(persons):
        if person1["id"] in processed:
            continue

        cluster = [person1]
        processed.add(person1["id"])

        # Find all other persons that match
        for person2 in persons[i + 1:]:
            if person2["id"] in processed:
                continue

            if _is_likely_same_person_for_merge(person1["label"], person2["label"]):
                cluster.append(person2)
                processed.add(person2["id"])

        clusters.append(cluster)

    # Merge duplicates in each cluster
    merged_nodes = [n for n in nodes if n["type"] != "person" or n["id"] == seed_id]
    merged_count = 0
    node_id_mapping = {}  # old_id -> new_id

    def score_node(node):
        """
        Score a node to determine which to keep.

        Higher score = better node (more complete information).
        Always keep the node with the most information.
        """
        score = 0

        # Priority 1: Has Scholar ID (most important - unique identifier)
        if node["attributes"].get("scholar_id"):
            score += 10000

        # Priority 2: Has h-index (indicates Scholar profile with data)
        if node["attributes"].get("h_index") is not None:
            score += 1000
            # Bonus points for higher h-index (more established researcher)
            score += node["attributes"].get("h_index", 0)

        # Priority 3: Has Scholar URL
        if node["links"].get("scholar_url"):
            score += 500

        # Priority 4: Longer name (more complete information)
        # "Priyanka Sharan" > "P Sharan"
        score += len(node["label"]) * 2

        # Priority 5: More collaborations with seed
        score += node["attributes"].get("collaborations_with_seed", 0) * 10

        # Priority 6: Full first name (not just initial)
        label_parts = node["label"].split()
        if label_parts and len(label_parts[0]) > 1:
            score += 5

        return score

    for cluster in clusters:
        if len(cluster) == 1:
            # No duplicate
            merged_nodes.append(cluster[0])
            continue

        # Multiple nodes - choose the best one to keep
        cluster.sort(key=score_node, reverse=True)
        kept_node = cluster[0]
        to_remove = cluster[1:]

        # If kept node has an abbreviated first name (e.g. "L Wang") but a removed
        # node has the full name (e.g. "Lu Wang"), promote the full name while
        # keeping all Scholar data (h_index, scholar_id, URL) from the kept node.
        kept_parts = kept_node["label"].split()
        kept_first_abbrev = (
            len(kept_parts) >= 1
            and len(kept_parts[0].replace(".", "").strip()) == 1
        )
        if kept_first_abbrev:
            for removed in to_remove:
                removed_parts = removed["label"].split()
                removed_first_full = (
                    len(removed_parts) >= 1
                    and len(removed_parts[0].replace(".", "").strip()) > 1
                )
                if removed_first_full:
                    old_id = kept_node["id"]
                    kept_node["label"] = removed["label"]
                    kept_node["id"] = _node_id("person", removed["label"])
                    # Remap edges that pointed to the old abbreviated ID
                    node_id_mapping[old_id] = kept_node["id"]
                    logger.info(
                        f"  Promoted full name: '{old_id}' → '{kept_node['label']}'"
                    )
                    break

        logger.info(
            f"Merging {len(to_remove)} duplicate(s) into '{kept_node['label']}'"
        )

        # Merge attributes from removed nodes
        for removed in to_remove:
            logger.debug(f"  Removing duplicate: '{removed['label']}'")

            # Merge roles
            kept_roles = set(kept_node.get("role", []))
            removed_roles = set(removed.get("role", []))
            kept_node["role"] = sorted(list(kept_roles | removed_roles))

            # Map old ID to kept ID
            node_id_mapping[removed["id"]] = kept_node["id"]

            merged_count += 1

        merged_nodes.append(kept_node)

    # Update edges to use merged node IDs
    updated_edges = []
    for edge in edges:
        source = edge["source"]
        target = edge["target"]

        # Replace with merged IDs if needed
        new_source = node_id_mapping.get(source, source)
        new_target = node_id_mapping.get(target, target)

        # Skip self-loops
        if new_source == new_target:
            continue

        # Update edge
        edge = dict(edge)
        edge["source"] = new_source
        edge["target"] = new_target

        # Check if this edge already exists (need to merge weights)
        edge_key = f"{new_source}__{edge['type']}__{new_target}"
        existing = [e for e in updated_edges if f"{e['source']}__{e['type']}__{e['target']}" == edge_key]

        if existing:
            # Merge weights
            existing[0]["weight"] = existing[0].get("weight", 1) + edge.get("weight", 1)
        else:
            updated_edges.append(edge)

    if merged_count > 0:
        logger.info(f"Merged {merged_count} duplicate person node(s)")

    return {
        "meta": graph["meta"],
        "nodes": merged_nodes,
        "edges": updated_edges,
    }


def build_graph_data(
    researcher_name: str,
    scholar: Optional[ScholarData],
    patents: PatentsData,
    max_patents: int = 10,
    patents_client: Optional[Any] = None,
    enrich_persons: bool = False,
    scholar_client: Optional[Any] = None,
    max_persons_to_enrich: int = 10
) -> Dict[str, Any]:
    """
    Build a network graph from Scholar and Patent data.

    Creates nodes for:
    - Seed person (the researcher)
    - Affiliated institution
    - Co-authors from publications
    - Publications (Scholar articles)
    - Patents
    - Co-inventors
    - Citing organizations

    Creates edges for:
    - has_patent: person -> patent
    - co_author_with: person -> co-author (publication collaboration)
    - authored_by: publication -> person (authorship)
    - co_invented: person -> co-inventor (aggregated patent collaboration)
    - co_invented_on: co-inventor -> patent (specific patent collaboration)
    - affiliated_with: person -> institution
    - cites_patent: organization -> patent (forward citations)

    Args:
        researcher_name: Name of the researcher.
        scholar: ScholarData object (optional).
        patents: PatentsData object.
        max_patents: Maximum patents to include (default: 10).
        patents_client: PatentsClient instance for resolving patent assignees (optional).
        enrich_persons: If True, enrich person nodes with Scholar profiles (default: False).
                       WARNING: Costs 2 API calls per person enriched.
        scholar_client: ScholarClient instance for enriching person nodes (optional).
        max_persons_to_enrich: Maximum persons to enrich (default: 10, ranked by collaborations).

    Returns:
        Dict with keys: meta, nodes, edges.

    Example:
        >>> graph = build_graph_data("Marie Curie", scholar_data, patents_data)
        >>> print(f"Nodes: {len(graph['nodes'])}")
        >>> print(f"Edges: {len(graph['edges'])}")
    """
    paris_now = datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds")

    seed_label = (scholar.name.strip() if scholar and scholar.name else researcher_name).strip()
    seed_id = _node_id("person", seed_label)

    gb = GraphBuilder()

    # Seed person node
    # Determine profile URL — OpenAlex author_id starts with https://openalex.org/
    _seed_author_id = scholar.author_id if scholar else None
    _is_openalex = bool(_seed_author_id and _seed_author_id.startswith("https://openalex.org/"))
    if _is_openalex:
        _profile_url = _seed_author_id  # already a full OpenAlex URL
    elif _seed_author_id:
        _profile_url = f"https://scholar.google.com/citations?user={_seed_author_id}"
    else:
        _profile_url = ""

    gb.add_node({
        "id": seed_id,
        "type": "person",
        "label": seed_label,
        "role": ["founder", "inventor"],
        "attributes": {
            "scholar_author_id": None if _is_openalex else _seed_author_id,
            "scholar_id": None if _is_openalex else _seed_author_id,
            "openalex_id": _seed_author_id if _is_openalex else None,
            "scholar_url": _profile_url or None,
            "affiliation": scholar.affiliation if scholar else "",
            "citations_total": scholar.citations_total if scholar else None,
            "h_index": scholar.h_index if scholar else None,
            "publications_total": scholar.publications_total if scholar else None,
        },
        "links": {
            "scholar_profile": _profile_url
        }
    })

    # Affiliation
    if scholar and scholar.affiliation:
        aff_label = scholar.affiliation.strip()
        aff_id = _node_id("org", aff_label)
        aff_type = _classify_org_type(aff_label)

        gb.add_node({
            "id": aff_id,
            "type": aff_type,
            "label": aff_label,
            "attributes": {"org_kind": aff_type},
            "links": {}
        })

        gb.add_edge(
            f"e:{seed_id}__affiliated_with__{aff_id}",
            {
                "source": seed_id,
                "target": aff_id,
                "type": "affiliated_with",
                "attributes": {"from": "scholar_affiliation"},
                "evidence": (
                    [{"kind": "url", "label": _profile_url.split("/")[2] if _profile_url else "Profile",
                      "url": _profile_url}]
                    if _profile_url else []
                )
            }
        )

    # Co-authors
    # Build publication lookup once (used for name resolution below)
    _pub_lookup_for_resolve: dict = {}
    if scholar and scholar.top_publications:
        for _p in scholar.top_publications:
            if _p.title:
                _pub_lookup_for_resolve[_normalize_person_name(_p.title)] = _p

    # For OpenAlex researchers: limit graph to top 50 co-authors by collaboration count.
    # scholar.coauthors stays complete (all co-authors used for corporate search / DB storage).
    _is_openalex_source = bool(
        scholar and scholar.author_id and "openalex.org" in scholar.author_id
    )
    _coauthors_for_graph = scholar.coauthors if scholar else []
    if _is_openalex_source and len(_coauthors_for_graph) > 50:
        _coauthors_for_graph = sorted(
            _coauthors_for_graph,
            key=lambda c: c.shared_pubs_count or 0,
            reverse=True
        )[:50]

    if scholar and _coauthors_for_graph:
        for coauthor in _coauthors_for_graph:
            coauthor_name = coauthor.name.strip()
            if not coauthor_name:
                continue

            # Check if this co-author is actually the seed person (abbreviated name)
            # This should normally not happen as _aggregate_coauthors already filters
            # but we add this check as a safety measure
            if _is_same_person(coauthor_name, seed_label):
                continue

            # Try to resolve abbreviated name (e.g. "L Wang" → "Lu Wang") using
            # the co-author's example_titles cross-referenced against publication authors.
            # This is zero extra API calls — we already have both pieces of data.
            resolved_name = _resolve_coauthor_name_via_publications(
                coauthor_name,
                coauthor.example_titles or [],
                list(_pub_lookup_for_resolve.values()),
            )
            name_was_resolved = False
            if resolved_name:
                from src.logger import logger as _log_resolve
                _log_resolve.info(
                    f"✓ Resolved co-author '{coauthor_name}' → '{resolved_name}' "
                    f"via example_titles"
                )
                coauthor_name = resolved_name
                name_was_resolved = True

            coauthor_id = _node_id("person", coauthor_name)

            # Homonymy detection: same name slug but different OpenAlex ID → different person
            if coauthor_id in gb.nodes and coauthor.openalex_id:
                existing_oa_id = gb.nodes[coauthor_id].get("attributes", {}).get("openalex_id")
                if existing_oa_id and existing_oa_id != coauthor.openalex_id:
                    short_id = coauthor.openalex_id.split("/")[-1].lower()
                    coauthor_id = f"person:{slug(coauthor_name)}__{short_id}"
                    from src.logger import logger as _log_homonym
                    _log_homonym.info(
                        f"Homonymy detected: '{coauthor_name}' has two OpenAlex IDs "
                        f"— disambiguated node: {coauthor_id}"
                    )

            # Add co-author node if not already present
            if coauthor_id not in gb.nodes:
                # If name was resolved from an abbreviated form, discard enrichment data
                # (h_index/scholar_id were fetched for the abbreviated name and may be wrong)
                if name_was_resolved:
                    node_h_index = None
                    node_scholar_id = None
                    node_scholar_url = None
                    scholar_profile_url = ""
                else:
                    node_h_index = coauthor.h_index
                    node_scholar_id = coauthor.scholar_id
                    node_scholar_url = coauthor.scholar_url
                    scholar_profile_url = coauthor.scholar_url or ""
                    if not scholar_profile_url and coauthor.scholar_id:
                        scholar_profile_url = f"https://scholar.google.com/citations?user={coauthor.scholar_id}"

                gb.add_node({
                    "id": coauthor_id,
                    "type": "person",
                    "label": coauthor_name,
                    "role": ["co_author"],
                    "attributes": {
                        "shared_pubs_count": coauthor.shared_pubs_count,
                        "last_shared_year": coauthor.last_shared_year,
                        "example_titles": coauthor.example_titles or [],
                        "h_index": node_h_index,
                        "scholar_id": node_scholar_id,
                        "scholar_url": node_scholar_url,
                        "openalex_id": coauthor.openalex_id or None,
                    },
                    "links": {
                        "scholar_profile": scholar_profile_url
                    }
                })

            # Add edge from seed to co-author
            gb.add_edge(
                f"e:{seed_id}__co_author_with__{coauthor_id}",
                {
                    "source": seed_id,
                    "target": coauthor_id,
                    "type": "co_author_with",
                    "weight": coauthor.shared_pubs_count,
                    "attributes": {
                        "shared_pubs_count": coauthor.shared_pubs_count,
                        "last_shared_year": coauthor.last_shared_year,
                    },
                    "evidence": (
                        [{"kind": "url", "label": _profile_url.split("/")[2] if _profile_url else "Profile",
                          "url": _profile_url}]
                        if _profile_url else []
                    )
                }
            )

    # Publications
    # Track co-authorship counts from publication author lists, to supplement
    # Scholar's explicit co-author list (which is often incomplete for young researchers)
    pub_coauthor_counts: dict = {}  # author_id -> {"name": str, "count": int, "pubs": [pub_id]}

    # Pre-pass A: build lookup pub_title (normalized) → Scholar co-author abbreviated name.
    # This lets us cross-reference: if Scholar says "L Wang" co-authored publication X,
    # and Semantic Scholar says publication X has "Linlin Wang" → "Linlin Wang" IS "L Wang".
    _pub_title_to_scholar_coauthor: dict = {}  # norm_title → abbreviated coauthor name
    if scholar and scholar.coauthors:
        for _ca in scholar.coauthors:
            for _title in (_ca.example_titles or []):
                _norm_title = _normalize_person_name(_title)  # reuse normalizer for consistency
                _pub_title_to_scholar_coauthor[_norm_title] = _ca.name

    # Pre-pass B: detect ambiguous publication co-authors.
    # If two distinct full names share the same (surname, first_initial), e.g. "Linlin Wang"
    # and "Lu Wang", they can't be naively attributed. We'll resolve them via cross-reference
    # (pre-pass A) in the main loop rather than blindly keeping or discarding them.
    _ambiguous_pub_author_norms: set = set()
    if scholar and scholar.top_publications:
        from collections import defaultdict as _defaultdict
        _si_to_names: dict = _defaultdict(set)  # (surname, initial) → set of full names
        for _pub in scholar.top_publications:
            for _aname in (_pub.authors or []):
                _aname = _aname.strip()
                if not _aname or _is_same_person(_aname, seed_label):
                    continue
                _norm = _normalize_person_name(_aname)
                _parts = _norm.split()
                # Only consider full first names (len > 1), not abbreviated "l wang"
                if len(_parts) >= 2 and len(_parts[0]) > 1:
                    _si_to_names[(_parts[-1], _parts[0][0])].add(_aname)
        for _key, _names in _si_to_names.items():
            if len(_names) > 1:
                from src.logger import logger as _log
                _log.warning(
                    f"⚠ Ambiguous pub co-authors {_key}: {_names} — "
                    f"will resolve via Scholar example_titles cross-reference"
                )
                for _n in _names:
                    _ambiguous_pub_author_norms.add(_normalize_person_name(_n))

    if scholar and scholar.top_publications:
        for pub in scholar.top_publications:  # All publications
            pub_title = (pub.title or "").strip()
            if not pub_title:
                continue

            pub_id = _publication_node_id(pub_title)

            # Add publication node
            gb.add_node({
                "id": pub_id,
                "type": "publication",
                "label": pub_title,
                "attributes": {
                    "year": pub.year,
                    "cited_by": pub.cited_by,
                    "authors": pub.authors or [],
                    "authors_count": len(pub.authors or []),
                    "source": pub.source or "",
                    "abstract": pub.abstract or "",
                },
                "links": {
                    "scholar_url": pub.link or "",
                }
            })

            # ALWAYS create an edge from publication to the seed person (researcher)
            # since these are HER publications
            gb.add_edge(
                f"e:{pub_id}__authored_by__{seed_id}",
                {
                    "source": pub_id,
                    "target": seed_id,
                    "type": "authored_by",
                    "attributes": {"year": pub.year},
                    "evidence": (
                        [{"kind": "url", "label": "Google Scholar",
                          "url": pub.link}]
                        if pub.link else []
                    )
                }
            )

            # Create edges from publication to all its other authors
            pub_authors = pub.authors or []
            for author_name in pub_authors:
                author_name = author_name.strip()
                if not author_name:
                    continue

                # Check if this author is the seed person (even with abbreviated name)
                # e.g., "A Nedelec" should match "Alice Nedelec"
                if _is_same_person(author_name, seed_label):
                    # Use the seed person's ID instead of creating a duplicate
                    author_id = seed_id
                else:
                    author_id = _node_id("person", author_name)

                # Skip edge creation if this is the seed person (already added above)
                if author_id == seed_id:
                    continue

                # If this author is ambiguous (same surname+initial as another pub co-author),
                # confirm via Scholar's example_titles cross-reference before adding.
                # e.g., Scholar says "L Wang" co-authored pub X → if pub X's full author list
                # shows "Linlin Wang" → confirmed. Otherwise skip to avoid false attribution.
                if _normalize_person_name(author_name) in _ambiguous_pub_author_norms:
                    _pub_norm = _normalize_person_name(pub_title)
                    _scholar_ca = _pub_title_to_scholar_coauthor.get(_pub_norm)
                    if _scholar_ca and _is_same_person(author_name, _scholar_ca):
                        from src.logger import logger as _log2
                        _log2.info(
                            f"✓ Resolved ambiguous '{author_name}' via '{pub_title[:50]}' "
                            f"(Scholar co-author: '{_scholar_ca}')"
                        )
                        # Confirmed — fall through and add normally
                    else:
                        # Can't confirm via Scholar example_titles → skip
                        continue

                # Add author node if not already present.
                # For OpenAlex: skip creating new nodes — only the top-50 co-authors
                # (added above via _coauthors_for_graph) get nodes. All author names
                # remain visible in the filter via publication node's attributes.authors.
                if author_id not in gb.nodes:
                    if _is_openalex_source:
                        continue
                    gb.add_node({
                        "id": author_id,
                        "type": "person",
                        "label": author_name,
                        "role": ["co_author"],
                        "attributes": {},
                        "links": {}
                    })

                # Add edge from publication to author
                gb.add_edge(
                    f"e:{pub_id}__authored_by__{author_id}",
                    {
                        "source": pub_id,
                        "target": author_id,
                        "type": "authored_by",
                        "attributes": {"year": pub.year},
                        "evidence": (
                            [{"kind": "url", "label": "Google Scholar",
                              "url": pub.link}]
                            if pub.link else []
                        )
                    }
                )

                # Track for co_author_with aggregation
                if author_id not in pub_coauthor_counts:
                    pub_coauthor_counts[author_id] = {"name": author_name, "count": 0, "pub_ids": []}
                pub_coauthor_counts[author_id]["count"] += 1
                pub_coauthor_counts[author_id]["pub_ids"].append(pub_id)

        # Create co_author_with edges for all publication co-authors not already
        # covered by Scholar's explicit co-author list
        already_linked = {
            e["target"] for e in gb.edges.values()
            if e.get("type") == "co_author_with" and e.get("source") == seed_id
        }
        for author_id, info in pub_coauthor_counts.items():
            if author_id in already_linked:
                # Scholar already gave us this co-author with better data; skip
                continue
            shared_count = info["count"]
            evidence_pubs = info["pub_ids"][:3]  # Limit evidence to 3 publications
            gb.add_edge(
                f"e:{seed_id}__co_author_with__{author_id}",
                {
                    "source": seed_id,
                    "target": author_id,
                    "type": "co_author_with",
                    "weight": shared_count,
                    "attributes": {"shared_pubs_count": shared_count},
                    "evidence": (
                        [{"kind": "url", "label": _profile_url.split("/")[2] if _profile_url else "Profile",
                          "url": _profile_url}]
                        if _profile_url else []
                    )
                }
            )

    # Patents
    top_patents = (patents.top_patents or [])[:max_patents]
    inventor_query = strip_accents_basic(seed_label)
    patents_search_url = f'https://patents.google.com/?q=inventor:"{inventor_query}"'

    for pt in top_patents:
        pid = pt.patent_id or ""
        patent_nid = _patent_node_id(_normalize_patent_id(pid) if pid else (pt.link or ""))
        pt_pub_dt = parse_yyyy_mm_dd(pt.publication_date)

        gb.add_node({
            "id": patent_nid,
            "type": "patent",
            "label": (pt.title or "(no title)").strip(),
            "attributes": {
                "patent_id": pid,
                "publication_date": pt.publication_date,
                "filing_date": pt.filing_date,
                "priority_date": pt.priority_date,
                "current_assignee": pt.current_assignee,
                "claims_top3": pt.claims_top3 or [],
                "co_inventors": pt.co_inventors or [],
                "cited_by": pt.cited_by,
                "citing_companies_count": len([
                    x for x in (pt.citing_assignees or [])
                    if x and not _is_placeholder(x)
                ]),
            },
            "links": {
                "patents_url": pt.link or "",
                "patents_search": patents_search_url
            }
        })

        gb.add_edge(
            f"e:{seed_id}__has_patent__{patent_nid}",
            {
                "source": seed_id,
                "target": patent_nid,
                "type": "has_patent",
                "evidence": [{"kind": "url", "label": "Google Patents", "url": pt.link}] if pt.link else []
            }
        )

        # Current assignee (ASSIGNED_TO edge)
        # Split by comma to handle multiple assignees
        if pt.current_assignee:
            assignee_parts = [part.strip() for part in pt.current_assignee.split(",") if part.strip()]

            for assignee_label in assignee_parts:
                assignee_canonical = _normalize_corp_name(assignee_label)
                assignee_type = _classify_org_type(assignee_canonical)
                assignee_id = _node_id("org", assignee_canonical)

                if assignee_id not in gb.nodes:
                    gb.add_node({
                        "id": assignee_id,
                        "type": assignee_type,
                        "label": assignee_canonical,
                        "role": ["assignee"],
                        "attributes": {"org_kind": assignee_type},
                        "links": {}
                    })

                edge_id = f"e:{patent_nid}__assigned_to__{assignee_id}"
                if edge_id not in gb.edges:
                    gb.add_edge(
                        edge_id,
                        {
                            "source": patent_nid,
                            "target": assignee_id,
                            "type": "assigned_to",
                            "attributes": {"relation": "current_assignee"},
                            "evidence": [{"kind": "url", "label": "Google Patents", "url": pt.link}] if pt.link else []
                        }
                    )

        # Co-inventors
        for name in dedup_preserve_order(pt.co_inventors or []):
            co_id = _node_id("person", name)
            if co_id not in gb.nodes:
                gb.add_node({
                    "id": co_id,
                    "type": "person",
                    "label": name,
                    "role": ["co_inventor"],
                    "attributes": {},
                    "links": {}
                })

            # Edge from seed person to co-inventor (aggregated view)
            gb.add_edge(
                f"e:{seed_id}__co_invented__{co_id}",
                {
                    "source": seed_id,
                    "target": co_id,
                    "type": "co_invented",
                    "attributes": {"via": ["patents"]},
                    "evidence": [{"kind": "url", "label": "Google Patents", "url": pt.link}] if pt.link else []
                }
            )

            # Edge from co-inventor to specific patent (detailed view)
            gb.add_edge(
                f"e:{co_id}__co_invented_on__{patent_nid}",
                {
                    "source": co_id,
                    "target": patent_nid,
                    "type": "co_invented_on",
                    "attributes": {"patent_id": pt.patent_id or ""},
                    "evidence": [{"kind": "url", "label": "Google Patents", "url": pt.link}] if pt.link else []
                }
            )

        # Forward citations (patents that cite this patent)
        raw_events = list(getattr(pt, "citing_patents", None) or [])
        current_assignee = (getattr(pt, "current_assignee", None) or "").strip()

        # Filter events by date
        filtered_events = []
        for ev in raw_events:
            ev_pub_dt = parse_yyyy_mm_dd(ev.get("publication_date") if isinstance(ev, dict) else None)
            if pt_pub_dt and ev_pub_dt and ev_pub_dt < pt_pub_dt:
                continue
            filtered_events.append(ev)

        # Get citing companies (excluding self-citations)
        citing_companies = dedup_preserve_order([
            (ev.get("assignee") or "").strip()
            for ev in filtered_events
            if isinstance(ev, dict)
            and (ev.get("assignee") or "").strip()
            and not _is_placeholder((ev.get("assignee") or "").strip())
            and not (current_assignee and _same_org((ev.get("assignee") or "").strip(), current_assignee))
        ])

        # Fallback to citing_assignees when no detailed events
        if not citing_companies and not raw_events:
            citing_companies = dedup_preserve_order([
                c for c in (pt.citing_assignees or [])
                if c and not _is_placeholder(c)
                and not (current_assignee and _same_org(c, current_assignee))
            ])

        for comp in citing_companies:
            comp_canonical = _normalize_corp_name(comp) if comp else comp
            entity_type = _classify_entity_type(comp_canonical)
            node_prefix = "person" if entity_type == "person" else "org"
            entity_id = _node_id(node_prefix, comp_canonical)

            if entity_id not in gb.nodes:
                gb.add_node({
                    "id": entity_id,
                    "type": entity_type,
                    "label": comp_canonical,
                    "role": ["citing_assignee"] if entity_type == "person" else [],
                    "attributes": {"org_kind": entity_type} if entity_type != "person" else {},
                    "links": {}
                })
            org_id = entity_id  # Keep variable name for edge creation

            # Find matching events for this company
            events = [
                ev for ev in filtered_events
                if isinstance(ev, dict) and _same_org((ev.get("assignee") or "").strip(), comp)
            ]

            # If using fallback (no detailed events), still create edge with weight 1
            weight = len(events) if events else 1
            events_count = len(events) if events else 1

            gb.add_edge(
                f"e:{org_id}__cites_patent__{patent_nid}",
                {
                    "source": org_id,
                    "target": patent_nid,
                    "type": "cites_patent",
                    "weight": weight,
                    "attributes": {"section": "Cited By", "events_count": events_count},
                    "evidence": [{"kind": "url", "label": "Google Patents", "url": pt.link}] if pt.link else []
                }
            )

    # Calculate collaborations for all person nodes (ALWAYS, not just when enriching)
    person_nodes_with_collab = []

    for node_id, node in gb.nodes.items():
        if node["type"] != "person" or node_id == seed_id:
            continue

        # Calculate collaborations with seed person
        collab_count = 0

        # Count co-publications
        for edge_id, edge in gb.edges.items():
            if edge["type"] == "co_author_with":
                if (edge["source"] == seed_id and edge["target"] == node_id) or \
                   (edge["source"] == node_id and edge["target"] == seed_id):
                    collab_count += edge.get("weight", 1)

        # Count co-inventions
        for edge_id, edge in gb.edges.items():
            if edge["type"] == "co_invented":
                if (edge["source"] == seed_id and edge["target"] == node_id) or \
                   (edge["source"] == node_id and edge["target"] == seed_id):
                    collab_count += edge.get("weight", 1)

        # Always add collaboration count to node
        node["attributes"]["collaborations_with_seed"] = collab_count

        person_nodes_with_collab.append({
            "node_id": node_id,
            "node": node,
            "collab_count": collab_count
        })

    # Enrich person nodes with Scholar profiles (optional, requires API calls)
    if enrich_persons and scholar_client:
        from src.logger import logger
        logger.info("Enriching person nodes with Scholar profiles...")

        # Sort by collaboration count (descending) and take top N
        person_nodes_with_collab.sort(key=lambda x: x["collab_count"], reverse=True)
        persons_to_enrich = person_nodes_with_collab[:max_persons_to_enrich]

        total_persons = len(person_nodes_with_collab)
        enriching_count = len(persons_to_enrich)

        logger.info(
            f"Enriching {enriching_count}/{total_persons} persons "
            f"(top collaborators, max={max_persons_to_enrich})"
        )
        logger.info(f"Estimated API calls: {enriching_count * 2}")

        # Enrich top N persons with Scholar profiles
        enriched_count = 0
        failed_count = 0

        for i, item in enumerate(persons_to_enrich, 1):
            node = item["node"]
            person_name = node["label"]

            logger.info(f"[{i}/{enriching_count}] Enriching '{person_name}'...")

            # Enrich with Scholar profile
            scholar_data = _enrich_person_with_scholar(person_name, scholar_client)

            # Update node attributes
            if scholar_data["h_index"] is not None:
                node["attributes"]["h_index"] = scholar_data["h_index"]
                enriched_count += 1
            else:
                failed_count += 1

            # Update node links
            if scholar_data["scholar_profile_url"]:
                node["links"]["scholar_profile"] = scholar_data["scholar_profile_url"]

            # Save enriched data to database for future reuse
            if scholar_data["h_index"] is not None or scholar_data["scholar_profile_url"]:
                try:
                    from src.database.database import SessionLocal
                    from src.database.deduplication import find_or_create_scientist

                    db_session = SessionLocal()
                    try:
                        # Extract scholar_id from URL if available
                        scholar_id = None
                        if scholar_data["scholar_profile_url"]:
                            import re
                            match = re.search(r'user=([^&]+)', scholar_data["scholar_profile_url"])
                            if match:
                                scholar_id = match.group(1)

                        # Save to DB
                        scientist, created = find_or_create_scientist(
                            db_session,
                            name=person_name,
                            scholar_id=scholar_id,
                            h_index=scholar_data["h_index"],
                            scholar_url=scholar_data["scholar_profile_url"],
                            openalex_id=node["attributes"].get("openalex_id")
                        )
                        db_session.commit()

                        if created:
                            logger.debug(f"  💾 Saved {person_name} to DB")
                        else:
                            logger.debug(f"  💾 Updated {person_name} in DB")

                    finally:
                        db_session.close()

                except Exception as e:
                    logger.debug(f"  Could not save {person_name} to DB: {e}")

        logger.info(
            f"Person enrichment completed: {enriched_count} enriched, {failed_count} not found"
        )

    # Build initial graph
    graph = {
        "meta": {
            "graph_id": f"{slug(seed_label)}_{paris_now.replace(':', '-')}",
            "seed_person_id": seed_id,
            "generated_at": paris_now,
            "sources": ["google_scholar", "google_patents"],
            "scope": {"max_patents": max_patents},
        },
        "nodes": list(gb.nodes.values()),
        "edges": list(gb.edges.values()),
    }

    # Merge duplicate person nodes
    graph = _merge_duplicate_persons(graph)

    return graph
