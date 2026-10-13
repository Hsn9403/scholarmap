"""
Tolerant author lookup on OpenAlex, for the "type a name" step.

OpenAlex's `display_name.search` filter is strict: "Yann Le Cun" finds nothing
while "Yann LeCun" does, and a single typo ("Yan Lecun") returns zero results.
People type names the way they heard them, so the lookup runs in tiers and stops
at the first one that returns something:

1. exact: the name as typed;
2. variants: particles joined or split ("Le Cun" / "LeCun"), accents and
   hyphens dropped;
3. approximate: search on the family name alone, then keep the profiles whose
   name is close to what was typed (catches typos in either name).

Only tier 3 is flagged `approximate`, so the caller can say "closest matches".
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

# Below this, a tier-3 profile is considered someone else
APPROXIMATE_MIN_SCORE = 0.8


def _normalize(name: str) -> str:
    """Lowercase, no accents, letters and single spaces only."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-zA-Z\s]", " ", name).lower()
    return re.sub(r"\s+", " ", name).strip()


def name_similarity(query: str, candidate: str) -> float:
    """
    How close a profile name is to what was typed, between 0 and 1.

    Compared with spaces removed ("le cun" vs "lecun"), in the typed order and with
    the typed tokens reversed ("Charpentier Emmanuelle"). Order matters within each
    comparison, so "Yan Lecun" stays far from "Lecun Wang". A middle initial in the
    profile ("Jennifer A. Doudna") is ignored when the query has none.
    """
    q, c = _normalize(query), _normalize(candidate)
    if not q or not c:
        return 0.0
    q_tokens = q.split()
    c_tokens = [t for t in c.split() if len(t) > 1 or len(q_tokens) > 2] or c.split()
    target = "".join(c_tokens)
    straight = SequenceMatcher(None, "".join(q_tokens), target).ratio()
    reversed_ = SequenceMatcher(None, "".join(reversed(q_tokens)), target).ratio()
    return max(straight, reversed_)


def name_variants(name: str) -> List[str]:
    """Other ways the same name is commonly written, most likely first."""
    tokens = name.split()
    variants: List[str] = []
    if len(tokens) >= 3:
        # "Yann Le Cun" -> "Yann LeCun"; "Ana De La Cruz" -> "Ana DeLaCruz"
        variants.append(" ".join(tokens[:1] + ["".join(tokens[1:])]))
        variants.append(" ".join(tokens[:-2] + [tokens[-2] + tokens[-1]]))
    # "Yann LeCun" -> "Yann Le Cun"
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    if split != name:
        variants.append(split)
    plain = _normalize(name)
    if plain and plain != name.lower():
        variants.append(plain)
    seen, unique = {name.lower()}, []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower())
            unique.append(v)
    return unique


def search_author_candidates(
    name: str, client: Any, limit: int = 5
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Up to `limit` OpenAlex author records for a typed name.

    Args:
        name: What the user typed.
        client: An OpenAlexClient (only `_make_request` is used).
        limit: Maximum number of profiles returned.

    Returns:
        (authors, approximate): raw OpenAlex author dicts, and whether they come
        from the typo-tolerant tier rather than an exact or variant match.
    """
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return [], False

    def _by_display_name(query: str) -> List[Dict[str, Any]]:
        raw = client._make_request("/authors", {
            "filter": f"display_name.search:{query}",
            "per-page": limit,
        })
        return raw.get("results", [])

    # 1 + 2. exact, then common spelling variants
    for query in [name] + name_variants(name):
        results = _by_display_name(query)
        if results:
            return results[:limit], False

    # 3. family name alone, ranked by closeness to the typed name
    tokens = _normalize(name).split()
    if not tokens:
        return [], False
    pool: Dict[str, Dict[str, Any]] = {}
    family_queries = [tokens[-1]]
    if len(tokens) >= 3:
        family_queries.append("".join(tokens[1:]))  # "le cun" typed with a typo
    for query in family_queries:
        raw = client._make_request("/authors", {"search": query, "per-page": 50})
        for author in raw.get("results", []):
            pool.setdefault(author.get("id", ""), author)

    # A typo at the end of the family name ("Lecunn") defeats the search above:
    # autocomplete on a shortened family name, then fetch those profiles in full
    if len(tokens) >= 2:
        first, family = " ".join(tokens[:-1]), tokens[-1]
        ids: List[str] = []
        for cut in (1, 2):
            if len(family) - cut < 3:
                break
            raw = client._make_request("/autocomplete/authors", {"q": f"{first} {family[:-cut]}"})
            ids += [r["id"].rsplit("/", 1)[-1] for r in raw.get("results", []) if r.get("id")]
        ids = [i for i in dict.fromkeys(ids) if f"https://openalex.org/{i}" not in pool][:25]
        if ids:
            raw = client._make_request("/authors", {
                "filter": "openalex_id:" + "|".join(ids),
                "per-page": len(ids),
            })
            for author in raw.get("results", []):
                pool.setdefault(author.get("id", ""), author)

    scored = sorted(
        ((name_similarity(name, a.get("display_name", "")), a) for a in pool.values()),
        key=lambda pair: (pair[0], pair[1].get("works_count", 0)),
        reverse=True,
    )
    close = [a for score, a in scored if score >= APPROXIMATE_MIN_SCORE]
    return close[:limit], bool(close)
