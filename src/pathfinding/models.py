"""
Data models for pathfinding system.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from enum import Enum


class NodeType(str, Enum):
    """Type of node in the graph."""
    PERSON = "person"
    PUBLICATION = "publication"
    ORGANIZATION = "organization"


class RelationType(str, Enum):
    """Type of relationship between nodes."""
    AUTHORED = "authored"
    COAUTHOR = "coauthor"
    AFFILIATED = "affiliated"
    EMPLOYED = "employed"
    ASSIGNED_PATENT = "assigned_patent"


@dataclass
class Evidence:
    """Evidence supporting a relationship."""
    source: str  # openalex, ror, patent, etc.
    year: Optional[int] = None
    title: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Node:
    """Node in the knowledge graph."""
    id: str
    type: NodeType
    name: str
    is_corporate: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "is_corporate": self.is_corporate,
            "metadata": self.metadata
        }


@dataclass
class Edge:
    """Edge connecting two nodes."""
    source: str
    target: str
    relation_type: RelationType
    score: float
    evidence: Evidence

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type.value,
            "score": self.score,
            "evidence": self.evidence.to_dict()
        }


@dataclass
class PathStep:
    """Single step in a path."""
    entity: Node
    relation: Optional[Edge] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {"entity": self.entity.to_dict()}
        if self.relation:
            result["relation"] = self.relation.to_dict()
        return result


@dataclass
class Path:
    """Path from scientist to corporate."""
    steps: List[PathStep]
    score: float
    summary: str = ""

    @property
    def length(self) -> int:
        """Number of hops in the path."""
        return len([s for s in self.steps if s.relation is not None])

    @property
    def start_node(self) -> Node:
        """First node in path."""
        return self.steps[0].entity

    @property
    def end_node(self) -> Node:
        """Last node in path."""
        return self.steps[-1].entity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": round(self.score, 3),
            "length": self.length,
            "summary": self.summary or self._generate_summary(),
            "connection_type": self.get_connection_type(),
            "evidence": self.get_evidence_details(),
            "steps": [step.to_dict() for step in self.steps]
        }

    def _generate_summary(self) -> str:
        """Generate human-readable summary."""
        if len(self.steps) < 2:
            return "Invalid path"

        start = self.steps[0].entity.name
        end = self.steps[-1].entity.name

        if self.length == 1:
            relation = self.steps[0].relation.relation_type.value if self.steps[0].relation else "linked to"
            return f"{start} → {relation} → {end}"
        else:
            return f"{start} → ... ({self.length} steps) → {end}"

    def get_connection_type(self) -> str:
        """
        Determine the exact type of connection.

        Returns a human-readable description of how the scientist
        is connected to the corporate.
        """
        if len(self.steps) < 2:
            return "Unknown connection"

        # Analyze the path to determine connection type
        relation_types = []
        for step in self.steps:
            if step.relation:
                relation_types.append(step.relation.relation_type.value)

        # Direct affiliation
        if len(relation_types) == 1 and relation_types[0] == "affiliated":
            return "Direct affiliation"

        # Direct patent assignment
        if "assigned_patent" in relation_types and len(relation_types) <= 2:
            return "Patent assignee"

        # Via co-author with affiliation
        if "coauthor" in relation_types and "affiliated" in relation_types:
            # Find the co-author name
            coauthor_name = None
            for i, step in enumerate(self.steps):
                if step.relation and step.relation.relation_type.value == "coauthor":
                    if i + 1 < len(self.steps):
                        coauthor_name = self.steps[i + 1].entity.name
                        break

            if coauthor_name:
                return f"Co-author '{coauthor_name}' is affiliated with this corporate"
            return "Via co-author affiliation"

        # Via co-inventor with patent
        if "coauthor" in relation_types and "assigned_patent" in relation_types:
            # Find the co-inventor name
            coinventor_name = None
            for i, step in enumerate(self.steps):
                if step.relation and step.relation.relation_type.value == "coauthor":
                    if i + 1 < len(self.steps):
                        coinventor_name = self.steps[i + 1].entity.name
                        break

            if coinventor_name:
                return f"Co-inventor '{coinventor_name}' has patent assigned to this corporate"
            return "Via co-inventor patent assignment"

        return f"Connected via {len(relation_types)} relationships"

    def get_evidence_details(self) -> List[Dict[str, Any]]:
        """
        Extract detailed evidence from the path.

        Returns list of evidence items with type, title, year, url.
        """
        evidence_list = []

        for i, step in enumerate(self.steps):
            if not step.relation:
                continue

            ev = step.relation.evidence
            target = step.relation.target
            target_step = next((s for s in self.steps if s.entity.id == target), None)

            if target_step:
                evidence_item = {
                    "type": step.relation.relation_type.value,
                    "from": self.steps[i].entity.name if i < len(self.steps) else "Unknown",
                    "to": target_step.entity.name,
                    "entity_type": target_step.entity.type.value,
                }

                if ev.title:
                    evidence_item["title"] = ev.title
                if ev.year:
                    evidence_item["year"] = ev.year
                if ev.url:
                    evidence_item["url"] = ev.url

                evidence_list.append(evidence_item)

        return evidence_list


@dataclass
class CorporateConnection:
    """Connection between a scientist and a corporate."""
    scientist_id: str
    scientist_name: str
    corporate_id: str
    corporate_name: str
    best_path: Path
    all_paths: List[Path] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scientist": {
                "id": self.scientist_id,
                "name": self.scientist_name
            },
            "corporate": {
                "id": self.corporate_id,
                "name": self.corporate_name
            },
            "best_path": self.best_path.to_dict(),
            "alternative_paths": [p.to_dict() for p in self.all_paths[:2]]
        }
