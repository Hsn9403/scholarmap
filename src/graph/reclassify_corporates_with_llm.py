"""
Reclassify corporate graph nodes that are actually institutions.

Uses GPT-4o to review the full list of corporate-labelled nodes and flag
those that are universities, research centers, hospitals or public agencies.
The reclassification is purely in-memory (graph dict mutation) — no DB write.
"""
import os
import json
import re
import time
from typing import Dict, List

from src.logger import logger


_SYSTEM_PROMPT = """You are an expert entity classifier for a scientific due-diligence tool.
You receive a list of organization names that have been automatically labelled as "corporate"
(i.e. private companies). Your job is to identify which ones are actually institutions
(universities, research centers, hospitals, public agencies, non-profits, government bodies, etc.)
and should be reclassified.

Respond ONLY with a valid JSON array of the IDs that must be reclassified as institution.
No markdown, no explanation, just the JSON array.
Example: ["node_42", "node_7"]
If none need reclassification, return: []"""

_USER_PROMPT_TEMPLATE = """Here is the list of nodes currently classified as "corporate".
For each, the ID and the display name are given.

{entries}

Return a JSON array with the IDs of entities that are NOT private companies but rather
institutions (universities, research labs, hospitals, government bodies, public agencies,
non-profits, etc.).

Examples of what MUST be reclassified as institution:
- "Centre Nat Rech Scient" → CNRS → public research agency → institution
- "Inserm" → French public medical research agency → institution
- "Assistance Publique Hopitaux" → public hospital system → institution
- "Harvard University", "MIT", "Sorbonne" → academic institution
- "CHU de Paris", "AP-HP" → public hospital → institution
- "Inria", "CEA", "CNRS" → French public research bodies → institution

Examples of what MUST stay as corporate (do NOT reclassify):
- "Pfizer", "Sanofi", "Boehringer Ingelheim", "Roche", "AbbVie" → pharma companies → corporate
- "Hologic", "Medtronic", "Siemens Healthineers", "Abbott" → medical device companies → corporate
- "Audika Groupe Sa", "Cadeka Microcircuits Llc" → companies → corporate
- Any company with a country suffix like "(Germany)", "(France)", "(USA)" → usually corporate
- Any entity with Inc, Corp, SA, SAS, GmbH, Ltd, LLC in the name → corporate

Be conservative: when in doubt, leave as corporate. Only reclassify if you are certain it is a public/academic institution."""


def reclassify_corporate_nodes_with_llm(graph: Dict) -> Dict:
    """
    Review corporate nodes in the graph and reclassify institutions.

    Mutates graph in-place: changes node["type"] from "corporate" to "institution"
    for nodes identified by GPT-4o as actual institutions.

    Args:
        graph: Graph dict with keys "nodes" and "edges".

    Returns:
        The same graph dict (mutated in-place).
    """
    _t_total = time.time()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — corporate reclassification skipped")
        return graph

    # Gather all corporate nodes
    all_corporate_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "corporate"]
    if not all_corporate_nodes:
        logger.info("[LLM] No corporate nodes to reclassify.")
        return graph

    # Pre-filter: skip nodes with unambiguous corporate suffixes — the LLM doesn't
    # need to see "Pfizer Inc." or "Sanofi SA". Only send names where it's unclear.
    _CORPORATE_SUFFIX = re.compile(
        r"\b(inc|corp|corporation|co|ltd|llc|llp|plc|sa|sas|sarl|gmbh|ag|bv|nv|oy|ab)\b\.?$",
        re.IGNORECASE,
    )
    ambiguous_nodes = [
        n for n in all_corporate_nodes
        if not _CORPORATE_SUFFIX.search((n.get("label") or n["id"]).rstrip())
    ]

    if not ambiguous_nodes:
        logger.info(f"[LLM] All {len(all_corporate_nodes)} corporate nodes have clear suffixes — skipping LLM.")
        return graph

    logger.info(
        f"[LLM] Starting reclassification: {len(ambiguous_nodes)} ambiguous nodes "
        f"(skipped {len(all_corporate_nodes) - len(ambiguous_nodes)} with clear corporate suffixes)..."
    )

    # Build prompt entries — one per line for readability
    entries = "\n".join(
        f'- ID: "{n["id"]}"  Name: "{n.get("label", n["id"])}"'
        for n in ambiguous_nodes
    )
    user_prompt = _USER_PROMPT_TEMPLATE.format(entries=entries)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

        logger.info(f"[LLM] Calling {model} for corporate reclassification...")
        _t_start = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_completion_tokens=2000,  # enough for all IDs even if 200+ nodes
        )

        _t_elapsed = time.time() - _t_start
        logger.info(f"[LLM] Response received in {_t_elapsed:.2f}s")

        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ids_to_reclassify: List[str] = json.loads(raw)

        if not ids_to_reclassify:
            logger.info("[LLM] No corporate nodes to reclassify as institution.")
            return graph

        # Build a lookup set for fast access
        ids_set = set(str(i) for i in ids_to_reclassify)

        reclassified = []
        for node in graph["nodes"]:
            if str(node.get("id")) in ids_set and node.get("type") == "corporate":
                node["type"] = "institution"
                reclassified.append(node.get("label", node["id"]))

        logger.info(
            f"[LLM] Reclassified {len(reclassified)} node(s) from corporate → institution: "
            + ", ".join(reclassified)
        )

    except Exception as e:
        logger.error(f"LLM corporate reclassification failed: {e}")

    _t_total_elapsed = time.time() - _t_total
    logger.info(f"[LLM] Total reclassification time: {_t_total_elapsed:.2f}s")

    return graph
