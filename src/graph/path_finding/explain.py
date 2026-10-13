#!/usr/bin/env python3
"""
Human-readable explanation generator for path-based evidence.

This module generates natural language explanations of discovered paths,
making the relationship evidence understandable to non-technical users.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .schema import EvidenceLevel, Hypothesis
from .path_finder import FoundPath
from .scoring import ScoredPath, TargetScore


# =============================================================================
# Edge Type Descriptions (for path narration)
# =============================================================================

EDGE_DESCRIPTIONS = {
    # Outgoing (source → target)
    ("has_patent", "out"): "holds patent",
    ("assigned_to", "out"): "is assigned to",
    ("affiliated_with", "out"): "is affiliated with",
    ("co_invented", "out"): "co-invented with",
    ("co_author_with", "out"): "co-authored with",
    ("cites", "out"): "cites patent owned by",
    # Incoming (target ← source)
    ("cites_patent", "in"): "was cited by",
    ("co_invented", "in"): "was co-inventor with",
}

# Evidence level labels (French/English)
EVIDENCE_LABELS = {
    EvidenceLevel.HARD: ("Preuve solide", "Hard evidence"),
    EvidenceLevel.MEDIUM: ("Preuve indirecte", "Medium evidence"),
    EvidenceLevel.SOFT: ("Signal faible", "Soft signal"),
}

HYPOTHESIS_LABELS = {
    Hypothesis.H1: ("Connexion directe", "Direct connection"),
    Hypothesis.H2: ("Connexion indirecte", "Indirect connection"),
    Hypothesis.H3: ("Connexion distante", "Distant connection"),
}


@dataclass
class PathExplanation:
    """
    Human-readable explanation of a path.

    Attributes:
        path: The original path.
        narrative: Natural language description.
        evidence_label: Evidence level description.
        hypothesis_label: Hypothesis level description.
        key_facts: List of key facts extracted from the path.
    """
    path: FoundPath
    narrative: str
    evidence_label: str
    hypothesis_label: str
    key_facts: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_id": self.path.pattern.pattern_id,
            "target_label": self.path.target_label,
            "narrative": self.narrative,
            "evidence_label": self.evidence_label,
            "hypothesis_label": self.hypothesis_label,
            "key_facts": self.key_facts,
        }


@dataclass
class TargetExplanation:
    """
    Complete explanation for a target entity.

    Attributes:
        target: The target score info.
        summary: One-sentence summary.
        detailed: Multi-paragraph explanation.
        path_explanations: Explanations for each path.
        confidence_statement: Statement about confidence level.
    """
    target: TargetScore
    summary: str
    detailed: str
    path_explanations: List[PathExplanation]
    confidence_statement: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_id": self.target.target_id,
            "target_label": self.target.target_label,
            "target_type": self.target.target_type,
            "summary": self.summary,
            "detailed": self.detailed,
            "confidence_statement": self.confidence_statement,
            "path_explanations": [p.to_dict() for p in self.path_explanations],
            "total_score": round(self.target.total_score, 2),
            "path_count": self.target.path_count,
        }


class PathExplainer:
    """
    Generates human-readable explanations for paths.
    """

    def __init__(self, lang: str = "fr"):
        """
        Initialize explainer.

        Args:
            lang: Language for explanations ("fr" or "en").
        """
        self.lang = lang
        self._lang_idx = 0 if lang == "fr" else 1

    def explain_path(self, path: FoundPath) -> PathExplanation:
        """
        Generate explanation for a single path.

        Args:
            path: The FoundPath to explain.

        Returns:
            PathExplanation with narrative and facts.
        """
        pattern = path.pattern
        nodes = path.nodes
        edges = path.edges

        # Build narrative from path steps
        narrative = self._build_narrative(nodes, edges, pattern)

        # Get labels
        evidence_label = EVIDENCE_LABELS.get(
            pattern.evidence_level, ("Inconnu", "Unknown")
        )[self._lang_idx]

        hypothesis_label = HYPOTHESIS_LABELS.get(
            pattern.hypothesis, ("Inconnu", "Unknown")
        )[self._lang_idx]

        # Extract key facts
        key_facts = self._extract_key_facts(path)

        return PathExplanation(
            path=path,
            narrative=narrative,
            evidence_label=evidence_label,
            hypothesis_label=hypothesis_label,
            key_facts=key_facts,
        )

    def explain_target(self, target: TargetScore) -> TargetExplanation:
        """
        Generate complete explanation for a target entity.

        Args:
            target: TargetScore with aggregated path info.

        Returns:
            TargetExplanation with summary and details.
        """
        # Explain each path
        path_explanations = [
            self.explain_path(sp.path) for sp in target.paths
        ]

        # Generate summary
        summary = self._generate_summary(target, path_explanations)

        # Generate detailed explanation
        detailed = self._generate_detailed(target, path_explanations)

        # Generate confidence statement
        confidence = self._generate_confidence_statement(target)

        return TargetExplanation(
            target=target,
            summary=summary,
            detailed=detailed,
            path_explanations=path_explanations,
            confidence_statement=confidence,
        )

    def _build_narrative(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        pattern
    ) -> str:
        """Build natural language narrative for path."""
        if not nodes:
            return ""

        # Start with seed person
        seed_label = nodes[0].get("label", "?")
        parts = [seed_label]

        # Add each step
        for i, edge in enumerate(edges):
            edge_type = edge.get("type", "?")
            direction = pattern.edge_sequence[i][1] if i < len(pattern.edge_sequence) else "out"

            # Get edge description
            desc = EDGE_DESCRIPTIONS.get((edge_type, direction))
            if not desc:
                desc = edge_type.replace("_", " ")

            # Get next node
            next_node = nodes[i + 1] if i + 1 < len(nodes) else {}
            next_label = next_node.get("label", "?")

            parts.append(f"{desc} **{next_label}**")

        # Join with arrows or natural flow
        if self.lang == "fr":
            return " → ".join(parts)
        return " → ".join(parts)

    def _extract_key_facts(self, path: FoundPath) -> List[str]:
        """Extract notable facts from path edges."""
        facts = []

        for edge in path.edges:
            edge_type = edge.get("type", "")
            attrs = edge.get("attributes", {})
            weight = edge.get("weight", 1)

            # Co-authorship facts
            if edge_type == "co_author_with":
                count = attrs.get("shared_pubs_count", weight)
                if count > 1:
                    if self.lang == "fr":
                        facts.append(f"{count} publications en commun")
                    else:
                        facts.append(f"{count} shared publications")

                year = attrs.get("last_shared_year")
                if year:
                    if self.lang == "fr":
                        facts.append(f"Collaboration récente: {year}")
                    else:
                        facts.append(f"Recent collaboration: {year}")

            # Co-invention facts
            elif edge_type == "co_invented" and weight > 1:
                if self.lang == "fr":
                    facts.append(f"{weight} brevets co-inventés")
                else:
                    facts.append(f"{weight} co-invented patents")

            # Citation facts
            elif edge_type in ("cites", "cites_patent") and weight > 1:
                if self.lang == "fr":
                    facts.append(f"{weight} citations")
                else:
                    facts.append(f"{weight} citations")

            # Evidence URLs
            evidence = edge.get("evidence", [])
            for ev in evidence[:1]:  # Only first evidence
                if ev.get("kind") == "url" and ev.get("url"):
                    facts.append(f"Source: {ev.get('label', 'Link')}")

        return facts

    def _generate_summary(
        self,
        target: TargetScore,
        explanations: List[PathExplanation]
    ) -> str:
        """Generate one-sentence summary."""
        name = target.target_label
        count = target.path_count
        best_hyp = target.best_hypothesis

        if self.lang == "fr":
            if best_hyp == Hypothesis.H1:
                return f"**{name}** : connexion directe établie ({count} chemin{'s' if count > 1 else ''})."
            elif best_hyp == Hypothesis.H2:
                return f"**{name}** : connexion indirecte via {count} chemin{'s' if count > 1 else ''}."
            else:
                return f"**{name}** : signal faible détecté ({count} chemin{'s' if count > 1 else ''})."
        else:
            if best_hyp == Hypothesis.H1:
                return f"**{name}**: direct connection established ({count} path{'s' if count > 1 else ''})."
            elif best_hyp == Hypothesis.H2:
                return f"**{name}**: indirect connection via {count} path{'s' if count > 1 else ''}."
            else:
                return f"**{name}**: weak signal detected ({count} path{'s' if count > 1 else ''})."

    def _generate_detailed(
        self,
        target: TargetScore,
        explanations: List[PathExplanation]
    ) -> str:
        """Generate multi-paragraph detailed explanation."""
        lines = []
        name = target.target_label

        # Introduction
        if self.lang == "fr":
            lines.append(f"## Analyse de la relation avec {name}\n")
            lines.append(f"Score total: **{target.total_score:.1f}** ({target.path_count} chemins trouvés)\n")
        else:
            lines.append(f"## Relationship Analysis: {name}\n")
            lines.append(f"Total score: **{target.total_score:.1f}** ({target.path_count} paths found)\n")

        # Group by hypothesis level
        h1_paths = [e for e in explanations if e.path.pattern.hypothesis == Hypothesis.H1]
        h2_paths = [e for e in explanations if e.path.pattern.hypothesis == Hypothesis.H2]
        h3_paths = [e for e in explanations if e.path.pattern.hypothesis == Hypothesis.H3]

        # H1 section
        if h1_paths:
            if self.lang == "fr":
                lines.append("### Connexions directes (H1)\n")
            else:
                lines.append("### Direct Connections (H1)\n")

            for exp in h1_paths:
                lines.append(f"- {exp.narrative}")
                if exp.key_facts:
                    lines.append(f"  - {', '.join(exp.key_facts)}")
            lines.append("")

        # H2 section
        if h2_paths:
            if self.lang == "fr":
                lines.append("### Connexions indirectes (H2)\n")
            else:
                lines.append("### Indirect Connections (H2)\n")

            for exp in h2_paths:
                lines.append(f"- {exp.narrative}")
                if exp.key_facts:
                    lines.append(f"  - {', '.join(exp.key_facts)}")
            lines.append("")

        # H3 section
        if h3_paths:
            if self.lang == "fr":
                lines.append("### Signaux faibles (H3)\n")
            else:
                lines.append("### Weak Signals (H3)\n")

            for exp in h3_paths[:5]:  # Limit to 5
                lines.append(f"- {exp.narrative}")
            if len(h3_paths) > 5:
                if self.lang == "fr":
                    lines.append(f"  *(et {len(h3_paths) - 5} autres...)*")
                else:
                    lines.append(f"  *(and {len(h3_paths) - 5} more...)*")
            lines.append("")

        return "\n".join(lines)

    def _generate_confidence_statement(self, target: TargetScore) -> str:
        """Generate confidence statement based on evidence quality."""
        best_ev = target.best_evidence
        best_hyp = target.best_hypothesis
        path_count = target.path_count

        if self.lang == "fr":
            if best_ev == EvidenceLevel.HARD and best_hyp == Hypothesis.H1:
                return "Confiance ÉLEVÉE: relation directe vérifiable."
            elif best_ev == EvidenceLevel.HARD or (best_hyp == Hypothesis.H2 and path_count >= 3):
                return "Confiance MOYENNE: plusieurs indices convergents."
            else:
                return "Confiance FAIBLE: signaux indirects à vérifier."
        else:
            if best_ev == EvidenceLevel.HARD and best_hyp == Hypothesis.H1:
                return "HIGH confidence: verifiable direct relationship."
            elif best_ev == EvidenceLevel.HARD or (best_hyp == Hypothesis.H2 and path_count >= 3):
                return "MEDIUM confidence: multiple converging indicators."
            else:
                return "LOW confidence: indirect signals require verification."


# =============================================================================
# Convenience Functions
# =============================================================================

def explain_paths(
    paths: List[FoundPath],
    lang: str = "fr"
) -> List[PathExplanation]:
    """
    Generate explanations for multiple paths.

    Args:
        paths: List of FoundPath instances.
        lang: Language ("fr" or "en").

    Returns:
        List of PathExplanation instances.
    """
    explainer = PathExplainer(lang)
    return [explainer.explain_path(p) for p in paths]


def explain_targets(
    targets: List[TargetScore],
    lang: str = "fr"
) -> List[TargetExplanation]:
    """
    Generate explanations for target entities.

    Args:
        targets: List of TargetScore instances.
        lang: Language ("fr" or "en").

    Returns:
        List of TargetExplanation instances.
    """
    explainer = PathExplainer(lang)
    return [explainer.explain_target(t) for t in targets]


def generate_report(
    targets: List[TargetScore],
    seed_name: str,
    lang: str = "fr"
) -> str:
    """
    Generate a complete markdown report.

    Args:
        targets: Ranked list of TargetScore instances.
        seed_name: Name of the seed person.
        lang: Language ("fr" or "en").

    Returns:
        Markdown-formatted report string.
    """
    explainer = PathExplainer(lang)
    lines = []

    # Title
    if lang == "fr":
        lines.append(f"# Rapport de diligence: {seed_name}\n")
        lines.append(f"Analyse des connexions avec {len(targets)} entités.\n")
    else:
        lines.append(f"# Due Diligence Report: {seed_name}\n")
        lines.append(f"Analysis of connections with {len(targets)} entities.\n")

    # Summary table
    if lang == "fr":
        lines.append("## Résumé des connexions\n")
        lines.append("| Rang | Entité | Type | Score | Niveau | Chemins |")
    else:
        lines.append("## Connection Summary\n")
        lines.append("| Rank | Entity | Type | Score | Level | Paths |")

    lines.append("|------|--------|------|-------|--------|--------|")

    for i, t in enumerate(targets[:20], 1):
        hyp = t.best_hypothesis.value if t.best_hypothesis else "?"
        lines.append(
            f"| {i} | {t.target_label} | {t.target_type} | "
            f"{t.total_score:.1f} | {hyp} | {t.path_count} |"
        )

    lines.append("")

    # Detailed sections for top targets
    if lang == "fr":
        lines.append("## Analyse détaillée\n")
    else:
        lines.append("## Detailed Analysis\n")

    for target in targets[:10]:  # Top 10 only
        explanation = explainer.explain_target(target)
        lines.append(explanation.detailed)
        lines.append(f"*{explanation.confidence_statement}*\n")
        lines.append("---\n")

    return "\n".join(lines)
