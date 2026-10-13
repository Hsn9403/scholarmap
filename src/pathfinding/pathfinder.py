"""
Pathfinding algorithm to find connections between scientists and corporates.

Uses BFS with scoring to find the best explainable paths.
"""
from typing import List, Dict, Set, Optional, Tuple
from collections import deque
import heapq

from src.logger import logger

from .models import Path, PathStep, Node, Edge, NodeType


class Pathfinder:
    """
    Find paths in a graph from scientist to corporate.

    Uses weighted BFS to find shortest paths with best scores.
    """

    def __init__(
        self,
        nodes: Dict[str, Node],
        edges: List[Edge],
        max_path_length: int = 5
    ):
        """
        Initialize pathfinder.

        Args:
            nodes: Dict mapping node_id to Node.
            edges: List of edges.
            max_path_length: Maximum path length (number of hops).
        """
        self.nodes = nodes
        self.edges = edges
        self.max_path_length = max_path_length

        # Build adjacency list for fast traversal
        self._adjacency: Dict[str, List[Edge]] = {}
        for edge in edges:
            if edge.source not in self._adjacency:
                self._adjacency[edge.source] = []
            self._adjacency[edge.source].append(edge)

        logger.debug(
            f"Pathfinder initialized: {len(nodes)} nodes, {len(edges)} edges, "
            f"max path length={max_path_length}"
        )

    def find_paths(
        self,
        source_id: str,
        target_id: Optional[str] = None,
        max_paths: int = 3
    ) -> List[Path]:
        """
        Find paths from source to target (or any corporate if target=None).

        Args:
            source_id: Source node ID (scientist).
            target_id: Target node ID (corporate), or None for any corporate.
            max_paths: Maximum number of paths to return.

        Returns:
            List of Path objects, sorted by score (best first).
        """
        if source_id not in self.nodes:
            logger.error(f"Source node not found: {source_id}")
            return []

        if target_id and target_id not in self.nodes:
            logger.error(f"Target node not found: {target_id}")
            return []

        logger.info(
            f"Finding paths from {source_id} to "
            f"{target_id or 'any corporate'} (max={max_paths})"
        )

        # If target specified, find paths to that target
        if target_id:
            paths = self._bfs_paths(source_id, lambda nid: nid == target_id)
        else:
            # Find paths to any corporate
            paths = self._bfs_paths(
                source_id,
                lambda nid: nid in self.nodes and self.nodes[nid].is_corporate
            )

        # Score and sort paths
        scored_paths = [(self._score_path(p), p) for p in paths]
        scored_paths.sort(key=lambda x: x[0], reverse=True)

        # Take top N and build Path objects
        result = []
        for score, path_node_ids in scored_paths[:max_paths]:
            path_obj = self._build_path_object(path_node_ids, score)
            result.append(path_obj)

        logger.info(f"Found {len(result)} path(s)")
        return result

    def find_all_corporate_connections(
        self,
        scientist_id: str,
        max_corporates: int = 10
    ) -> Dict[str, Path]:
        """
        Find best path to each reachable corporate.

        Args:
            scientist_id: Scientist node ID.
            max_corporates: Maximum number of corporates to return.

        Returns:
            Dict mapping corporate_id to best Path.
        """
        logger.info(f"Finding all corporate connections for {scientist_id}")

        # Find all paths to corporates
        all_paths = self._bfs_all_paths(
            scientist_id,
            lambda nid: nid in self.nodes and self.nodes[nid].is_corporate
        )

        # Group by target corporate
        corporates_paths: Dict[str, List[List[str]]] = {}
        for path in all_paths:
            target_id = path[-1]
            if target_id not in corporates_paths:
                corporates_paths[target_id] = []
            corporates_paths[target_id].append(path)

        # For each corporate, keep best path
        result = {}
        for corporate_id, paths in corporates_paths.items():
            # Score all paths
            scored = [(self._score_path(p), p) for p in paths]
            scored.sort(key=lambda x: x[0], reverse=True)

            # Keep best path
            best_score, best_path = scored[0]
            path_obj = self._build_path_object(best_path, best_score)
            result[corporate_id] = path_obj

        # Sort by score and limit
        sorted_corporates = sorted(
            result.items(),
            key=lambda x: x[1].score,
            reverse=True
        )[:max_corporates]

        logger.info(f"Found {len(sorted_corporates)} corporate connection(s)")
        return dict(sorted_corporates)

    def _bfs_paths(
        self,
        source_id: str,
        is_target: callable
    ) -> List[List[str]]:
        """
        BFS to find paths to targets matching predicate.

        Args:
            source_id: Source node ID.
            is_target: Function (node_id) -> bool to identify targets.

        Returns:
            List of paths (each path is list of node IDs).
        """
        paths_found = []
        queue = deque([(source_id, [source_id])])
        visited = {source_id}

        while queue:
            current_id, path = queue.popleft()

            # Check if we reached a target
            if len(path) > 1 and is_target(current_id):
                paths_found.append(path)
                continue  # Don't explore further from this node

            # Check max length
            if len(path) >= self.max_path_length + 1:
                continue

            # Explore neighbors
            for edge in self._adjacency.get(current_id, []):
                neighbor_id = edge.target

                # Skip if visited (avoid cycles)
                if neighbor_id in path:
                    continue

                new_path = path + [neighbor_id]
                queue.append((neighbor_id, new_path))

        return paths_found

    def _bfs_all_paths(
        self,
        source_id: str,
        is_target: callable
    ) -> List[List[str]]:
        """
        BFS to find ALL paths to targets (not just shortest).

        Args:
            source_id: Source node ID.
            is_target: Function (node_id) -> bool to identify targets.

        Returns:
            List of paths.
        """
        paths_found = []
        queue = deque([(source_id, [source_id])])

        while queue:
            current_id, path = queue.popleft()

            # Check if target
            if len(path) > 1 and is_target(current_id):
                paths_found.append(path)
                continue

            # Check max length
            if len(path) >= self.max_path_length + 1:
                continue

            # Explore neighbors
            for edge in self._adjacency.get(current_id, []):
                neighbor_id = edge.target

                # Skip cycles
                if neighbor_id in path:
                    continue

                new_path = path + [neighbor_id]
                queue.append((neighbor_id, new_path))

        return paths_found

    def _score_path(self, path_node_ids: List[str]) -> float:
        """
        Score a path based on edge scores and length.

        Args:
            path_node_ids: List of node IDs in path.

        Returns:
            Path score (0-1, higher is better).
        """
        if len(path_node_ids) < 2:
            return 0.0

        # Collect edge scores
        edge_scores = []
        for i in range(len(path_node_ids) - 1):
            source = path_node_ids[i]
            target = path_node_ids[i + 1]

            # Find edge
            edge = self._find_edge(source, target)
            if edge:
                edge_scores.append(edge.score)
            else:
                edge_scores.append(0.5)  # Default if edge not found

        # Aggregate score: geometric mean of edge scores
        # Penalize longer paths
        avg_score = sum(edge_scores) / len(edge_scores)
        length_penalty = 1.0 / (1.0 + 0.1 * len(path_node_ids))

        return avg_score * length_penalty

    def _find_edge(self, source_id: str, target_id: str) -> Optional[Edge]:
        """Find edge between two nodes."""
        for edge in self._adjacency.get(source_id, []):
            if edge.target == target_id:
                return edge
        return None

    def _build_path_object(
        self,
        path_node_ids: List[str],
        score: float
    ) -> Path:
        """
        Build Path object from node IDs.

        Args:
            path_node_ids: List of node IDs.
            score: Path score.

        Returns:
            Path object.
        """
        steps = []

        for i, node_id in enumerate(path_node_ids):
            node = self.nodes.get(node_id)
            if not node:
                logger.warning(f"Node not found in path: {node_id}")
                continue

            # Get edge to next node
            edge = None
            if i < len(path_node_ids) - 1:
                next_id = path_node_ids[i + 1]
                edge = self._find_edge(node_id, next_id)

            step = PathStep(entity=node, relation=edge)
            steps.append(step)

        return Path(steps=steps, score=score)
