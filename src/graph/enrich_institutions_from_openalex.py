"""
Create institution nodes from OpenAlex affiliation data stored in person nodes.

Must be called AFTER enrich_persons_from_openalex(), which stores
openalex_institutions in each person node's attributes.
"""
import re
from typing import Dict, Any

from src.logger import logger

# Large corporations that OpenAlex sometimes misclassifies as institutions
# (e.g. "Apple (Israel)", "Boehringer Ingelheim (Germany)").
# Names may be followed by a country suffix in parentheses — handled by \b.
_KNOWN_CORPORATE = re.compile(
    r"""
    # ── Big Pharma (US/EU) ──────────────────────────────────────────────────
    \bpfizer\b | \broche\b | \bnovartis\b | \bsanofi\b | \bastrazeneca\b
    | \bboehringer\b | \bmerck\b | \bbayer\b | \bgsk\b
    | \bglaxosmithkline\b | \beli\s+lilly\b | \blilly\b
    | \bbristol.myers\b | \babbvie\b | \bamgen\b | \bgilead\b
    | \bbiogen\b | \bmoderna\b | \bregeneron\b | \bjanssen\b
    | \bgenentech\b | \bservier\b | \bipsen\b | \bguerbet\b
    | \bpierre\s+fabre\b | \bipr\b
    # ── Big Medtech / Device (US/EU) ────────────────────────────────────────
    | \bmedtronic\b | \babbott\b | \bsiemens\s+healthineers\b
    | \bge\s+healthcare\b | \bphilips\b | \bboston\s+scientific\b
    | \bstryker\b | \bzimmer\b | \bbecton\b | \bbd\b
    | \bhologic\b | \bintuitive\s+surgical\b | \bbaxter\b
    | \bterumo\b | \bfresenius\b | \bgetinge\b | \bpenumbra\b
    # ── Big Tech with healthcare arms ───────────────────────────────────────
    | \bapple\b | \bgoogle\b | \balphabet\b | \bmicrosoft\b
    | \bamazon\b | \bibm\b | \bmeta\b | \bverily\b
    | \bnvidia\b | \bqualcomm\b
    # ── French industry ─────────────────────────────────────────────────────
    | \bair\s+liquide\b | \bbiomerieux\b | \bessilor\b | \bvygon\b
    | \beos\s+imaging\b
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_known_corporate(name: str) -> bool:
    """Return True if the name matches a well-known corporate entity."""
    return bool(_KNOWN_CORPORATE.search(name or ""))


def enrich_institutions_from_openalex(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Iterate person nodes that have openalex_institutions set and create:
    - One institution node (type="institution", color=purple) per unique institution
    - One affiliated_with edge per (person, institution) pair

    Deduplicates by institution name across all persons.
    Skips institution IDs that already exist in the graph (e.g. seed affiliation).

    Args:
        graph: Graph dict with nodes and edges (modified in-place and returned).

    Returns:
        Updated graph dict.
    """
    # Seed : institutions actuelles + passées
    # Autres co-auteurs : institution actuelle seulement (déduplication → ~15-25 nœuds)
    seed_id = graph.get("meta", {}).get("seed_person_id")

    existing_ids: set = {n["id"] for n in graph["nodes"]}
    existing_edge_ids: set = {e.get("id", "") for e in graph["edges"]}

    new_nodes: Dict[str, Dict] = {}  # inst_id -> node dict (dedup)
    new_edges: list = []

    for node in graph["nodes"]:
        if node.get("type") != "person":
            continue

        attrs = node.get("attributes", {})
        all_institutions = attrs.get("openalex_institutions", [])
        if not all_institutions:
            continue

        person_id = node["id"]
        is_seed = (seed_id and person_id == seed_id)

        # Seed : tout ; co-auteurs : institution actuelle uniquement
        institutions = all_institutions if is_seed else [i for i in all_institutions if i.get("is_current")]

        if is_seed:
            current = [i["name"] for i in institutions if i.get("is_current")]
            past = [i["name"] for i in institutions if not i.get("is_current")]
            logger.info(f"[Institutions/seed] {node['label']}: {len(institutions)} total — current={current} | past={past}")

        for inst in institutions:
            name = inst.get("name", "").strip()
            if not name:
                continue

            # Known corporates misclassified by OpenAlex → create as corporate node
            if _is_known_corporate(name):
                logger.debug(f"[Institutions] Reclassifying as corporate: {name}")
                safe = name.lower()[:50]
                for ch in " /-(),.":
                    safe = safe.replace(ch, "_")
                corp_id = f"corporate:{safe}"
                if corp_id not in existing_ids and corp_id not in new_nodes:
                    new_nodes[corp_id] = {
                        "id": corp_id,
                        "type": "corporate",
                        "label": name,
                        "attributes": {"source": "openalex", "country": ""},
                    }
                edge_id = f"e:{person_id}__affiliated_with__{corp_id}"
                if edge_id not in existing_edge_ids:
                    new_edges.append({
                        "id": edge_id,
                        "source": person_id,
                        "target": corp_id,
                        "type": "affiliated_with_corporate",
                        "label": "openalex",
                        "weight": 1,
                        "attributes": {"source": "openalex", "is_current": inst.get("is_current", False)},
                        "evidence": [],
                    })
                    existing_edge_ids.add(edge_id)
                continue

            # Build a stable node ID from the institution name
            safe = name.lower()[:50]
            for ch in " /-(),.":
                safe = safe.replace(ch, "_")
            inst_id = f"inst:{safe}"

            if inst_id not in existing_ids and inst_id not in new_nodes:
                new_nodes[inst_id] = {
                    "id": inst_id,
                    "type": "institution",
                    "label": name,
                    "attributes": {
                        "source": "openalex",
                        "is_current": inst.get("is_current", False),
                    },
                    "links": {
                        "openalex_url": inst.get("openalex_url", "")
                    },
                }

            edge_id = f"e:{person_id}__affiliated_with__{inst_id}"
            if edge_id not in existing_edge_ids:
                new_edges.append({
                    "id": edge_id,
                    "source": person_id,
                    "target": inst_id,
                    "type": "affiliated_with",
                    "weight": 1,
                    "attributes": {
                        "source": "openalex",
                        "is_current": inst.get("is_current", False),
                    },
                    "evidence": [],
                })
                existing_edge_ids.add(edge_id)

    if new_nodes:
        graph["nodes"].extend(new_nodes.values())
        graph["edges"].extend(new_edges)
        logger.info(
            f"✅ [OpenAlex] Institutions : {len(new_nodes)} nœuds créés, "
            f"{len(new_edges)} arêtes ajoutées"
        )
    else:
        logger.info("ℹ️  [OpenAlex] Aucune donnée d'institution à ajouter au graphe")

    return graph
