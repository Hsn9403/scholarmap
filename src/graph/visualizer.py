#!/usr/bin/env python3
"""
Graph visualization and filtering utilities.

This module provides functions to:
- Filter graphs to N-hop neighborhoods
- Render interactive HTML visualizations using pyvis
"""
from __future__ import annotations

import json as _json
import math
from html import escape as _esc
from typing import Any, Dict, List, Optional, Set

import networkx as nx
from pyvis.network import Network

from src.logger import logger
from src.helpers import slug


def _title_case_corporate(name: str) -> str:
    """
    Convert corporate name to Title Case for professional display.

    Examples:
        "astrazeneca" -> "Astrazeneca"
        "eli lilly" -> "Eli Lilly"
        "meta platforms inc" -> "Meta Platforms Inc"
    """
    if not name:
        return name
    return name.title()


def extract_two_hop_subgraph(
    graph: Dict[str, Any],
    cutoff: int = 2,
    allowed_types: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Extract a subgraph containing only nodes within N hops of the seed.

    Uses BFS to find all nodes within `cutoff` distance from the seed node,
    then keeps only edges where both endpoints are in the subgraph.

    Args:
        graph: Full graph dict with keys: meta, nodes, edges.
        cutoff: Maximum distance from seed (default: 2).
        allowed_types: Optional set of node types to keep (seed always kept).

    Returns:
        Filtered graph dict with same structure.

    Raises:
        KeyError: If graph.meta.seed_person_id is missing.

    Example:
        >>> subgraph = extract_two_hop_subgraph(full_graph, cutoff=2)
        >>> print(f"Filtered to {len(subgraph['nodes'])} nodes")
    """
    meta = graph.get("meta", {}) or {}
    seed = meta.get("seed_person_id")
    if not seed:
        raise KeyError("graph.meta.seed_person_id is required")

    nodes_in = graph.get("nodes", []) or []
    edges_in = graph.get("edges", []) or []

    # Build lookup
    node_lookup: Dict[str, Dict[str, Any]] = {
        n["id"]: n for n in nodes_in
        if isinstance(n, dict) and "id" in n
    }

    # Build NetworkX graph (undirected for distance calculation)
    G = nx.Graph()
    for nid, n in node_lookup.items():
        G.add_node(nid, **n)

    for e in edges_in:
        if not isinstance(e, dict):
            continue
        src, tgt = e.get("source"), e.get("target")
        if src and tgt:
            G.add_edge(src, tgt, **e)

    # BFS to find nodes within cutoff
    lengths = nx.single_source_shortest_path_length(G, seed, cutoff=cutoff)
    kept_ids: Set[str] = set(lengths.keys())

    # Optional type filtering
    if allowed_types is not None:
        filtered: Set[str] = set()
        for nid in kept_ids:
            if nid == seed:
                filtered.add(nid)
                continue
            n = node_lookup.get(nid)
            if n and n.get("type") in allowed_types:
                filtered.add(nid)
        kept_ids = filtered

    # Filter edges and nodes
    kept_edges = [
        e for e in edges_in
        if isinstance(e, dict)
        and e.get("source") in kept_ids
        and e.get("target") in kept_ids
    ]

    kept_nodes = [node_lookup[nid] for nid in kept_ids if nid in node_lookup]

    return {
        "meta": {
            **meta,
            "scope": {
                **(meta.get("scope", {}) or {}),
                "two_hop": True,
                "cutoff": cutoff,
                **({"allowed_types": sorted(list(allowed_types))} if allowed_types else {}),
            },
        },
        "nodes": kept_nodes,
        "edges": kept_edges,
    }


# Node colors by type
NODE_COLORS = {
    "person": "#2D7FF9",
    "corporate": "#F39C12",
    "institution": "#9B59B6",
    "patent": "#34495E",
    "publication": "#27AE60",  # Green for publications
}

# Usage instructions banner (displayed at top of graph)
USAGE_INSTRUCTIONS_HTML = """
<div id="usage-instructions" style="
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #EFF6FF, #DBEAFE);
    border: 1px solid #3B82F6;
    border-radius: 10px;
    padding: 14px 24px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    box-shadow: 0 3px 10px rgba(59, 130, 246, 0.15);
    z-index: 9998;
    max-width: 700px;
    line-height: 1.6;
">
  <div style="display: flex; gap: 24px; color: #1E40AF;">
    <div style="flex: 1;">
      <div style="font-weight: 600; margin-bottom: 4px; color: #1E3A8A;">
        <svg style="display: inline-block; width: 14px; height: 14px; margin-right: 4px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <circle cx="12" cy="12" r="10"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
        Node size
      </div>
      <div style="font-size: 12px; color: #3B82F6;">
        Larger = key bridges between academia & industry
      </div>
    </div>
    <div style="border-left: 1px solid #93C5FD; margin: 0 8px;"></div>
    <div style="flex: 1;">
      <div style="font-weight: 600; margin-bottom: 4px; color: #1E3A8A;">
        <svg style="display: inline-block; width: 14px; height: 14px; margin-right: 4px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M5 12h14"/>
          <path d="M12 5l7 7-7 7"/>
        </svg>
        Edge direction
      </div>
      <div style="font-size: 12px; color: #3B82F6;">
        → Citation | — Collaboration/Affiliation
      </div>
    </div>
    <div style="border-left: 1px solid #93C5FD; margin: 0 8px;"></div>
    <div style="flex: 1;">
      <div style="font-weight: 600; margin-bottom: 4px; color: #1E3A8A;">
        <svg style="display: inline-block; width: 14px; height: 14px; margin-right: 4px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M3 6h18M7 12h10M11 18h2"/>
        </svg>
        Filters
      </div>
      <div style="font-size: 12px; color: #3B82F6;">
        Click a category to show/hide its nodes
      </div>
    </div>
  </div>
</div>
"""

# Recenter button HTML
RECENTER_BUTTON_HTML = """
<button id="recenter-btn" style="
    position: fixed;
    top: 66px;
    right: 20px;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    font-family: Arial, sans-serif;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
    z-index: 9999;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 8px;
" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(59, 130, 246, 0.5)';"
   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 8px rgba(59, 130, 246, 0.4)';"
   onclick="recenterGraph()">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
    <circle cx="12" cy="12" r="10"/>
    <circle cx="12" cy="12" r="3"/>
    <line x1="12" y1="2" x2="12" y2="6"/>
    <line x1="12" y1="18" x2="12" y2="22"/>
    <line x1="2" y1="12" x2="6" y2="12"/>
    <line x1="18" y1="12" x2="22" y2="12"/>
  </svg>
  <span>Recentrer</span>
</button>
"""

# Legend HTML template (simplified - just colors)
LEGEND_HTML = """
<div id="legend" style="
    position: fixed;
    top: 120px;
    right: 20px;
    background: #ffffff;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 14px 16px;
    font-family: Arial, sans-serif;
    font-size: 13px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    z-index: 9999;
    max-width: 200px;
">
  <div style="font-weight: bold; margin-bottom: 10px;">Legend</div>
  <div style="margin-bottom: 6px;">
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#2D7FF9;margin-right:8px;"></span>
    Person (Founder, KOLs)
  </div>
  <div style="margin-bottom: 6px;">
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#F39C12;margin-right:8px;"></span>
    Corporate
  </div>
  <div style="margin-bottom: 6px;">
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#9B59B6;margin-right:8px;"></span>
    Institution
  </div>
  <div style="margin-bottom: 6px;">
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#34495E;margin-right:8px;"></span>
    Patent
  </div>
  <div style="margin-bottom: 6px;">
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#27AE60;margin-right:8px;"></span>
    Publication
  </div>

</div>
"""

# Filters panel HTML template (will be populated with JavaScript)
FILTERS_PANEL_HTML = """
<div id="custom-tooltip"></div>
<div id="filters-panel">

  <!-- Corporates -->
  <div class="filter-group" id="group-corporates">
    <span class="info-icon">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="8.5"/><line x1="10" y1="9" x2="10" y2="14" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
      <span class="info-tooltip">Entreprises ayant cité des publications ou brevets du chercheur.<br><br>Cliquer sur un nœud corporate dans le graphe dévoile le chemin de connexion et les raisons du lien.</span>
    </span>
    <button class="group-btn" onclick="toggleDropdown('corporates')">
      <span class="dot" style="background:#F39C12;"></span>
      Corporates <span class="badge" id="corporates-count">0</span>
      <span class="chevron">▾</span>
    </button>
    <div class="dropdown" id="dropdown-corporates" style="min-width:260px;">
      <div class="dd-search">
        <input type="text" id="corporates-search" placeholder="Rechercher un corporate…" oninput="filterCorporatesList(this.value)">
      </div>
      <div class="dd-actions">
        <button onclick="selectAllCorporates()">All</button>
        <button onclick="deselectAllCorporates()">None</button>
        <button id="btn-direct-corporates" onclick="toggleDirectFilter('corporates')" style="margin-left:auto;background:#f8fafc;color:#4a5568;border:1px solid #e2e8f0;border-radius:6px;padding:3px 10px;font-size:11px;font-weight:500;cursor:pointer;letter-spacing:0.03em;">Directs</button>
      </div>
      <div id="corporates-list" class="items-list"></div>
      <div style="padding:7px 12px 6px;border-top:1px solid #e2e8f0;font-size:11.5px;color:#475569;line-height:1.4;">
        Activez un toggle ou cliquez directement sur un nœud corporate dans le graphe pour voir les raisons de la connexion.
      </div>
    </div>
  </div>

  <!-- Institutions -->
  <div class="filter-group" id="group-institutions">
    <span class="info-icon">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="8.5"/><line x1="10" y1="9" x2="10" y2="14" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
      <span class="info-tooltip">Établissements académiques affiliés au chercheur ou à ses co-auteurs.<br><br>Au survol : met en évidence les liens d'affiliation.</span>
    </span>
    <button class="group-btn" onclick="toggleDropdown('institutions')">
      <span class="dot" style="background:#9B59B6;"></span>
      Institutions <span class="badge" id="institutions-count">0</span>
      <span class="chevron">▾</span>
    </button>
    <div class="dropdown" id="dropdown-institutions" style="min-width:260px;">
      <div class="dd-search">
        <input type="text" id="institutions-search" placeholder="Rechercher une institution…" oninput="filterInstitutionsList(this.value)">
      </div>
      <div class="dd-actions">
        <button onclick="selectAllInstitutions()">All</button>
        <button onclick="deselectAllInstitutions()">None</button>
        <button id="btn-direct-institutions" onclick="toggleDirectFilter('institutions')" style="margin-left:auto;background:#f8fafc;color:#4a5568;border:1px solid #e2e8f0;border-radius:6px;padding:3px 10px;font-size:11px;font-weight:500;cursor:pointer;letter-spacing:0.03em;">Directs</button>
      </div>
      <div id="institutions-list" class="items-list"></div>
    </div>
  </div>

  <!-- Patents -->
  <div class="filter-group" id="group-patents">
    <span class="info-icon">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="8.5"/><line x1="10" y1="9" x2="10" y2="14" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
      <span class="info-tooltip">Brevets déposés par le chercheur ou ses co-inventeurs.<br><br>Au survol : affiche les co-inventeurs et l'entreprise déposante.</span>
    </span>
    <button class="group-btn" onclick="toggleDropdown('patents')">
      <span class="dot" style="background:#34495E;"></span>
      Patents <span class="badge" id="patents-count">0</span>
      <span class="chevron">▾</span>
    </button>
    <div class="dropdown" id="dropdown-patents">
      <div class="dd-actions">
        <button onclick="selectAllPatents()">All</button>
        <button onclick="deselectAllPatents()">None</button>
      </div>
      <div id="patents-list" class="items-list"></div>
    </div>
  </div>

  <!-- Publications -->
  <div class="filter-group" id="group-publications">
    <span class="info-icon">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="8.5"/><line x1="10" y1="9" x2="10" y2="14" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
      <span class="info-tooltip">Articles scientifiques publiés par le chercheur et ses co-auteurs.<br><br>Au survol : affiche le titre complet de la publication.</span>
    </span>
    <button class="group-btn" onclick="toggleDropdown('publications')">
      <span class="dot" style="background:#27AE60;"></span>
      Publications <span class="badge" id="publications-count">0</span>
      <span class="chevron">▾</span>
    </button>
    <div class="dropdown" id="dropdown-publications" style="min-width:260px;">
      <div class="dd-search">
        <input type="text" id="publications-search" placeholder="Rechercher par titre, mot-clé…" oninput="filterPublicationsList(this.value)">
      </div>
      <div class="dd-actions">
        <button onclick="selectAllPublications()">All</button>
        <button onclick="deselectAllPublications()">None</button>
      </div>
      <div id="publications-list" class="items-list"></div>
    </div>
  </div>

  <!-- Co-auteurs -->
  <div class="filter-group" id="group-coauthors">
    <span class="info-icon">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="8.5"/><line x1="10" y1="9" x2="10" y2="14" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>
      <span class="info-tooltip">Co-auteurs du chercheur, triés par nombre de collaborations.<br><br>Limité aux 50 co-auteurs les plus fréquents si le chercheur en a davantage.<br><br>Utilisez la barre de recherche pour filtrer par nom.</span>
    </span>
    <button class="group-btn" onclick="toggleDropdown('coauthors')">
      <span class="dot" style="background:#2D7FF9;"></span>
      Co-auteurs <span class="badge" id="coauthors-count">0</span>
      <span class="chevron">▾</span>
    </button>
    <div class="dropdown" id="dropdown-coauthors" style="min-width:260px;">
      <div class="dd-search">
        <input type="text" id="coauthors-search" placeholder="Rechercher un co-auteur…" oninput="filterCoauthorsList(this.value)">
      </div>
      <div class="dd-actions">
        <button onclick="selectAllCoauthors()">All</button>
        <button onclick="deselectAllCoauthors()">None</button>
      </div>
      <div id="coauthors-list" class="items-list"></div>
    </div>
  </div>

  <!-- Stats -->
  <div id="filter-stats">
    <span id="visible-nodes-count">0</span> nodes &nbsp;·&nbsp; <span id="visible-edges-count">0</span> edges
  </div>

  <!-- Zoom controls -->
  <div id="zoom-controls">
    <button class="zoom-btn" onclick="zoomGraph(-1)" title="Zoom out">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="7"/>
        <line x1="8" y1="11" x2="14" y2="11"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    </button>
    <button class="zoom-btn" onclick="zoomGraph(1)" title="Zoom in">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="7"/>
        <line x1="11" y1="8" x2="11" y2="14"/>
        <line x1="8" y1="11" x2="14" y2="11"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    </button>
  </div>

</div>

<style>
  body {
    padding-top: 62px;
  }

  /* ── Horizontal filter bar ── */
  #filters-panel {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 62px;
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    display: flex;
    flex-direction: row;
    align-items: center;
    padding: 0 16px;
    gap: 6px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    z-index: 9999;
  }

  /* ── Each category group ── */
  .filter-group {
    position: relative;
  }

  .group-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background: white;
    border: 1.5px solid #d1d5db;
    border-radius: 7px;
    padding: 7px 14px 7px 12px;
    font-size: 14px;
    font-weight: 600;
    color: #374151;
    cursor: pointer;
    white-space: nowrap;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  }

  .group-btn:hover {
    background: #e5e7eb;
    border-color: #6b7280;
    color: #111827;
    box-shadow: 0 2px 6px rgba(0,0,0,0.13);
  }

  .group-btn.active {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #1d4ed8;
    box-shadow: 0 1px 4px rgba(59,130,246,0.18);
  }

  .group-btn.empty {
    opacity: 0.4;
    cursor: not-allowed;
    pointer-events: none;
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .badge {
    background: #f1f5f9;
    color: #64748b;
    border-radius: 5px;
    padding: 1px 7px;
    font-size: 12px;
    font-weight: 700;
    border: 1px solid #e2e8f0;
  }

  .group-btn.active .badge {
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #bfdbfe;
  }

  .chevron {
    font-size: 16px;
    color: #6b7280;
    transition: transform 0.2s;
    margin-left: 2px;
    line-height: 1;
  }

  .group-btn.active .chevron {
    transform: rotate(180deg);
  }

  /* ── Info icon + tooltip ── */
  .info-icon {
    position: absolute;
    top: -7px;
    left: -7px;
    width: 16px;
    height: 16px;
    color: #9ca3af;
    cursor: default;
    z-index: 10;
    transition: color 0.15s;
  }

  .info-icon svg {
    width: 100%;
    height: 100%;
    display: block;
    background: white;
    border-radius: 50%;
  }

  .info-icon:hover {
    color: #3b82f6;
  }

  .info-icon .info-tooltip {
    display: none;
    position: absolute;
    top: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    color: #f1f5f9;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.5;
    padding: 8px 12px;
    border-radius: 8px;
    white-space: normal;
    width: 220px;
    z-index: 99999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    pointer-events: none;
  }

  .info-icon .info-tooltip::before {
    content: '';
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-bottom-color: #1e293b;
  }

  .info-icon:hover .info-tooltip {
    display: block;
  }

  /* Corporates est tout à gauche — aligner le tooltip à gauche pour éviter le débordement */
  #group-corporates .info-tooltip {
    left: 0;
    transform: none;
  }

  #group-corporates .info-tooltip::before {
    left: 8px;
    transform: none;
  }

  /* ── Dropdown panel ── */
  .dropdown {
    display: none;
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    min-width: 220px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    z-index: 10000;
    padding: 8px 0;
  }

  .dropdown.open {
    display: block;
  }

  .dd-actions {
    display: flex;
    gap: 6px;
    padding: 4px 12px 8px;
    border-bottom: 1px solid #f1f5f9;
  }

  .dd-actions button {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
    color: #4a5568;
    cursor: pointer;
  }

  .dd-actions button:hover {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #1d4ed8;
  }

  .items-list {
    max-height: 280px;
    overflow-y: auto;
    padding: 4px 0;
  }

  .items-list::-webkit-scrollbar {
    width: 5px;
  }

  .items-list::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
  }

  /* ── Search input inside dropdown ── */
  .dd-search {
    padding: 8px 10px 4px;
  }

  .dd-search input {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    color: #374151;
    outline: none;
    background: #f9fafb;
  }

  .dd-search input:focus {
    border-color: #3b82f6;
    background: white;
  }

  /* ── Filter items inside dropdown ── */
  .filter-item {
    display: flex;
    align-items: flex-start;
    padding: 6px 12px;
    margin: 0;
    border-radius: 0;
    transition: background 0.12s ease;
  }

  .filter-item:hover {
    background: #f8fafc;
  }

  .filter-item input[type="checkbox"] {
    margin: 2px 10px 0 0;
    width: 15px;
    height: 15px;
    cursor: pointer;
    accent-color: #3b82f6;
    flex-shrink: 0;
  }

  .filter-item label {
    cursor: pointer;
    flex: 1;
    line-height: 1.4;
    color: #4a5568;
    font-size: 12.5px;
  }

  .filter-item:hover label {
    color: #1e293b;
  }

  /* ── Publication items ── */
  .publication-item {
    margin: 0;
  }

  .publication-title {
    cursor: pointer;
    display: flex;
    align-items: flex-start;
    padding: 6px 12px;
    transition: background 0.12s ease;
  }

  .publication-title:hover {
    background: #f8fafc;
  }

  .publication-title input[type="checkbox"] {
    margin: 2px 10px 0 0;
    width: 15px;
    height: 15px;
    cursor: pointer;
    accent-color: #3b82f6;
    flex-shrink: 0;
  }

  .expand-icon {
    margin-right: 6px;
    font-size: 11px;
    color: #3b82f6;
    user-select: none;
    margin-top: 2px;
    flex-shrink: 0;
    transition: transform 0.2s, color 0.15s;
  }

  .publication-title:hover .expand-icon {
    color: #1d4ed8;
  }

  .publication-title.open .expand-icon {
    transform: rotate(90deg);
  }

  .pub-title-text {
    flex: 1;
    line-height: 1.4;
    color: #4a5568;
    font-size: 12.5px;
  }

  .pub-title-text::after {
    content: ' — co-auteurs';
    font-size: 10.5px;
    color: #3b82f6;
    font-style: italic;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .publication-title:hover .pub-title-text::after {
    opacity: 1;
  }

  .publication-title:hover .pub-title-text {
    color: #1e293b;
  }

  .coauthors-list {
    margin-left: 38px;
    padding: 4px 12px 4px 0;
    display: none;
  }

  .coauthors-list.expanded {
    display: block;
  }

  .coauthors-list > div:first-child {
    font-weight: 600;
    font-size: 11px;
    color: #718096;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .coauthor-item {
    padding: 3px 8px;
    margin: 1px 0;
    cursor: pointer;
    color: #718096;
    font-size: 11.5px;
    border-radius: 4px;
    transition: all 0.12s ease;
  }

  .coauthor-item:hover {
    background: #eff6ff;
    color: #3b82f6;
    padding-left: 12px;
  }

  /* ── Toggle switches (corporates) ── */
  .toggle-item {
    display: flex;
    align-items: center;
    padding: 6px 12px;
    transition: background 0.12s ease;
  }

  .toggle-item:hover {
    background: #f8fafc;
  }

  .toggle-switch {
    position: relative;
    display: inline-block;
    width: 36px;
    height: 20px;
    margin-right: 10px;
    flex-shrink: 0;
  }

  .toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #dbeafe;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 20px;
  }

  .toggle-slider:before {
    position: absolute;
    content: "";
    height: 14px;
    width: 14px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.25s;
    border-radius: 50%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }

  input:checked + .toggle-slider {
    background: linear-gradient(135deg, #14B8A6, #0D9488);
    box-shadow: 0 2px 8px rgba(20, 184, 166, 0.3);
  }

  input:checked + .toggle-slider:before {
    transform: translateX(16px);
    background: white;
  }

  .toggle-label {
    cursor: pointer;
    flex: 1;
    line-height: 1.4;
    color: #4a5568;
    font-size: 12.5px;
  }

  .toggle-item:hover .toggle-label {
    color: #1e293b;
  }

  /* ── Zoom controls ── */
  #zoom-controls {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: 12px;
    margin-right: 12px;
    flex-shrink: 0;
  }

  .zoom-btn {
    width: 32px;
    height: 32px;
    border: 1.5px solid #d1d5db;
    border-radius: 6px;
    background: white;
    color: #374151;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    transition: background 0.15s, border-color 0.15s;
    padding: 0;
  }

  .zoom-btn:hover {
    background: #e5e7eb;
    border-color: #6b7280;
  }

  /* ── Stats counter (right side) ── */
  #filter-stats {
    margin-left: auto;
    font-size: 13px;
    color: #64748b;
    white-space: nowrap;
    padding-left: 12px;
  }

  #filter-stats span {
    font-weight: 700;
    color: #1e293b;
    font-size: 14px;
  }
