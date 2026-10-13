#!/usr/bin/env python3
"""
Path finder for discovering relationship paths in KOL networks.

This module traverses the graph to find paths matching defined patterns,
starting from the seed person and exploring connections to organizations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.logger import logger
from .schema import PathPattern, ALL_PATTERNS, Hypothesis, EvidenceLevel


@dataclass
class FoundPath:
    """
    A path instance found in the graph.

    Attributes:
        pattern: The pattern this path matches.
        nodes: List of node dicts traversed (in order).
        edges: List of edge dicts traversed (in order).
        target_node: The final node (usually an organization).
        raw_score: Unweighted score based on edge weights.
    """
    pattern: PathPattern
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    target_node: Dict[str, Any]
    raw_score: float = 0.0

    @property
    def target_id(self) -> str:
        """ID of the target node."""
        return self.target_node.get("id", "")

    @property
    def target_label(self) -> str:
        """Label of the target node."""
        return self.target_node.get("label", "")

    @property
    def target_type(self) -> str:
        """Type of the target node."""
        return self.target_node.get("type", "")

    @property
    def path_length(self) -> int:
        """Number of edges in this path."""
        return len(self.edges)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pattern_id": self.pattern.pattern_id,
            "pattern_name": self.pattern.name,
            "hypothesis": self.pattern.hypothesis.value,
            "evidence_level": self.pattern.evidence_level.value,
            "target_id": self.target_id,
            "target_label": self.target_label,
            "target_type": self.target_type,
            "path_length": self.path_length,
            "raw_score": self.raw_score,
            "node_ids": [n.get("id") for n in self.nodes],
            "edge_types": [e.get("type") for e in self.edges],
        }


class GraphIndex:
    """
    Index structure for efficient graph traversal.

    Pre-builds adjacency lists for outgoing and incoming edges,
    enabling fast path exploration.
    """

    def __init__(self, graph_data: Dict[str, Any]):
        """
        Build index from graph data.

        Args:
            graph_data: Dict with "nodes" and "edges" lists.
        """
        self.nodes_by_id: Dict[str, Dict[str, Any]] = {}
        self.edges_out: Dict[str, List[Dict[str, Any]]] = {}  # source_id -> edges
        self.edges_in: Dict[str, List[Dict[str, Any]]] = {}   # target_id -> edges

        # Index nodes
        for node in graph_data.get("nodes", []):
            node_id = node.get("id")
            if node_id:
                self.nodes_by_id[node_id] = node

        # Index edges (both directions)
        for edge in graph_data.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")

            if source:
                if source not in self.edges_out:
                    self.edges_out[source] = []
                self.edges_out[source].append(edge)

            if target:
                if target not in self.edges_in:
                    self.edges_in[target] = []
                self.edges_in[target].append(edge)

        logger.debug(
            f"GraphIndex built: {len(self.nodes_by_id)} nodes, "
            f"{sum(len(v) for v in self.edges_out.values())} edges"
        )

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node by ID."""
        return self.nodes_by_id.get(node_id)

    def get_outgoing_edges(
        self,
        node_id: str,
        edge_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get edges going out from this node."""
        edges = self.edges_out.get(node_id, [])
        if edge_type:
            edges = [e for e in edges if e.get("type") == edge_type]
        return edges

    def get_incoming_edges(
        self,
        node_id: str,
        edge_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get edges coming into this node."""
        edges = self.edges_in.get(node_id, [])
        if edge_type:
            edges = [e for e in edges if e.get("type") == edge_type]
        return edges


class PathFinder:
    """
    Finds paths in the graph matching defined patterns.

    Uses depth-first search with pattern-guided exploration.
    """

    def __init__(self, graph_data: Dict[str, Any]):
        """
        Initialize with graph data.

        Args:
            graph_data: Dict with "meta", "nodes", "edges" from build_graph_data.
        """
        self.graph_data = graph_data
        self.index = GraphIndex(graph_data)
        self.seed_id = graph_data.get("meta", {}).get("seed_person_id", "")

    def find_all_paths(
        self,
        patterns: Optional[List[PathPattern]] = None,
        max_paths_per_pattern: int = 100
    ) -> List[FoundPath]:
        """
        Find all paths matching the given patterns.

        Args:
            patterns: Patterns to search for (default: all patterns).
            max_paths_per_pattern: Limit paths per pattern to avoid explosion.

        Returns:
            List of FoundPath instances.
        """
        if patterns is None:
            patterns = ALL_PATTERNS

        all_paths: List[FoundPath] = []

        for pattern in patterns:
            paths = self._find_pattern_paths(pattern, max_paths_per_pattern)
            all_paths.extend(paths)
            logger.debug(f"Pattern {pattern.pattern_id}: found {len(paths)} paths")

        return all_paths

    def find_paths_to_target(
        self,
        target_id: str,
        patterns: Optional[List[PathPattern]] = None
    ) -> List[FoundPath]:
        """
        Find all paths that end at a specific target node.

        Args:
            target_id: ID of the target node.
            patterns: Patterns to search (default: all).

        Returns:
            List of FoundPath instances ending at target.
        """
        all_paths = self.find_all_paths(patterns)
        return [p for p in all_paths if p.target_id == target_id]

    def find_paths_by_hypothesis(
        self,
        hypothesis: Hypothesis
    ) -> List[FoundPath]:
        """
        Find all paths for a specific hypothesis level.

        Args:
            hypothesis: H1, H2, or H3.

        Returns:
            List of FoundPath instances.
        """
        patterns = [p for p in ALL_PATTERNS if p.hypothesis == hypothesis]
        return self.find_all_paths(patterns)

    def _find_pattern_paths(
        self,
        pattern: PathPattern,
        max_paths: int = 100
    ) -> List[FoundPath]:
        """
        Find all paths matching a single pattern.

        Uses DFS starting from seed node, following the edge sequence.
        """
        if not self.seed_id:
            logger.warning("No seed_id found in graph meta")
            return []

        seed_node = self.index.get_node(self.seed_id)
        if not seed_node:
            logger.warning(f"Seed node {self.seed_id} not found in graph")
            return []

        found_paths: List[FoundPath] = []

        # Start DFS from seed
        self._dfs_search(
            pattern=pattern,
            current_node=seed_node,
            edge_index=0,
            path_nodes=[seed_node],
            path_edges=[],
            visited_nodes={self.seed_id},
            found_paths=found_paths,
            max_paths=max_paths,
        )

        return found_paths

    def _dfs_search(
        self,
        pattern: PathPattern,
        current_node: Dict[str, Any],
        edge_index: int,
        path_nodes: List[Dict[str, Any]],
        path_edges: List[Dict[str, Any]],
        visited_nodes: Set[str],
        found_paths: List[FoundPath],
        max_paths: int,
    ) -> None:
        """
        Recursive DFS to find paths matching pattern.

        Args:
            pattern: The pattern being matched.
            current_node: Current position in graph.
            edge_index: Which edge in pattern sequence we're looking for.
            path_nodes: Nodes traversed so far.
            path_edges: Edges traversed so far.
            visited_nodes: Set of visited node IDs (cycle prevention).
            found_paths: Accumulator for found paths.
            max_paths: Stop when this many paths found.
        """
        # Check if we found enough paths
        if len(found_paths) >= max_paths:
            return

        # Check if we completed the pattern
        if edge_index >= len(pattern.edge_sequence):
            # Pattern complete - create FoundPath
            target_node = path_nodes[-1]

            # Validate node type constraint if specified
            if pattern.node_types and len(pattern.node_types) > len(path_nodes) - 1:
                expected_type = pattern.node_types[-1]
                if expected_type and target_node.get("type") != expected_type:
                    return

            # Calculate raw score from edge weights
            raw_score = self._calculate_raw_score(pattern, path_edges)

            found_paths.append(FoundPath(
                pattern=pattern,
                nodes=list(path_nodes),
                edges=list(path_edges),
                target_node=target_node,
                raw_score=raw_score,
            ))
            return

        # Get the next edge requirement
        edge_type, direction = pattern.edge_sequence[edge_index]
        current_id = current_node.get("id", "")

        # Get candidate edges based on direction
        if direction == "out":
            candidate_edges = self.index.get_outgoing_edges(current_id, edge_type)
        else:  # direction == "in"
            candidate_edges = self.index.get_incoming_edges(current_id, edge_type)

        # Explore each candidate edge
        for edge in candidate_edges:
            # Determine next node based on direction
            if direction == "out":
                next_node_id = edge.get("target")
            else:
                next_node_id = edge.get("source")

            # Skip if already visited (cycle prevention)
            if next_node_id in visited_nodes:
                continue

            next_node = self.index.get_node(next_node_id)
            if not next_node:
                continue

            # Check node type constraint if specified
            if pattern.node_types and edge_index + 1 < len(pattern.node_types):
                expected_type = pattern.node_types[edge_index + 1]
                if expected_type and next_node.get("type") != expected_type:
                    continue

            # Recurse
            self._dfs_search(
                pattern=pattern,
                current_node=next_node,
                edge_index=edge_index + 1,
                path_nodes=path_nodes + [next_node],
                path_edges=path_edges + [edge],
                visited_nodes=visited_nodes | {next_node_id},
                found_paths=found_paths,
                max_paths=max_paths,
            )

    def _calculate_raw_score(
        self,
        pattern: PathPattern,
        edges: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate raw score from edge weights.

        Multiplies edge weights by pattern weight factors.
        """
        score = 0.0

        for i, edge in enumerate(edges):
            edge_type = edge.get("type", "")
            edge_weight = edge.get("weight", 1)

            # Get weight factor from pattern
            factor = pattern.weight_factors.get(edge_type, 1.0)

            # Add weighted contribution
            score += edge_weight * factor

        return score


def find_paths(
    graph_data: Dict[str, Any],
    patterns: Optional[List[PathPattern]] = None
) -> List[FoundPath]:
    """
    Convenience function to find paths in a graph.

    Args:
        graph_data: Graph data from build_graph_data().
        patterns: Patterns to search (default: all).

    Returns:
        List of FoundPath instances.
    """
    finder = PathFinder(graph_data)
    return finder.find_all_paths(patterns)
