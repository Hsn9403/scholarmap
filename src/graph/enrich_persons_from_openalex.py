"""
Enrich person nodes with OpenAlex data (h_index, openalex_url).

Used when the seed researcher was sourced from OpenAlex (not Scholar).
For each person node in the graph, searches OpenAlex by name to get
h_index and profile URL — 1 API call per node.

OpenAlex is free with generous rate limits (~10 req/s recommended).
Requests are parallelized with ThreadPoolExecutor (max 10 workers).
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

from src.logger import logger
from src.progress import report


def _store_openalex_institutions(attrs: dict, author: dict) -> None:
    """Extrait et stocke toutes les institutions OpenAlex dans les attrs du nœud."""
    all_institutions = []
    seen_names: set = set()
    for inst in (author.get("last_known_institutions") or []):
        name = inst.get("display_name", "").strip()
        if name and name not in seen_names:
            all_institutions.append({
                "name": name,
                "openalex_url": inst.get("id", ""),
                "is_current": True,
            })
            seen_names.add(name)
    for aff in (author.get("affiliations") or []):
        inst_data = aff.get("institution") or {}
        name = inst_data.get("display_name", "").strip()
        if name and name not in seen_names:
            all_institutions.append({
                "name": name,
                "openalex_url": inst_data.get("id", ""),
                "is_current": False,
            })
            seen_names.add(name)
    if all_institutions:
        attrs["openalex_institutions"] = all_institutions


def enrich_persons_from_openalex(
    graph: Dict[str, Any],
    openalex_client,
) -> int:
    """
    Enrich all person nodes in the graph with OpenAlex data.

    For each person node:
    - Searches OpenAlex by name (display_name.search filter)
    - Reads h_index from summary_stats
    - Sets openalex_id attribute and scholar_profile link (OpenAlex URL)
    - Sets affiliation if not already present

    Nodes that already have h_index set (e.g. the seed node) are skipped
    unless they lack an openalex_url, in which case only the URL is added.

    Args:
        graph: Graph dict with nodes and edges.
        openalex_client: OpenAlexClient instance.

    Returns:
        Number of person nodes enriched with at least h_index.
    """
    person_nodes = [
        n for n in graph.get("nodes", [])
        if n.get("type") == "person"
    ]

    if not person_nodes:
        return 0

    logger.info(
        f"[OpenAlex] Enrichissement de {len(person_nodes)} nœuds personnes avec OpenAlex..."
    )

    def _enrich_node(node: Dict[str, Any]) -> bool:
        """Enrich a single person node. Returns True if h_index was set."""
        name = node.get("label") or ""
        if not name:
            return False

        attrs = node.setdefault("attributes", {})
        links = node.setdefault("links", {})

        # Si le nœud a déjà un openalex_id (chercheur seed), on récupère quand même
        # ses affiliations via get_author() pour créer les nœuds institution.
        if attrs.get("openalex_id"):
            if not links.get("scholar_profile"):
                links["scholar_profile"] = attrs["openalex_id"]
            if not attrs.get("openalex_institutions"):
                try:
                    from src.pathfinding.openalex_client import OpenAlexClient as _OAClient
                    _client = _OAClient()
                    author = _client.get_author(attrs["openalex_id"])
                    if author:
                        _store_openalex_institutions(attrs, author)
                except Exception as _e:
                    logger.warning(f"  ⚠ {name}: institution fetch failed: {_e}")
            return False

        # Skip co-authors that are Scholar-sourced (have a scholar_id)
        if attrs.get("scholar_id"):
            return False

        try:
            # Each thread uses its own client instance to avoid contention on
            # the shared _last_request_time rate-limiter
            from src.pathfinding.openalex_client import OpenAlexClient as _OAClient
            _client = _OAClient()
            author = _client.search_author(name)
            if not author:
                logger.debug(f"  ⊘ {name}: not found in OpenAlex")
                return False

            openalex_url: str = author.get("id", "")
            h_index = (author.get("summary_stats") or {}).get("h_index")

            institutions = author.get("last_known_institutions") or []
            affiliation = institutions[0].get("display_name", "") if institutions else ""

            if openalex_url:
                attrs["openalex_id"] = openalex_url
                links["scholar_profile"] = openalex_url

            if h_index is not None:
                attrs["h_index"] = h_index

            if affiliation and not attrs.get("affiliation"):
                attrs["affiliation"] = affiliation

            # Store all institutions (current + past) for graph node creation
            _store_openalex_institutions(attrs, author)

            logger.info(
                f"  ✅ {name}: h_index={h_index}"
                + (f", openalex={openalex_url}" if openalex_url else "")
            )
            return h_index is not None

        except Exception as e:
            logger.warning(f"  ⚠ {name}: OpenAlex enrichment failed: {e}")
            return False

    enriched = 0
    done = 0
    report("coauthors_openalex", 0, len(person_nodes))
    # 5 workers max pour limiter la consommation mémoire sur Clever Cloud XS (256MB).
    # Chaque worker crée sa propre session HTTP — au-delà de 5, le risque OOM augmente.
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_enrich_node, node): node for node in person_nodes}
        for future in as_completed(futures):
            if future.result():
                enriched += 1
            done += 1
            report("coauthors_openalex", done, len(person_nodes))

    logger.info(
        f"✅ [OpenAlex] Person enrichment: {enriched}/{len(person_nodes)} nodes enriched"
    )
    return enriched