</style>
"""


def _sanitize_connections(connections: list) -> list:
    """Convert non-JSON-serializable values (e.g. datetime.date) in connections to strings."""
    import datetime

    def _safe(v: Any) -> Any:
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: _safe(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_safe(item) for item in v]
        return v

    return [_safe(c) for c in (connections or [])]


def _safe_url(url: Any) -> str:
    """Only http(s) links reach an href: the URLs come from external APIs."""
    url = str(url or "").strip()
    return _esc(url) if url.lower().startswith(("http://", "https://")) else ""


def _js_literal(value: Any) -> str:
    """JSON safe to inline in a <script>: '</script>' in a title must not end it."""
    return (_json.dumps(value, ensure_ascii=False, default=str)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _build_js_graph_data(graph: Dict[str, Any]) -> str:
    """
    Build JavaScript-compatible graph data for filters panel.

    Extracts nodes grouped by type with relevant metadata for filtering.

    Args:
        graph: Graph dict with keys: meta, nodes, edges.

    Returns:
        JSON string with nodes grouped by type.
    """
    import json

    corporates = []
    institutions = []
    patents = []
    publications = []
    persons = []

    seed_id = graph.get("meta", {}).get("seed_person_id", "")

    # Compute direct node IDs: nodes linked to seed with no person intermediary
    edges = graph.get("edges", [])
    # 1) Seed's own patent IDs (has_patent edges)
    seed_patent_ids = {
        e.get("target") for e in edges
        if e.get("source") == seed_id and e.get("type") == "has_patent"
    }
    # 2) Directly from seed via any edge
    direct_ids: set = {e.get("target") for e in edges if e.get("source") == seed_id}
    # 3) Corporate cites a patent that belongs to seed (not a co-author)
    for e in edges:
        if e.get("type") == "cites_patent" and e.get("target") in seed_patent_ids:
            direct_ids.add(e.get("source"))

    for node in graph.get("nodes", []):
        node_type = node.get("type")
        node_id = node.get("id")
        label = node.get("label", "")
        attrs = node.get("attributes", {})

        if node_type == "person" and node_id != seed_id:
            collab_count = attrs.get("collaborations_with_seed") or 0
            persons.append({
                "id": node_id,
                "label": label,
                "collaborations": collab_count
            })

        if node_type == "corporate":
            corporates.append({
                "id": node_id,
                "label": _title_case_corporate(label),
                "type": "corporate",
                "country": attrs.get("country") or "Unknown",
                "connections": _sanitize_connections(attrs.get("connections", [])),
                "direct": node_id in direct_ids,
            })
        elif node_type == "institution":
            institutions.append({
                "id": node_id,
                "label": label,
                "type": "institution",
                "connections": _sanitize_connections(attrs.get("connections", [])),
                "direct": node_id in direct_ids,
            })
        elif node_type == "patent":
            patent_id = attrs.get("patent_id", "")
            # Clean patent ID (remove "patent/" prefix)
            clean_patent_id = patent_id.replace("patent/", "").replace("/en", "") if patent_id else ""
            patent_title = attrs.get("title", "")  # Full patent title from attributes
            patents.append({
                "id": node_id,
                "label": f"{clean_patent_id}: {label}" if clean_patent_id else label,
                "type": "patent",
                "title": patent_title  # Include full title for display
            })
        elif node_type == "publication":
            year = attrs.get("year", "")
            display_label = label

            # Get co-authors from publication node attributes (full list).
            # Using attributes.authors is faster than edge traversal and works for
            # OpenAlex where not all authors have graph nodes.
            coauthors = [
                {"id": f"person:{slug(name)}", "name": name}
                for name in (attrs.get("authors") or [])
                if name
            ]

            publications.append({
                "id": node_id,
                "label": display_label,
                "year": year,
                "type": "publication",
                "coauthors": coauthors
            })

    data = {
        "corporates": sorted(corporates, key=lambda x: x["label"]),
        "institutions": sorted(institutions, key=lambda x: x["label"]),
        "patents": patents,  # Keep original order (usually by relevance)
        "publications": sorted(publications, key=lambda x: x.get("year") or "", reverse=True),
        "persons": sorted(persons, key=lambda x: x["collaborations"], reverse=True)
    }

    try:
        return _js_literal(data)
    except (TypeError, ValueError) as e:
        logger.warning(f"Graph data serialization failed ({e}), retrying with string fallback")
        return _js_literal(data)


def render_graph_html(
    graph: Dict[str, Any],
    out_html: str = "network_graph.html"
) -> None:
    """
    Render an interactive HTML visualization of the graph.

    Creates a pyvis network visualization with:
    - Color-coded nodes by type
    - Node sizes based on betweenness centrality
    - Tooltips with node/edge details
    - Legend overlay

    Args:
        graph: Graph dict with keys: meta, nodes, edges.
        out_html: Output HTML file path (default: "network_graph.html").

    Example:
        >>> render_graph_html(graph, "my_network.html")
        >>> # Open my_network.html in browser
    """
    seed_id = graph["meta"]["seed_person_id"]

    # Build NetworkX graph
    G = nx.DiGraph()

    # Node type lookup
    node_type_lookup = {n["id"]: n.get("type", "unknown") for n in graph.get("nodes", [])}

    # Add nodes
    for n in graph["nodes"]:
        nid = n["id"]
        ntype = n["type"]
        label = n.get("label", nid)
        original_label = label  # keep original title for tooltip

        # Apply title case to corporate names for professional display
        if ntype == "corporate":
            label = _title_case_corporate(label)

        # Shorten labels
        if ntype == "patent":
            label = (n.get("attributes", {}).get("patent_id") or nid)
            label = label.replace("patent/", "").replace("/en", "").replace("patent:", "")
        elif ntype == "publication":
            label = " "  # space prevents vis.js from falling back to node ID
        elif ntype in ("corporate", "institution"):
            pass  # keep full label

        color = NODE_COLORS.get(ntype, "#95A5A6")

        # ── Build tooltip HTML ──────────────────────────────────────────────
        attrs = n.get("attributes") or {}
        links = n.get("links") or {}
        scholar_url = links.get("scholar_profile", "") or links.get("scholar_url", "")

        # Libellés, titres, noms viennent d'APIs externes : tout est échappé ici
        def _badge(text, cls):
            return f'<span class="tt-badge tt-badge-{_esc(str(cls))}">{_esc(str(text))}</span>'

        def _row(key, val):
            return f'<div class="tt-row"><span class="tt-key">{_esc(str(key))}</span><span class="tt-val">{_esc(str(val))}</span></div>'

        def _cta(text, url):
            href = _safe_url(url)
            return f'<a class="tt-cta" href="{href}" target="_blank">{_esc(str(text))} &rarr;</a>' if href else ""

        if ntype == "person":
            is_seed = (nid == seed_id)
            badge = _badge("Chercheur analysé", "person") if is_seed else _badge("Co-auteur", "person")
            h_index = attrs.get("h_index")
            collab_count = attrs.get("collaborations_with_seed")
            last_year = attrs.get("last_shared_year")

            rows = []
            if h_index is not None:
                rows.append(_row("H-index", str(h_index)))
            if collab_count is not None and collab_count > 0 and not is_seed:
                collab_str = f"{collab_count} publication{'s' if collab_count > 1 else ''} en commun"
                if last_year:
                    collab_str += f" · dernière en {last_year}"
                rows.append(_row("Collaborations", collab_str))

            cta = _cta("Voir le profil OpenAlex", scholar_url) if scholar_url else ""

            tooltip_html = f'<div class="tt-header"><span class="tt-name">{_esc(str(label))}</span>{badge}</div>'
            if rows:
                tooltip_html += f'<div class="tt-body">{"".join(rows)}</div>'
            if cta:
                tooltip_html += cta
            if not rows and not cta:
                tooltip_html += '<div class="tt-body"><span class="tt-muted">Profil non trouvé</span></div>'
            if not is_seed and scholar_url:
                tooltip_html += '<div class="tt-hint">Cliquez pour ouvrir le profil</div>'

        elif ntype == "publication":
            year = attrs.get("year", "")
            source = attrs.get("source", "")
            cited_by = attrs.get("cited_by")
            authors = attrs.get("authors") or []
            pub_url = links.get("scholar_url", "")

            display_title = original_label[:75] + "…" if len(original_label) > 75 else original_label

            rows = []
            if year:
                rows.append(_row("Année", str(year)))
            if source:
                rows.append(_row("Revue", source[:50]))
            if cited_by is not None:
                rows.append(_row("Citations", str(cited_by)))
            if authors:
                authors_short = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_short += f" +{len(authors) - 3}"
                rows.append(_row("Co-auteurs", authors_short))

            cta = _cta("Lire l'article", pub_url) if pub_url else ""

            tooltip_html = f'<div class="tt-header"><span class="tt-name tt-name-sm">{_esc(str(display_title))}</span>{_badge("Publication", "publication")}</div>'
            if rows:
                tooltip_html += f'<div class="tt-body">{"".join(rows)}</div>'
            if cta:
                tooltip_html += cta
                tooltip_html += '<div class="tt-hint">Cliquez pour ouvrir l\'article</div>'

        elif ntype == "patent":
            pub_date = attrs.get("publication_date", "")
            assignee = attrs.get("current_assignee", "")
            co_inventors = attrs.get("co_inventors") or []
            cited_by = attrs.get("cited_by")
            patents_link = links.get("patents_url", "")

            display_title = label[:75] + "…" if len(label) > 75 else label

            rows = []
            if assignee:
                rows.append(_row("Déposant", assignee[:45]))
            if pub_date:
                rows.append(_row("Publié le", pub_date))
            if co_inventors:
                inv_str = ", ".join(co_inventors[:3])
                if len(co_inventors) > 3:
                    inv_str += f" +{len(co_inventors) - 3}"
                rows.append(_row("Co-inventeurs", inv_str))
            if cited_by is not None:
                rows.append(_row("Citations", f"{cited_by} brevets"))

            cta = _cta("Voir sur Google Patents", patents_link) if patents_link else ""

            tooltip_html = f'<div class="tt-header"><span class="tt-name tt-name-sm">{_esc(str(display_title))}</span>{_badge("Brevet", "patent")}</div>'
            if rows:
                tooltip_html += f'<div class="tt-body">{"".join(rows)}</div>'
            if cta:
                tooltip_html += cta
                tooltip_html += '<div class="tt-hint">Cliquez pour ouvrir le brevet</div>'

        elif ntype == "corporate":
            connections = attrs.get("connections", [])
            logger.debug(f"Corporate node {nid}: attrs keys = {list(attrs.keys())}")
            logger.debug(f"Corporate node {nid}: connections = {len(connections)}")

            rows_html = ""
            if connections:
                for conn in connections[:5]:
                    scientist_name = conn.get("scientist_name", "")
                    aff_type_raw = conn.get("affiliation_type", "")
                    _aff_labels = {
                        "patent_inventor": "Co-inventeur",
                        "co_author": "Co-auteur",
                        "clinical_trial": "Essai clinique",
                        "transparence_sante": "Transparence Santé",
                        "employment": "Affiliation",
                    }
                    aff_type = _aff_labels.get(aff_type_raw, aff_type_raw)
                    if scientist_name:
                        rows_html += (
                            f'<div class="tt-conn-row">'
                            f'<span class="tt-conn-name">{_esc(str(scientist_name))}</span>'
                            f'<span class="tt-conn-type">{_esc(str(aff_type))}</span>'
                            f'</div>'
                        )
                if len(connections) > 5:
                    rows_html += f'<div class="tt-muted">+{len(connections) - 5} autre(s) connexion(s)</div>'

            tooltip_html = f'<div class="tt-header"><span class="tt-name">{_esc(str(label))}</span>{_badge("Corporate", "corporate")}</div>'
            if rows_html:
                conn_label = f'Connexions ({len(connections)})'
                tooltip_html += f'<div class="tt-body"><div class="tt-conn-label">{conn_label}</div>{rows_html}</div>'
            tooltip_html += '<div class="tt-hint">Cliquez pour explorer les chemins de connexion</div>'

        elif ntype == "institution":
            openalex_url = links.get("openalex_url", "") or links.get("scholar_profile", "")
            is_current = attrs.get("is_current", False)
            badge_label = "Institution actuelle" if is_current else "Institution"
            tooltip_html = f'<div class="tt-header"><span class="tt-name">{_esc(str(label))}</span>{_badge(badge_label, "institution")}</div>'
            tooltip_html += '<div class="tt-body"><div class="tt-muted" style="font-size:11px;color:#6B7280;margin-bottom:2px;">Source\u00a0: OpenAlex</div></div>'
            if openalex_url:
                tooltip_html += _cta("Voir sur OpenAlex", openalex_url)
                tooltip_html += '<div class="tt-hint">Cliquez pour ouvrir la fiche</div>'

        else:
            badge_label = ntype.capitalize()
            tooltip_html = f'<div class="tt-header"><span class="tt-name">{_esc(str(label))}</span>{_badge(badge_label, ntype)}</div>'
            for lk, url in links.items():
                if url:
                    tooltip_html += _cta(lk, url)

        # Store URLs in node data for click event
        scholar_profile_url = links.get("scholar_profile", "") or links.get("scholar_url", "")
        patents_url = links.get("patents_url", "")
        # Page publique ouverte au clic quand le graphe est affiché seul (CLI)
        open_url = {
            "person": scholar_profile_url,
            "publication": links.get("scholar_url", ""),
            "patent": patents_url,
            "institution": links.get("openalex_url", "") or links.get("scholar_profile", ""),
        }.get(ntype, "")

        G.add_node(
            nid,
            label=label,
            tooltip_html=tooltip_html,
            color=color,
            node_type=ntype,
            scholar_url=scholar_profile_url,
            patents_url=patents_url,
            open_url=open_url,
        )

    # Add edges
    for e in graph["edges"]:
        s, t = e["source"], e["target"]
        etype = e["type"]
        w = e.get("weight", 1)

        # Build evidence links
        ev_html = ""
        ev = e.get("evidence") or []
        if ev:
            items = [
                f'<a href="{_safe_url(x.get("url"))}" target="_blank">{_esc(str(x.get("label", "source")))}</a>'
                for x in ev[:3] if _safe_url(x.get("url"))
            ]
            if items:
                ev_html = "<br/>" + " | ".join(items)

        G.add_edge(s, t, value=w, title=None, etype=etype, weight=w)

    # Calculate centrality for node sizing
    # degree_centrality (O(V)) for large graphs, betweenness (O(V*E)) only for small ones
    # — visually equivalent but 10-30x faster on constrained CPU (e.g. Clever Cloud)
    edge_count = G.number_of_edges()
    if edge_count > 200:
        btw = nx.degree_centrality(G)
    else:
        btw = nx.betweenness_centrality(G)

    # Freeze physics after stabilisation for large graphs (>550 edges)
    freeze_physics = edge_count > 550
    if freeze_physics:
        logger.info(f"Large graph detected ({edge_count} edges) — physics will freeze after stabilisation")

    # Create pyvis network
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#ffffff",
        directed=False
    )

    _physics_options = (
        """
        "physics": {
          "solver": "barnesHut",
          "barnesHut": {
            "gravitationalConstant": -4000,
            "centralGravity": 0.3,
            "springLength": 200,
            "springConstant": 0.02,
            "damping": 0.6,
            "avoidOverlap": 1
          },
          "minVelocity": 0.1,
          "stabilization": {
            "enabled": true,
            "iterations": 3000,
            "updateInterval": 50,
            "fit": true
          }
        },"""
        if freeze_physics else
        """
        "physics": {
          "solver": "barnesHut",
          "barnesHut": {
            "gravitationalConstant": -3000,
            "centralGravity": 0.8,
            "springLength": 170,
            "springConstant": 0.04,
            "damping": 0.35,
            "avoidOverlap": 1
          },
          "minVelocity": 0.5,
          "stabilization": {
            "enabled": true,
            "iterations": 1500,
            "updateInterval": 25
          }
        },"""
    )

    net.set_options("""
    var options = {
      "nodes": {
        "shape": "dot",
        "font": {"size": 12},
        "scaling": {"min": 12, "max": 55}
      },
      "edges": {
        "smooth": false,
        "color": {"inherit": true},
        "width": 1
      },""" + _physics_options + """
      "interaction": {
        "hover": true,
        "tooltipDelay": 120,
        "hideEdgesOnDrag": true,
        "zoomView": true,
        "zoomSpeed": 0.3,
        "dragView": true,
        "navigationButtons": false,
        "keyboard": {
          "enabled": false
        }
      }
    }
    """)

    # Add nodes to pyvis
    for nid, data in G.nodes(data=True):
        ntype = node_type_lookup.get(nid, "unknown")
        base_size = 16
        if ntype == "person":
            size = base_size + int(80 * btw.get(nid, 0.0))
        elif ntype in ("corporate", "institution"):
            size = base_size + 10 + int(55 * btw.get(nid, 0.0))
        else:
            size = base_size + int(30 * btw.get(nid, 0.0))

        if nid == seed_id:
            net.add_node(nid, **data, size=size + 15, fixed=True, x=0, y=0)
        else:
            net.add_node(nid, **data, size=size)

    # Add edges to pyvis
    for u, v, edata in G.edges(data=True):
        etype = edata.get("etype", "")
        w = edata.get("weight", edata.get("value", 1)) or 1

        arrows = "to" if etype == "cites_patent" else ""
        # Linear edge thickness: 1 + (co-publications * 0.4)
        # More visual difference between 3 and 10 co-pubs than logarithmic
        width = 1 + w * 0.4

        # Update tooltip verb
        if etype == "cites_patent":
            verb = "cites (forward)"
        else:
            verb = etype

        net.add_edge(u, v, value=w, width=width, title=None, etype=etype, arrows=arrows)

    # Write HTML
    net.write_html(out_html)

    # Inject legend, filters panel and JavaScript
    with open(out_html, "r", encoding="utf-8") as f:
        html = f.read()

    # Build graph data for JavaScript (nodes grouped by type)
    js_graph_data = _build_js_graph_data(graph)

    # JS snippet injected in stabilizationIterationsDone for large graphs
    freeze_js = (
        "network.setOptions({ physics: { enabled: false } });  // freeze: large graph"
        if freeze_physics else ""
    )

    # Add comprehensive JavaScript for filters, pathfinding and highlighting
    filters_javascript = f"""
<script type="text/javascript">
    // Graph data for filters
    const graphData = {js_graph_data};
    const seedNodeId = {_js_literal(graph['meta']['seed_person_id'])};
    let seedLabel = "";  // Will be set after network init

    // Les chaînes du graphe viennent d'APIs externes : échapper avant innerHTML
    function escHtml(s) {{
        return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {{
            return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];
        }});
    }}
    function safeHref(u) {{
        u = String(u || '').trim();
        return /^https?:\\/\\//i.test(u) ? escHtml(u) : '';
    }}

    // State management
    let highlightedCorporates = new Set();  // supports multi-corporate highlight
    let originalNodeColors = {{}};
    let originalEdgeColors = {{}};

    // Initialize filters panel on load
    document.addEventListener('DOMContentLoaded', function() {{
        populateFilters();
        storeOriginalColors();
        setupViewConstraints();
    }});

    // Zoom in/out buttons
    window.zoomGraph = function(direction) {{
        const currentScale = network.getScale();
        const factor = direction > 0 ? 1.3 : 0.77;
        const newScale = Math.min(3.0, Math.max(0.3, currentScale * factor));
        network.moveTo({{ scale: newScale, animation: {{ duration: 200, easingFunction: 'easeInOutQuad' }} }});
    }};

    // Setup zoom and pan constraints
    function setupViewConstraints() {{
        const MIN_ZOOM = 0.3;
        const MAX_ZOOM = 3.0;

        // Intercept wheel events to normalize trackpad sensitivity.
        // Trackpads emit many small deltaY values (< 50); mouse wheels emit large ones (~120).
        // We handle trackpad events manually with a gentle factor and block vis.js from
        // processing them, so two-finger scroll feels smooth instead of jumpy.
        const container = network.canvas.frame.canvas.parentElement;
        container.addEventListener('wheel', function(e) {{
            if (Math.abs(e.deltaY) < 50) {{
                // Trackpad — handle manually with reduced sensitivity
                e.preventDefault();
                e.stopImmediatePropagation();
                const scale = network.getScale();
                const factor = 1 - e.deltaY * 0.004;
                const newScale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale * factor));
                network.moveTo({{ scale: newScale }});
            }}
            // Mouse wheel (large deltaY) — let vis.js handle normally
        }}, {{ passive: false, capture: true }});

        // Clamp zoom limits for mouse wheel events handled by vis.js
        network.on("zoom", function(params) {{
            const scale = network.getScale();
            if (scale < MIN_ZOOM) {{
                network.moveTo({{scale: MIN_ZOOM}});
            }} else if (scale > MAX_ZOOM) {{
                network.moveTo({{scale: MAX_ZOOM}});
            }}
        }});

        // Store initial view position after stabilization
        // For large graphs (>{edge_count} edges): freeze physics so nodes stop moving
        network.once("stabilizationIterationsDone", function() {{
            window.initialViewPosition = network.getViewPosition();
            window.initialScale = network.getScale();
            {freeze_js}
        }});

        // Detect if user has moved too far from graph
        let checkViewInterval = setInterval(function() {{
            const position = network.getViewPosition();
            const scale = network.getScale();

            // Calculate distance from origin
            const distance = Math.sqrt(position.x * position.x + position.y * position.y);

            // If user is very far (more than 3000 units from center), show warning
            if (distance > 3000) {{
                showRecenterWarning();
            }} else {{
                hideRecenterWarning();
            }}
        }}, 1000);
    }}

    // Recenter graph to fit all nodes
    function recenterGraph() {{
        network.fit({{
            animation: {{
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }}
        }});
        hideRecenterWarning();
    }}

    // Show warning when user is too far
    function showRecenterWarning() {{
        let warning = document.getElementById('view-warning');
        if (!warning) {{
            warning = document.createElement('div');
            warning.id = 'view-warning';
            warning.style.cssText = `
                position: fixed;
                top: 150px;
                right: 230px;
                background: #FEF3C7;
                border: 2px solid #F59E0B;
                border-radius: 8px;
                padding: 12px 16px;
                font-family: Arial, sans-serif;
                font-size: 13px;
                color: #92400E;
                box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
                z-index: 9998;
                display: flex;
                align-items: center;
                gap: 8px;
                animation: slideIn 0.3s ease;
            `;
            warning.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                <span>You're far from the graph! Click "Recentrer" to go back.</span>
            `;
            document.body.appendChild(warning);
        }}
        warning.style.display = 'flex';
    }}

    // Hide warning
    function hideRecenterWarning() {{
        const warning = document.getElementById('view-warning');
        if (warning) {{
            warning.style.display = 'none';
        }}
    }}

    // Store original colors for reset
    function storeOriginalColors() {{
        nodes.forEach(function(node) {{
            originalNodeColors[node.id] = node.color;
        }});
        edges.forEach(function(edge) {{
            originalEdgeColors[edge.id] = edge.color || '#D1D5DB';  // subtle light gray
        }});

        // Set seedLabel from node data
        const seedNode = nodes.get(seedNodeId);
        if (seedNode) {{
            seedLabel = seedNode.label || '';
        }}
    }}

    // Populate filters panel with checkboxes
    function populateFilters() {{
        // Corporates (toggle switches, off by default)
        const corporatesList = document.getElementById('corporates-list');
        graphData.corporates.forEach(function(corp) {{
            corporatesList.appendChild(createCorporateToggle(corp));
        }});
        document.getElementById('corporates-count').textContent = graphData.corporates.length;
        if (graphData.corporates.length === 0) document.querySelector('#group-corporates .group-btn').classList.add('empty');

        // Institutions
        const institutionsList = document.getElementById('institutions-list');
        graphData.institutions.forEach(function(inst) {{
            institutionsList.appendChild(createFilterCheckbox(inst, 'institution'));
        }});
        document.getElementById('institutions-count').textContent = graphData.institutions.length;
        if (graphData.institutions.length === 0) document.querySelector('#group-institutions .group-btn').classList.add('empty');

        // Patents
        const patentsList = document.getElementById('patents-list');
        graphData.patents.forEach(function(patent) {{
            patentsList.appendChild(createFilterCheckbox(patent, 'patent'));
        }});
        document.getElementById('patents-count').textContent = graphData.patents.length;
        if (graphData.patents.length === 0) document.querySelector('#group-patents .group-btn').classList.add('empty');

        // Publications (masquées par défaut)
        const publicationsList = document.getElementById('publications-list');
        graphData.publications.forEach(function(pub) {{
            publicationsList.appendChild(createPublicationItem(pub));
            nodes.update({{id: pub.id, hidden: true}});
        }});
        document.getElementById('publications-count').textContent = graphData.publications.length;
        if (graphData.publications.length === 0) document.querySelector('#group-publications .group-btn').classList.add('empty');

        // Co-auteurs : visibles seulement s'ils sont reliés à un corporate ou une institution
        const corpInstIds = new Set(
            [...(graphData.corporates || []), ...(graphData.institutions || [])].map(function(n) {{ return n.id; }})
        );
        const linkedPersonIds = new Set();
        edges.forEach(function(edge) {{
            if (corpInstIds.has(edge.to))   linkedPersonIds.add(edge.from);
            if (corpInstIds.has(edge.from)) linkedPersonIds.add(edge.to);
        }});
        const coauthorsList = document.getElementById('coauthors-list');
        graphData.persons.forEach(function(person) {{
            const isLinked = linkedPersonIds.has(person.id);
            coauthorsList.appendChild(createCoauthorItem(person, isLinked));
            if (!isLinked) nodes.update({{id: person.id, hidden: true}});
        }});
        document.getElementById('coauthors-count').textContent = graphData.persons.length;
        if (graphData.persons.length === 0) document.querySelector('#group-coauthors .group-btn').classList.add('empty');

        updateStats();
    }}

    // Create toggle switch for corporates
    function createCorporateToggle(item) {{
        const div = document.createElement('div');
        div.className = 'toggle-item';
        div.dataset.nodeId = item.id;
        div.dataset.label = (item.label || '').toLowerCase();

        const toggleSwitch = document.createElement('label');
        toggleSwitch.className = 'toggle-switch';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = false; // Off by default
        checkbox.id = 'filter-' + item.id;
        checkbox.onchange = function() {{
            handleCorporateFilter(item.id, this.checked);
        }};

        const slider = document.createElement('span');
        slider.className = 'toggle-slider';

        toggleSwitch.appendChild(checkbox);
        toggleSwitch.appendChild(slider);

        const labelWrapper = document.createElement('span');
        labelWrapper.className = 'toggle-label';
        labelWrapper.style.cssText = 'display:flex;align-items:center;gap:6px;';
        labelWrapper.onclick = function() {{
            checkbox.checked = !checkbox.checked;
            handleCorporateFilter(item.id, checkbox.checked);
        }};

        const labelText = document.createElement('span');
        labelText.textContent = item.label;
        labelWrapper.appendChild(labelText);

        if (item.country && item.country.toUpperCase() === 'USA') {{
            const flag = document.createElement('img');
            flag.src = 'https://flagcdn.com/16x12/us.png';
            flag.width = 16;
            flag.height = 12;
            flag.alt = 'USA';
            flag.style.cssText = 'border-radius:2px;flex-shrink:0;box-shadow:0 0 0 1px rgba(0,0,0,0.12);';
            labelWrapper.appendChild(flag);
        }}

        div.appendChild(toggleSwitch);
        div.appendChild(labelWrapper);

        return div;
    }}

    // Create checkbox for institution/patent/publication
    function createFilterCheckbox(item, type, defaultChecked = true) {{
        const div = document.createElement('div');
        div.className = 'filter-item';
        div.dataset.nodeId = item.id;
        div.dataset.label = (item.label || '').toLowerCase();

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = defaultChecked;
        checkbox.id = 'filter-' + item.id;
        checkbox.onchange = function() {{
            handleNodeFilter(item.id, this.checked);
        }};

        const label = document.createElement('label');
        label.htmlFor = checkbox.id;
        label.textContent = item.label;
        label.style.fontSize = '12px';

        div.appendChild(checkbox);
        div.appendChild(label);

        return div;
    }}

    // Create publication item with expandable co-authors
    function createPublicationItem(pub) {{
        const div = document.createElement('div');
        div.className = 'publication-item';
        div.dataset.title = (pub.label || '').toLowerCase();

        // Publication checkbox and title
        const titleDiv = document.createElement('div');
        titleDiv.className = 'publication-title';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = false;
        checkbox.id = 'filter-' + pub.id;
        checkbox.style.marginRight = '6px';
        checkbox.style.marginTop = '2px';
        checkbox.onchange = function() {{
            handleNodeFilter(pub.id, this.checked);
        }};

        const expandIcon = document.createElement('span');
        expandIcon.className = 'expand-icon';
        expandIcon.textContent = '▶';
        expandIcon.onclick = function() {{
            toggleCoauthors(pub.id);
        }};

        const titleText = document.createElement('span');
        titleText.className = 'pub-title-text';
        titleText.textContent = pub.label + ' (' + (pub.year || 'N/A') + ')';
        titleText.style.fontSize = '12px';
        titleText.style.cursor = 'pointer';
        titleText.onclick = function() {{
            toggleCoauthors(pub.id);
        }};

        titleDiv.appendChild(checkbox);
        titleDiv.appendChild(expandIcon);
        titleDiv.appendChild(titleText);

        // Co-authors list (initially hidden)
        const coauthorsList = document.createElement('div');
        coauthorsList.className = 'coauthors-list';
        coauthorsList.id = 'coauthors-' + pub.id;

        if (pub.coauthors && pub.coauthors.length > 0) {{
            const header = document.createElement('div');
            header.style.fontWeight = 'bold';
            header.style.marginBottom = '4px';
            header.textContent = 'Co-authors (' + pub.coauthors.length + '):';
            coauthorsList.appendChild(header);

            pub.coauthors.forEach(function(author) {{
                const authorDiv = document.createElement('div');
                authorDiv.className = 'coauthor-item';
                authorDiv.textContent = '• ' + author.name;
                authorDiv.onclick = function() {{
                    highlightPerson(author.id);
                }};
                coauthorsList.appendChild(authorDiv);
            }});
        }} else {{
            coauthorsList.textContent = 'No co-authors data';
        }}

        div.appendChild(titleDiv);
        div.appendChild(coauthorsList);

        return div;
    }}

    // Toggle co-authors list visibility
    function toggleCoauthors(pubId) {{
        const list = document.getElementById('coauthors-' + pubId);
        const icon = list.previousElementSibling.querySelector('.expand-icon');

        const titleDiv = list.previousElementSibling;
        if (list.classList.contains('expanded')) {{
            list.classList.remove('expanded');
            titleDiv.classList.remove('open');
            icon.textContent = '▶';
        }} else {{
            list.classList.add('expanded');
            titleDiv.classList.add('open');
            icon.textContent = '▶';
        }}
    }}

    // Handle corporate filter with path highlighting
    function handleCorporateFilter(nodeId, checked) {{
        if (checked) {{
            highlightedCorporates.add(nodeId);
        }} else {{
            highlightedCorporates.delete(nodeId);
        }}

        if (highlightedCorporates.size === 0) {{
            resetHighlight();
        }} else {{
            highlightPathsToAllCorporates();
        }}
    }}

    // Handle generic node filter (show/hide)
    function handleNodeFilter(nodeId, checked) {{
        try {{
            const nodeData = nodes.get(nodeId);
            if (!nodeData) return;

            if (checked) {{
                // Show node
                nodes.update({{id: nodeId, hidden: false}});

                // Show connected edges
                const connectedEdges = network.getConnectedEdges(nodeId);
                connectedEdges.forEach(function(edgeId) {{
                    const edge = edges.get(edgeId);
                    if (edge) {{
                        const sourceNode = nodes.get(edge.from);
                        const targetNode = nodes.get(edge.to);
                        // Only show edge if both nodes are visible
                        if (sourceNode && targetNode && !sourceNode.hidden && !targetNode.hidden) {{
                            edges.update({{id: edgeId, hidden: false}});
                        }}
                    }}
                }});
            }} else {{
                // Hide node
                nodes.update({{id: nodeId, hidden: true}});

                // Hide connected edges
                const connectedEdges = network.getConnectedEdges(nodeId);
                connectedEdges.forEach(function(edgeId) {{
                    edges.update({{id: edgeId, hidden: true}});
                }});
            }}

            updateStats();
        }} catch (e) {{
            console.error('Error handling node filter:', e);
        }}
    }}

    // Highlight all paths from seed to ALL currently checked corporates
    function highlightPathsToAllCorporates() {{
        const nodesInPaths = new Set();
        const edgesInPaths = new Set();
        const allPathsPerCorporate = [];

        highlightedCorporates.forEach(function(corporateId) {{
            const paths = findAllPaths(seedNodeId, corporateId);
            if (paths.length === 0) return;

            allPathsPerCorporate.push({{ corporateId, paths }});

            paths.forEach(function(path) {{
                for (let i = 0; i < path.length; i++) {{
                    nodesInPaths.add(path[i]);
                }}
                for (let i = 0; i < path.length - 1; i++) {{
                    const nodeA = path[i], nodeB = path[i + 1];
                    network.getConnectedEdges(nodeA).forEach(function(edgeId) {{
                        const edge = edges.get(edgeId);
                        if (edge && ((edge.from === nodeA && edge.to === nodeB) ||
                                     (edge.to === nodeA && edge.from === nodeB))) {{
                            edgesInPaths.add(edgeId);
                        }}
                    }});
                }}
            }});
        }});

        if (nodesInPaths.size === 0) {{
            alert('No connection found between the researcher and the selected corporate(s).');
            return;
        }}

        // Batch all vis.js updates — one call per dataset instead of one per node/edge
        const nodeUpdates = [];
        nodes.forEach(function(node) {{
            if (nodesInPaths.has(node.id)) {{
                nodeUpdates.push({{
                    id: node.id, hidden: false, borderWidth: 3,
                    color: {{
                        background: originalNodeColors[node.id],
                        border: '#22C55E',
                        highlight: {{ background: originalNodeColors[node.id], border: '#22C55E' }}
                    }}
                }});
            }} else {{
                nodeUpdates.push({{ id: node.id, hidden: true }});
            }}
        }});
        nodes.update(nodeUpdates);

        const edgeUpdates = [];
        edges.forEach(function(edge) {{
            if (edgesInPaths.has(edge.id)) {{
                edgeUpdates.push({{
                    id: edge.id,
                    hidden: false,
                    color: {{color:'#14B8A6', highlight:'#0D9488'}},
                    width: 3.5,
                    shadow: {{enabled: true, color: 'rgba(20, 184, 166, 0.3)', size: 10, x: 0, y: 0}}
                }});
            }} else {{
                edgeUpdates.push({{ id: edge.id, hidden: true }});
            }}
        }});
        edges.update(edgeUpdates);

        displayMultiPathsInfo(allPathsPerCorporate);
        updateStats();
    }}

    // ── Configuration des types de connexion ──
    const CONN_CFG = {{
        'patent_assignee':    {{ label: 'Brevet assigné',          color: '#7C3AED', bg: '#EDE9FE' }},
        'patent_citation':    {{ label: 'Citation de brevet',       color: '#6D28D9', bg: '#F5F3FF' }},
        'patent_inventor':    {{ label: 'Co-inventeur',             color: '#4F46E5', bg: '#EEF2FF' }},
        'clinical_trials':    {{ label: 'Essai clinique',           color: '#0369A1', bg: '#E0F2FE' }},
        'transparence_sante': {{ label: 'Transparence Santé',       color: '#0D9488', bg: '#F0FDFA' }},
        'open_payments':      {{ label: 'Open Payments (US)',        color: '#B45309', bg: '#FEF3C7' }},
        'employment':         {{ label: 'Affiliation',              color: '#64748B', bg: '#F1F5F9' }},
    }};

    function renderConnectionItem(conn) {{
        const type   = conn.affiliation_type || '';
        const person = conn.scientist_name   || '';
        const ev     = conn.evidence         || [];
        const cfg    = CONN_CFG[type] || {{ label: type.replace(/_/g,' '), color: '#64748B', bg: '#F1F5F9' }};

        function patentUrl(e) {{
            // Priority: direct link
            if (e.link || e.url) return e.link || e.url;

            // Fallback: construct from patent_id
            if (e.patent_id) return 'https://patents.google.com/patent/' + e.patent_id;

            // Last resort: search URL from title (for old data without IDs)
            // Use full title (no truncation) for exact search
            var title = (e.title || '').trim();
            if (title) {{
                return 'https://patents.google.com/?q=' + encodeURIComponent('"' + title + '"');
            }}

            return '';
        }}

        let body = '';
        if (type === 'patent_assignee') {{
            const e = ev[0] || {{}};
            const t = e.title ? '"' + e.title + '"' : '';
            const u = patentUrl(e);
            body = 'Brevet déposé par <strong>' + person + '</strong>, assigné à ce corporate'
                 + (t ? '<br/><span style="color:#64748B;font-style:italic;font-size:11px;">' + t + '</span>' : '')
                 + (u ? '<br/><a href="' + u + '" target="_blank" style="color:#0066CC;font-size:11px;">Voir le brevet →</a>' : '');

        }} else if (type === 'patent_citation') {{
            const e = ev[0] || {{}};
            const t = e.title ? '"' + e.title + '"' : '';
            const u = patentUrl(e);
            body = 'Ce corporate a cité un brevet de <strong>' + person + '</strong>'
                 + (t ? '<br/><span style="color:#64748B;font-style:italic;font-size:11px;">' + t + '</span>' : '')
                 + (u ? '<br/><a href="' + u + '" target="_blank" style="color:#0066CC;font-size:11px;">Voir le brevet →</a>' : '');

        }} else if (type === 'patent_inventor') {{
            const links = ev.map(function(e) {{
                const t = (e.title||e.patent_id||'');
                const u = patentUrl(e);
                return u ? '<a href="' + u + '" target="_blank" style="color:#0066CC;font-size:11px;">' + t + '</a>'
                         : '<span style="font-size:11px;color:#64748B;">' + t + '</span>';
            }}).join('<br/>');
            body = '<strong>' + person + '</strong> est co-inventeur de <strong>'
                 + ev.length + '\u00a0brevet(s)</strong> pour ce corporate'
                 + (links ? '<div style="margin-top:4px;">' + links + '</div>' : '');

        }} else if (type === 'clinical_trials') {{
            const links = ev.slice(0,3).map(function(e) {{
                const t = (e.study_title||'').substring(0,70) + (e.study_title&&e.study_title.length>70?'…':'');
                const u = e.url || ('https://clinicaltrials.gov/ct2/show/' + (e.nct_id||''));
                return '<a href="' + u + '" target="_blank" style="color:#0066CC;font-size:11px;">'
                     + (e.nct_id ? e.nct_id + (t?' — '+t:'') : t) + '</a>';
            }}).join('<br/>');
            var nSponsors = ev.filter(function(e) {{ return e.detection_field === 'Sponsor'; }}).length;
            var nCollabs  = ev.filter(function(e) {{ return e.detection_field === 'Collaborateur'; }}).length;
            var ctRelation;
            if (nCollabs > 0 && nSponsors === 0) {{
                ctRelation = 'avec ce corporate comme collaborateur';
            }} else if (nCollabs > 0 && nSponsors > 0) {{
                ctRelation = 'avec ce corporate (sponsor ou collaborateur)';
            }} else {{
                ctRelation = 'sponsorisé(s) par ce corporate';
            }}
            body = '<strong>' + person + '</strong> est investigateur sur <strong>' + ev.length + '\u00a0essai(s) clinique(s)</strong> ' + ctRelation
                 + (links ? '<div style="margin-top:4px;">' + links + '</div>' : '');

        }} else if (type === 'transparence_sante') {{
            const total = ev.reduce(function(s,e){{ return s+(parseFloat(e.amount)||0); }}, 0);
            const totalStr = total > 0 ? total.toLocaleString('fr-FR',{{style:'currency',currency:'EUR',maximumFractionDigits:0}}) : '';
            const reasons = [...new Set(ev.map(function(e){{ return e.reason; }}).filter(Boolean))].slice(0,3).join(', ');
            body = '<strong>' + person + '</strong> — <strong>' + ev.length + '\u00a0paiement(s) déclaré(s)</strong>'
                 + (totalStr ? ' — total\u00a0: <strong>' + totalStr + '</strong>' : '')
                 + (reasons ? '<br/><span style="color:#64748B;font-style:italic;font-size:11px;">' + reasons + '</span>' : '');

        }} else if (type === 'open_payments') {{
            const total = ev.reduce(function(s,e){{ return s+(parseFloat(e.amount_usd)||0); }}, 0);
            const totalStr = total > 0 ? total.toLocaleString('en-US',{{style:'currency',currency:'USD',maximumFractionDigits:0}}) : '';
            const natures = [...new Set(ev.map(function(e){{ return e.nature_of_payment; }}).filter(Boolean))].slice(0,3).join(', ');
            const years   = [...new Set(ev.map(function(e){{ return e.program_year; }}).filter(Boolean))].sort().join(', ');
            body = '<strong>' + person + '</strong> — <strong>' + ev.length + '\u00a0payment(s) — CMS Open Payments</strong>'
                 + (totalStr ? ' — total\u00a0: <strong>' + totalStr + '</strong>' : '')
                 + (natures ? '<br/><span style="color:#64748B;font-style:italic;font-size:11px;">' + natures + '</span>' : '')
                 + (years   ? '<br/><span style="color:#92400E;font-size:11px;">Year(s)\u00a0: ' + years + '</span>' : '');

        }} else if (type === 'employment') {{
            body = '<strong>' + person + '</strong> est affilié(e) à ce corporate (source Scholar)';

        }} else {{
            body = conn.notes || cfg.label;
        }}

        return '<div style="margin:5px 0;padding:8px 10px;border-radius:6px;background:' + cfg.bg + ';border-left:3px solid ' + cfg.color + ';">'
             + '<div style="font-size:10px;font-weight:700;color:' + cfg.color + ';text-transform:uppercase;letter-spacing:0.05em;margin-bottom:3px;">' + cfg.label + '</div>'
             + '<div style="font-size:12px;color:#334155;line-height:1.5;">' + body + '</div>'
             + '</div>';
    }}

    function closePathsPanel() {{
        const p = document.getElementById('paths-info-panel');
        if (p) p.remove();
        const ind = document.getElementById('connexion-scroll-indicator');
        if (ind) ind.remove();
        // Untoggle all active corporate toggles
        highlightedCorporates.forEach(function(corpId) {{
            const checkbox = document.getElementById('filter-' + corpId);
            if (checkbox) checkbox.checked = false;
        }});
        if (highlightedCorporates.size > 0) {{
            resetHighlight();
        }}
    }}

    // Retourne du HTML décrivant le lien entre la personne et le corporate (avec liens)
    function getConnectionLine(conn) {{
        const type  = conn.affiliation_type || '';
        const ev    = conn.evidence || [];
        const aStyle = 'color:#0066CC;font-size:11.5px;display:block;margin-top:2px;white-space:normal;word-break:break-word;overflow-wrap:break-word;';

        function patentUrl(e) {{
            // Priority: direct link
            if (e.link || e.url) return e.link || e.url;

            // Fallback: construct from patent_id
            if (e.patent_id) return 'https://patents.google.com/patent/' + e.patent_id;

            // Last resort: search URL from title (for old data without IDs)
            // Use full title (no truncation) for exact search
            var title = (e.title || '').trim();
            if (title) {{
                return 'https://patents.google.com/?q=' + encodeURIComponent('"' + title + '"');
            }}

            return '';
        }}

        if (type === 'patent_inventor') {{
            const links = ev.map(function(e) {{
                const t = escHtml(e.title || e.patent_id || '');
                const u = safeHref(patentUrl(e));
                return u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '" title="' + t + '">' + t + ' \u2197</a>'
                         : '<span style="' + aStyle + 'color:#64748B;" title="' + t + '">' + t + '</span>';
            }}).join('');
            return 'Co-inventeur de\u00a0' + ev.length + '\u00a0brevet(s) pour ce corporate' + links;

        }} else if (type === 'patent_assignee') {{
            const e = ev[0] || {{}};
            const t = e.title ? escHtml('"' + e.title.substring(0,60) + (e.title.length>60?'\u2026':'"')) : '';
            const u = safeHref(patentUrl(e));
            const link = u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '">Voir le brevet \u2197</a>' : '';
            return 'Brevet assign\u00e9 \u00e0 ce corporate'
                 + (t ? '<span style="' + aStyle + 'color:#64748B;">' + t + '</span>' : '')
                 + link;

        }} else if (type === 'patent_citation') {{
            const e = ev[0] || {{}};
            const u = safeHref(patentUrl(e));
            const link = u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '">Voir le brevet \u2197</a>' : '';
            return 'Ce corporate a cit\u00e9 un de ses brevets' + link;

        }} else if (type === 'clinical_trials') {{
            const nSponsors = ev.filter(function(e) {{ return e.detection_field === 'Sponsor'; }}).length;
            const nCollabs  = ev.filter(function(e) {{ return e.detection_field === 'Collaborateur'; }}).length;
            const rel = (nCollabs > 0 && nSponsors === 0) ? 'avec ce corporate comme collaborateur'
                      : (nCollabs > 0) ? 'avec ce corporate (sponsor ou collaborateur)'
                      : 'sponsoris\u00e9(s) par ce corporate';
            const links = ev.slice(0,3).map(function(e) {{
                const t = (e.study_title || '').substring(0,55) + (e.study_title && e.study_title.length>55 ? '\u2026' : '');
                const u = safeHref(e.url || ('https://clinicaltrials.gov/ct2/show/' + encodeURIComponent(e.nct_id || '')));
                const label = escHtml(e.nct_id ? e.nct_id + (t ? '\u00a0- ' + t : '') : t);
                return u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '">' + label + ' \u2197</a>'
                         : '<span style="' + aStyle + 'color:#64748B;">' + label + '</span>';
            }}).join('');
            return 'Investigateur sur\u00a0' + ev.length + '\u00a0essai(s) clinique(s)\u00a0' + rel + links;

        }} else if (type === 'transparence_sante') {{
            const total = ev.reduce(function(s,e){{ return s+(parseFloat(e.amount)||0); }}, 0);
            const totalStr = total > 0 ? '\u00a0- total\u00a0: ' + total.toLocaleString('fr-FR',{{style:'currency',currency:'EUR',maximumFractionDigits:0}}) : '';
            const reasonLinks = ev.filter(function(e){{ return e.reason; }}).slice(0,3).map(function(e) {{
                const u = e.declaration_id ? safeHref('https://www.transparence.sante.gouv.fr/pages/detailsdeclaration/?q.id=' + encodeURIComponent(e.declaration_id)) : '';
                return u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '">' + escHtml(e.reason) + ' \u2197</a>'
                         : '<span style="' + aStyle + 'color:#64748B;">' + escHtml(e.reason) + '</span>';
            }}).join('');
            return ev.length + '\u00a0paiement(s) d\u00e9clar\u00e9(s) - Transparence Sant\u00e9' + totalStr + reasonLinks;

        }} else if (type === 'open_payments') {{
            const total = ev.reduce(function(s,e){{ return s+(parseFloat(e.amount_usd)||0); }}, 0);
            const totalStr = total > 0 ? '\u00a0- total\u00a0: ' + total.toLocaleString('en-US',{{style:'currency',currency:'USD',maximumFractionDigits:0}}) : '';
            const natures = [...new Set(ev.map(function(e){{ return e.nature_of_payment; }}).filter(Boolean))].slice(0,3).map(escHtml).join(', ');
            return ev.length + '\u00a0payment(s) - CMS Open Payments' + totalStr
                 + (natures ? '<span style="' + aStyle + 'color:#64748B;">' + natures + '</span>' : '');

        }} else if (type === 'employment') {{
            const e = ev[0] || {{}};
            if (e.source !== 'openalex') return 'Affili\u00e9(e) \u00e0 ce corporate';
            const when = e.is_current ? 'affiliation actuelle' : 'affiliation pass\u00e9e';
            const u = safeHref(e.url);
            return 'Affili\u00e9(e) \u00e0 ce corporate (' + when + ')'
                 + (u ? '<a href="' + u + '" target="_blank" style="' + aStyle + '">Source\u00a0: OpenAlex \u2197</a>'
                      : '<span style="' + aStyle + 'color:#64748B;">Source\u00a0: OpenAlex</span>');
        }}
        return escHtml(type.replace(/_/g, ' '));
    }}

    // Panneau de connexions : affiche POURQUOI un corporate est lié
    function displayMultiPathsInfo(allPathsPerCorporate) {{
        const existingPanel = document.getElementById('paths-info-panel');
        if (existingPanel) existingPanel.remove();
        const existingInd = document.getElementById('connexion-scroll-indicator');
        if (existingInd) existingInd.remove();

        // Helper : trouve le type de relation entre le seed et une personne
        function getSeedRelation(personName) {{
            let personNodeId = null;
            nodes.forEach(function(n) {{
                if (n.label === personName && n.node_type === 'person') personNodeId = n.id;
            }});
            if (!personNodeId || personNodeId === seedNodeId) return null;
            const seedEdgeIds = network.getConnectedEdges(seedNodeId);
            for (var i = 0; i < seedEdgeIds.length; i++) {{
                const edge = edges.get(seedEdgeIds[i]);
                if (!edge) continue;
                const other = edge.from === seedNodeId ? edge.to : edge.from;
                if (other === personNodeId) {{
                    const etype = edge.etype || '';
                    if (etype === 'co_author_with') return 'co-auteur';
                    if (etype === 'co_invented')    return 'co-inventeur';
                    return null;
                }}
            }}
            return null;
        }}

        const seedLabel = (nodes.get(seedNodeId) || {{}}).label || '';
        function normName(s) {{
            return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
        }}

        const panel = document.createElement('div');
        panel.id = 'paths-info-panel';
        panel.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 16px 18px;
            min-width: 350px;
            max-width: 500px;
            max-height: 550px;
            overflow-y: scroll;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.12);
            z-index: 10000;
        `;

        const S = {{
            label:       'font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#0066CC;margin:10px 0 4px 0;',
            labelDirect: 'font-size:12.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#0066CC;margin:10px 0 4px 0;',
            arrow:       'font-size:13px;color:#1E293B;margin:3px 0;',
            arrowDirect: 'font-size:14px;font-weight:600;color:#1E293B;margin:3px 0;',
            corpName:    'font-size:15px;font-weight:700;color:#1E293B;margin-bottom:2px;',
            sep:         'border:none;border-top:1px solid #F1F5F9;margin:12px 0 10px;',
        }};

        let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                 + '<span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#0066CC;">Connexion</span>'
                 + '<button onclick="closePathsPanel()" style="border:none;background:none;font-size:18px;cursor:pointer;color:#94A3B8;line-height:1;padding:0;">×</button>'
                 + '</div>';

        allPathsPerCorporate.forEach(function({{ corporateId, paths }}, idx) {{
            const n    = nodes.get(corporateId);
            const name = n ? n.label : corporateId;

            const nodeData = (graphData.corporates||[]).find(function(c){{ return c.id===corporateId; }})
                          || (graphData.institutions||[]).find(function(i){{ return i.id===corporateId; }});
            const connections = nodeData ? (nodeData.connections||[]) : [];

            if (idx > 0) html += '<hr style="' + S.sep + '">';

            html += '<div style="' + S.corpName + '">' + escHtml(name) + '</div>';

            if (connections.length > 0) {{
                // Grouper les connexions par personne
                const byPerson = {{}};
                connections.forEach(function(conn) {{
                    const p = conn.scientist_name || '—';
                    if (!byPerson[p]) byPerson[p] = [];
                    byPerson[p].push(conn);
                }});

                // Trier : liens directs du seed en premier, puis liens indirects
                const persons = Object.keys(byPerson).sort(function(a, b) {{
                    const aD = normName(a) === normName(seedLabel) ? 0 : 1;
                    const bD = normName(b) === normName(seedLabel) ? 0 : 1;
                    return aD - bD;
                }});

                persons.forEach(function(person) {{
                    const rel = getSeedRelation(person);
                    const isDirect = (normName(person) === normName(seedLabel));
                    const isIndirect = !isDirect && rel;

                    if (isDirect) {{
                        html += '<div style="' + S.labelDirect + '">Lien direct\u00a0:</div>'
                              + '<div style="' + S.arrowDirect + '">\u2192\u00a0' + escHtml(person) + '</div>';
                    }} else if (isIndirect) {{
                        html += '<div style="' + S.label + '">Lien identifi\u00e9\u00a0:</div>'
                              + '<div style="' + S.arrow + '">\u2192\u00a0' + escHtml(person) + '</div>';
                    }}

                    html += '<div style="' + (isDirect ? S.labelDirect : S.label) + '">Pourquoi\u00a0?</div>';

                    if (isIndirect) {{
                        html += '<div style="' + S.arrow + '">\u2192\u00a0'
                              + rel.charAt(0).toUpperCase() + rel.slice(1) + ' avec\u00a0' + escHtml(seedLabel)
                              + '</div>';
                    }}

                    byPerson[person].forEach(function(conn) {{
                        const lineStyle = isDirect ? S.arrowDirect : S.arrow;
                        html += '<div style="' + lineStyle + '">\u2192\u00a0' + getConnectionLine(conn) + '</div>';
                    }});
                }});

            }} else {{
                // Fallback : afficher le chemin brut
                html += '<div style="' + S.label + '">Chemin identifi\u00e9\u00a0:</div>';
                paths.slice(0,2).forEach(function(path) {{
                    const labels = path.map(function(id){{ const nd=nodes.get(id); return nd?nd.label:id; }});
                    html += '<div style="' + S.arrow + '">\u2192\u00a0' + labels.map(escHtml).join(' \u2192 ') + '</div>';
                }});
            }}
        }});

        panel.innerHTML = html;
        document.body.appendChild(panel);

        // Indicateur visuel "↓ défiler" — fiable sur macOS quelle que soit la config scrollbar
        (function(){{
            var ind = document.createElement('div');
            ind.id = 'connexion-scroll-indicator';
            ind.style.cssText = 'position:fixed;bottom:20px;left:20px;height:52px;background:linear-gradient(to bottom,transparent,rgba(255,255,255,0.97));border-radius:0 0 10px 10px;z-index:10001;pointer-events:none;display:flex;align-items:flex-end;justify-content:center;padding-bottom:8px;opacity:0;transition:opacity 0.2s;';
            ind.innerHTML = '<span style="font-size:11px;color:#64748B;background:rgba(255,255,255,0.9);border:1px solid #E2E8F0;border-radius:10px;padding:2px 10px;">↓ d\u00e9filer</span>';
            document.body.appendChild(ind);

            function updateInd() {{
                ind.style.width = panel.offsetWidth + 'px';
                var hasMore = panel.scrollHeight > panel.clientHeight + 5;
                var atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 5;
                ind.style.opacity = (hasMore && !atBottom) ? '1' : '0';
            }}
            panel.addEventListener('scroll', updateInd);
            setTimeout(updateInd, 50);
        }})();
    }}

    // Reset highlight
    function resetHighlight() {{
        highlightedCorporates.clear();

        // Remove paths info panel and scroll indicator
        const pathsPanel = document.getElementById('paths-info-panel');
        if (pathsPanel) {{
            pathsPanel.remove();
        }}
        const scrollIndicator = document.getElementById('connexion-scroll-indicator');
        if (scrollIndicator) {{
            scrollIndicator.remove();
        }}

        // Batch all node updates instead of calling nodes.update() for each node
        const nodeUpdates = [];
        nodes.forEach(function(node) {{
            // Check if node should be visible based on filter checkboxes
            const checkbox = document.getElementById('filter-' + node.id);

            // Corporate nodes are always visible (toggle controls highlight, not visibility)
            const isCorporate = graphData.corporates.some(function(c) {{ return c.id === node.id; }});
            const shouldBeVisible = isCorporate || !checkbox || checkbox.checked;

            nodeUpdates.push({{
                id: node.id,
                hidden: !shouldBeVisible,
                color: originalNodeColors[node.id],
                borderWidth: 1
            }});
        }});
        nodes.update(nodeUpdates);  // Single batch call

        // Batch all edge updates instead of calling edges.update() for each edge
        const edgeUpdates = [];
        edges.forEach(function(edge) {{
            // Edge should be visible if both connected nodes are visible
            const sourceNode = nodes.get(edge.from);
            const targetNode = nodes.get(edge.to);
            const shouldBeVisible = sourceNode && targetNode && !sourceNode.hidden && !targetNode.hidden;

            edgeUpdates.push({{
                id: edge.id,
                hidden: !shouldBeVisible,
                color: originalEdgeColors[edge.id],
                width: edge.width || 1
            }});
        }});
        edges.update(edgeUpdates);  // Single batch call

        updateStats();
    }}

    // Find all paths from source to target using BFS
    function findAllPaths(sourceId, targetId) {{
        const paths = [];
        const maxDepth = 3;
        // Each queue item: [pathArray, visitedSet] — avoid O(n) path.includes()
        const queue = [[[sourceId], new Set([sourceId])]];
        let head = 0; // index-based queue avoids O(n) shift()

        while (head < queue.length) {{
            const [path, visited] = queue[head++];
            const currentNode = path[path.length - 1];

            if (path.length > maxDepth) continue;

            if (currentNode === targetId) {{
                paths.push(path);
                continue;
            }}

            network.getConnectedEdges(currentNode).forEach(function(edgeId) {{
                const edge = edges.get(edgeId);
                if (!edge) return;
                const neighbor = (edge.from === currentNode) ? edge.to : edge.from;
                if (!visited.has(neighbor) && nodes.get(neighbor)) {{
                    const newVisited = new Set(visited);
                    newVisited.add(neighbor);
                    queue.push([[...path, neighbor], newVisited]);
                }}
            }});
        }}

        return paths;
    }}

    // Highlight a person node (from co-author click)
    function highlightPerson(personId) {{
        // Focus on the node
        network.focus(personId, {{
            scale: 1.5,
            animation: {{
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }}
        }});

        // Temporarily highlight the node
        const originalColor = originalNodeColors[personId];
        nodes.update({{
            id: personId,
            color: {{
                background: '#FFD700',
                border: '#22C55E'
            }},
            borderWidth: 4
        }});

        // Reset after 2 seconds
        setTimeout(function() {{
            if (highlightedCorporates.size === 0) {{
                nodes.update({{
                    id: personId,
                    color: originalColor,
                    borderWidth: 1
                }});
            }}
        }}, 2000);
    }}

    // ── Dropdown toggle for horizontal filter bar ──
    function toggleDropdown(category) {{
        const btn = document.querySelector('#group-' + category + ' .group-btn');
        const dd = document.getElementById('dropdown-' + category);
        const isOpen = dd.classList.contains('open');
        // Close all dropdowns first
        document.querySelectorAll('.dropdown').forEach(function(d) {{ d.classList.remove('open'); }});
        document.querySelectorAll('.group-btn').forEach(function(b) {{ b.classList.remove('active'); }});
        // Open the clicked one if it was closed
        if (!isOpen) {{
            dd.classList.add('open');
            btn.classList.add('active');
            try {{ window.parent.postMessage({{ type: 'filterClick', filter: category }}, '*'); }} catch(e) {{}}
        }}
    }}

    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {{
        if (!e.target.closest('.filter-group')) {{
            document.querySelectorAll('.dropdown').forEach(function(d) {{ d.classList.remove('open'); }});
            document.querySelectorAll('.group-btn').forEach(function(b) {{ b.classList.remove('active'); }});
        }}
    }});

    // Select/Deselect all functions
    function selectAllCorporates() {{
        // Reset state first
        highlightedCorporates.clear();
        closePathsPanel();

        // In Directs mode, only select direct corporates
        var onlyDirect = directFilterActive.corporates;
        graphData.corporates.forEach(function(corp) {{
            if (onlyDirect && !corp.direct) return;
            highlightedCorporates.add(corp.id);
            const checkbox = document.getElementById('filter-' + corp.id);
            if (checkbox) checkbox.checked = true;
        }});

        // Single highlight pass at the end
        if (highlightedCorporates.size > 0) {{
            highlightPathsToAllCorporates();
        }}
    }}

    function deselectAllCorporates() {{
        highlightedCorporates.clear();
        graphData.corporates.forEach(function(corp) {{
            const checkbox = document.getElementById('filter-' + corp.id);
            if (checkbox) checkbox.checked = false;
        }});
        resetHighlight();
    }}

    // ── Batch helpers ────────────────────────────────────────────────────────
    // Un seul nodes.update([...]) + edges.update([...]) au lieu de N appels
    // individuels → élimine le freeze sur les grands groupes (>100 items)
    function _batchShowNodes(ids) {{
        if (!ids.length) return;
        const idSet = new Set(ids);
        nodes.update(ids.map(function(id) {{ return {{id: id, hidden: false}}; }}));
        const edgeUpdates = [];
        edges.forEach(function(edge) {{
            if (idSet.has(edge.from) || idSet.has(edge.to)) {{
                const f = nodes.get(edge.from), t = nodes.get(edge.to);
                if (f && t && !f.hidden && !t.hidden)
                    edgeUpdates.push({{id: edge.id, hidden: false}});
            }}
        }});
        if (edgeUpdates.length) edges.update(edgeUpdates);
        updateStats();
    }}

    function _batchHideNodes(ids) {{
        if (!ids.length) return;
        const idSet = new Set(ids);
        nodes.update(ids.map(function(id) {{ return {{id: id, hidden: true}}; }}));
        const edgeUpdates = [];
        edges.forEach(function(edge) {{
            if (idSet.has(edge.from) || idSet.has(edge.to))
                edgeUpdates.push({{id: edge.id, hidden: true}});
        }});
        if (edgeUpdates.length) edges.update(edgeUpdates);
        updateStats();
    }}
    // ─────────────────────────────────────────────────────────────────────────

    function selectAllInstitutions() {{
        const ids = [];
        graphData.institutions.forEach(function(inst) {{
            const cb = document.getElementById('filter-' + inst.id);
            if (cb && !cb.checked) {{ cb.checked = true; ids.push(inst.id); }}
        }});
        _batchShowNodes(ids);
    }}

    function deselectAllInstitutions() {{
        const ids = [];
        graphData.institutions.forEach(function(inst) {{
            const cb = document.getElementById('filter-' + inst.id);
            if (cb && cb.checked) {{ cb.checked = false; ids.push(inst.id); }}
        }});
        _batchHideNodes(ids);
    }}

    // ── Direct-only filter ──────────────────────────────────────────────────
    // State: which groups are in "directs only" mode
    var directFilterActive = {{ corporates: false, institutions: false }};

    function toggleDirectFilter(group) {{
        directFilterActive[group] = !directFilterActive[group];
        var btn = document.getElementById('btn-direct-' + group);
        if (directFilterActive[group]) {{
            btn.style.background = '#eff6ff';
            btn.style.color = '#1d4ed8';
            btn.style.borderColor = '#3b82f6';
        }} else {{
            btn.style.background = '#f8fafc';
            btn.style.color = '#4a5568';
            btn.style.borderColor = '#e2e8f0';
        }}
        applyDirectFilter(group);
    }}

    function applyDirectFilter(group) {{
        var active = directFilterActive[group];
        var listId = group + '-list';
        var items = document.getElementById(listId).querySelectorAll('.toggle-item, .filter-item');
        var data = group === 'corporates' ? graphData.corporates : graphData.institutions;

        // Build a set of direct IDs for fast lookup
        var directIds = new Set();
        data.forEach(function(d) {{ if (d.direct) directIds.add(d.id); }});

        // 1) Filter sidebar list
        items.forEach(function(el) {{
            var nodeId = el.dataset.nodeId;
            if (!nodeId) return;
            el.style.display = (active && !directIds.has(nodeId)) ? 'none' : '';
        }});

        // 2) Update graph — different strategy per group:
        //    Corporates use opacity (they're always visible, highlight controls paths)
        //    Institutions use hidden (checkbox controls their visibility)
        // Opacity dimming — node_type is the correct property (not group)
        var nodeType = group.slice(0, -1); // 'corporates'→'corporate', 'institutions'→'institution'
        nodes.forEach(function(node) {{
            if (node.node_type !== nodeType) return;
            if (active && !directIds.has(node.id)) {{
                nodes.update({{ id: node.id, opacity: 0.15, font: {{ color: '#ccc' }} }});
            }} else {{
                nodes.update({{ id: node.id, opacity: 1.0, font: {{ color: undefined }} }});
            }}
        }});
    }}
    // ─────────────────────────────────────────────────────────────────────────

    function selectAllPatents() {{
        const ids = [];
        graphData.patents.forEach(function(p) {{
            const cb = document.getElementById('filter-' + p.id);
            if (cb && !cb.checked) {{ cb.checked = true; ids.push(p.id); }}
        }});
        _batchShowNodes(ids);
    }}

    function deselectAllPatents() {{
        const ids = [];
        graphData.patents.forEach(function(p) {{
            const cb = document.getElementById('filter-' + p.id);
            if (cb && cb.checked) {{ cb.checked = false; ids.push(p.id); }}
        }});
        _batchHideNodes(ids);
    }}

    function selectAllPublications() {{
        const ids = [];
        graphData.publications.forEach(function(pub) {{
            const cb = document.getElementById('filter-' + pub.id);
            if (cb && !cb.checked) {{ cb.checked = true; ids.push(pub.id); }}
        }});
        _batchShowNodes(ids);
    }}

    function deselectAllPublications() {{
        const ids = [];
        graphData.publications.forEach(function(pub) {{
            const cb = document.getElementById('filter-' + pub.id);
            if (cb && cb.checked) {{ cb.checked = false; ids.push(pub.id); }}
        }});
        _batchHideNodes(ids);
    }}

    function filterPublicationsList(query) {{
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#publications-list .publication-item').forEach(function(item) {{
            item.style.display = (!q || item.dataset.title.includes(q)) ? '' : 'none';
        }});
    }}

    function filterCorporatesList(query) {{
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#corporates-list .toggle-item').forEach(function(item) {{
            item.style.display = (!q || (item.dataset.label || '').includes(q)) ? '' : 'none';
        }});
    }}

    function filterInstitutionsList(query) {{
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#institutions-list .filter-item').forEach(function(item) {{
            item.style.display = (!q || (item.dataset.label || '').includes(q)) ? '' : 'none';
        }});
    }}

    // ── Co-auteurs filter ──
    function createCoauthorItem(person, defaultChecked = true) {{
        const div = document.createElement('div');
        div.className = 'filter-item';
        div.dataset.name = person.label.toLowerCase();

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = defaultChecked;
        checkbox.id = 'filter-' + person.id;
        checkbox.onchange = function() {{
            handleNodeFilter(person.id, this.checked);
        }};

        const label = document.createElement('label');
        label.htmlFor = checkbox.id;

        const nameSpan = document.createElement('span');
        nameSpan.textContent = person.label;
        nameSpan.style.cssText = 'font-size:12px;color:#374151;';

        label.appendChild(nameSpan);

        if (person.collaborations > 0) {{
            const badge = document.createElement('span');
            badge.textContent = person.collaborations;
            badge.style.cssText = 'margin-left:6px;background:#dbeafe;color:#1d4ed8;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:700;';
            label.appendChild(badge);
        }}

        div.appendChild(checkbox);
        div.appendChild(label);
        return div;
    }}

    function filterCoauthorsList(query) {{
        const q = query.toLowerCase().trim();
        document.querySelectorAll('#coauthors-list .filter-item').forEach(function(item) {{
            item.style.display = (!q || item.dataset.name.includes(q)) ? '' : 'none';
        }});
    }}

    function selectAllCoauthors() {{
        const ids = [];
        graphData.persons.forEach(function(person) {{
            const cb = document.getElementById('filter-' + person.id);
            if (cb && !cb.checked) {{ cb.checked = true; ids.push(person.id); }}
        }});
        _batchShowNodes(ids);
    }}

    function deselectAllCoauthors() {{
        const ids = [];
        graphData.persons.forEach(function(person) {{
            const cb = document.getElementById('filter-' + person.id);
            if (cb && cb.checked) {{ cb.checked = false; ids.push(person.id); }}
        }});
        _batchHideNodes(ids);
    }}


    // Update stats
    function updateStats() {{
        let visibleNodes = 0;
        let visibleEdges = 0;

        nodes.forEach(function(node) {{
            if (!node.hidden) visibleNodes++;
        }});

        edges.forEach(function(edge) {{
            if (!edge.hidden) visibleEdges++;
        }});

        document.getElementById('visible-nodes-count').textContent = visibleNodes;
        document.getElementById('visible-edges-count').textContent = visibleEdges;
    }}

    // Dans l'appli web le graphe est une iframe sandboxée : la page parente ouvre
    // les liens (compatible Safari). Ouvert seul (CLI), on les ouvre nous-mêmes.
    const EMBEDDED = window.parent !== window;
    function openUrl(url) {{
        if (!/^https?:\\/\\//i.test(String(url || ''))) return;
        if (EMBEDDED) {{
            window.parent.postMessage({{ type: 'openUrl', url: url }}, '*');
        }} else {{
            window.open(url, '_blank', 'noopener');
        }}
    }}

    // ── Custom tooltip ──
    var _tt = document.getElementById('custom-tooltip');
    var _ttX = 0, _ttY = 0, _ttVisible = false;

    document.addEventListener('mousemove', function(e) {{
        _ttX = e.clientX;
        _ttY = e.clientY;
        if (_ttVisible) _positionTooltip();
    }});

    function _positionTooltip() {{
        var ttw = _tt.offsetWidth;
        var tth = _tt.offsetHeight;
        var vw  = window.innerWidth;
        var vh  = window.innerHeight;
        var off = 18;

        var left = _ttX + off;
        var top  = _ttY - Math.round(tth / 2);

        // Flip left if near right edge
        if (left + ttw + 12 > vw) left = _ttX - ttw - off;
        // Clamp: stay below filter bar (62px) and above bottom
        if (top < 70) top = 70;
        if (top + tth > vh - 8) top = vh - tth - 8;

        _tt.style.left = left + 'px';
        _tt.style.top  = top  + 'px';
    }}

    network.on('hoverNode', function(params) {{
        var nd = nodes.get(params.node);
        if (nd && nd.tooltip_html) {{
            _tt.innerHTML = nd.tooltip_html;
            _ttVisible = true;
            _tt.classList.add('visible');
            _positionTooltip();
        }}
        // Pointer cursor for clickable nodes
        if (nd && (nd.node_type === 'corporate' || nd.patents_url || nd.scholar_url)) {{
            network.canvas.frame.canvas.style.cursor = 'pointer';
        }}
    }});

    network.on('blurNode', function() {{
        _ttVisible = false;
        _tt.classList.remove('visible');
        network.canvas.frame.canvas.style.cursor = 'default';
    }});

    // Add click event handler to open Scholar profiles and Google Patents pages
    network.on("click", function(params) {{
        if (params.nodes.length > 0) {{
            var nodeId = params.nodes[0];
            var nodeData = nodes.get(nodeId);

            if (nodeData) {{
                if (nodeData.node_type === 'corporate') {{
                    // Toggle corporate highlight + show paths panel
                    var checkbox = document.getElementById('filter-' + nodeId);
                    var isChecked = highlightedCorporates.has(nodeId);
                    var newState = !isChecked;
                    if (checkbox) {{
                        checkbox.checked = newState;
                    }}
                    handleCorporateFilter(nodeId, newState);
                }} else if (nodeData.node_type === 'person' && EMBEDDED) {{
                    // Appli web : fiche co-auteur dans un nouvel onglet
                    const coauthorName = nodeData.label || nodeId;
                    const url = '/coauthor/' + encodeURIComponent(coauthorName) +
                                '?seed=' + encodeURIComponent(seedLabel);
                    window.open(url, '_blank');
                }} else if (nodeData.open_url) {{
                    // Profil OpenAlex, article, brevet ou institution
                    openUrl(nodeData.open_url);
                }}
            }}
        }}
    }});
</script>

<style>
    @keyframes slideIn {{
        from {{
            transform: translateX(20px);
            opacity: 0;
        }}
        to {{
            transform: translateX(0);
            opacity: 1;
        }}
    }}

    /* ── Scrollbar du panneau CONNEXION — toujours visible ── */
    #paths-info-panel::-webkit-scrollbar {{ width: 10px; }}
    #paths-info-panel::-webkit-scrollbar-track {{ background: #CBD5E0; border-radius: 4px; }}
    #paths-info-panel::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 4px; }}
    #paths-info-panel::-webkit-scrollbar-thumb:hover {{ background: #1E293B; }}
    #paths-info-panel {{ scrollbar-width: auto; scrollbar-color: #475569 #CBD5E0; }}

    /* ── Custom node tooltip ── */
    #custom-tooltip {{
        position: fixed;
        pointer-events: none;
        z-index: 99998;
        max-width: 300px;
        min-width: 180px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        font-size: 12.5px;
        line-height: 1.55;
        box-shadow: 0 4px 20px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.06);
        opacity: 0;
        transition: opacity 0.12s ease;
        overflow: hidden;
        word-break: break-word;
    }}

    #custom-tooltip.visible {{
        opacity: 1;
    }}

    #custom-tooltip .tt-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 8px;
        padding: 10px 13px 8px;
        border-bottom: 1px solid #f1f5f9;
    }}

    #custom-tooltip .tt-name {{
        font-weight: 700;
        font-size: 13px;
        color: #0f172a;
        flex: 1;
    }}

    #custom-tooltip .tt-name-sm {{
        font-size: 11.5px;
        font-weight: 600;
        color: #1e293b;
        line-height: 1.4;
    }}

    #custom-tooltip .tt-badge {{
        flex-shrink: 0;
        font-size: 10px;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 20px;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-top: 1px;
    }}

    #custom-tooltip .tt-badge-person      {{ background: #eff6ff; color: #1d4ed8; }}
    #custom-tooltip .tt-badge-publication {{ background: #f0fdf4; color: #15803d; }}
    #custom-tooltip .tt-badge-patent      {{ background: #fff7ed; color: #c2410c; }}
    #custom-tooltip .tt-badge-corporate   {{ background: #faf5ff; color: #7e22ce; }}
    #custom-tooltip .tt-badge-institution {{ background: #f0f9ff; color: #0369a1; }}

    #custom-tooltip .tt-body {{
        padding: 8px 13px 6px;
    }}

    #custom-tooltip .tt-row {{
        display: flex;
        align-items: baseline;
        gap: 6px;
        margin-bottom: 3px;
    }}

    #custom-tooltip .tt-key {{
        color: #64748b;
        font-size: 11px;
        min-width: 80px;
        flex-shrink: 0;
    }}

    #custom-tooltip .tt-val {{
        color: #1e293b;
        font-weight: 500;
        font-size: 12px;
    }}

    #custom-tooltip .tt-muted {{
        color: #94a3b8;
        font-size: 11.5px;
        padding: 4px 0;
    }}

    #custom-tooltip .tt-cta {{
        display: block;
        padding: 7px 13px;
        background: #f8fafc;
        border-top: 1px solid #f1f5f9;
        color: #2563eb;
        font-size: 11.5px;
        font-weight: 600;
        text-decoration: none;
        pointer-events: auto;
    }}

    #custom-tooltip .tt-hint {{
        padding: 5px 13px 8px;
        color: #2563eb;
        font-size: 10.5px;
        font-style: italic;
        opacity: 0.75;
    }}

    #custom-tooltip .tt-conn-label {{
        font-size: 10.5px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 5px;
    }}

    #custom-tooltip .tt-conn-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 6px;
        margin-bottom: 3px;
    }}

    #custom-tooltip .tt-conn-name {{
        color: #1e293b;
        font-weight: 500;
        font-size: 12px;
    }}

    #custom-tooltip .tt-conn-type {{
        color: #64748b;
        font-size: 10.5px;
        background: #f1f5f9;
        padding: 1px 6px;
        border-radius: 10px;
        white-space: nowrap;
    }}
</style>
"""

    html = html.replace("</body>", RECENTER_BUTTON_HTML + "\n" + FILTERS_PANEL_HTML + "\n" + LEGEND_HTML + "\n" + filters_javascript + "\n</body>")

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Graph HTML generated: {out_html}")
