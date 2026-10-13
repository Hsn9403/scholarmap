#!/usr/bin/env python3
"""
Scoring system for path-based evidence in KOL networks.

This module provides:
- Path scoring based on evidence level, path length, and edge weights
- Aggregation of multiple paths to the same target
- Ranking of targets by relationship strength
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.logger import logger
from .schema import EvidenceLevel, Hypothesis
from .path_finder import FoundPath


# =============================================================================
# Scoring Configuration
# =============================================================================

# Base scores by evidence level
EVIDENCE_BASE_SCORES = {
    EvidenceLevel.HARD: 100.0,
    EvidenceLevel.MEDIUM: 50.0,
    EvidenceLevel.SOFT: 20.0,
}

# Multiplier by hypothesis level (H1 > H2 > H3)
HYPOTHESIS_MULTIPLIERS = {
    Hypothesis.H1: 1.5,
    Hypothesis.H2: 1.0,
    Hypothesis.H3: 0.6,
}

# Decay factor per edge (longer paths = weaker signal)
PATH_LENGTH_DECAY = 0.85


@dataclass
class ScoredPath:
    """
    A path with its calculated score.

    Attributes:
        path: The original FoundPath.
        final_score: Computed score after all factors.
        score_breakdown: Dict explaining score components.
    """
    path: FoundPath
    final_score: float
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    @property
    def target_id(self) -> str:
        return self.path.target_id

    @property
    def target_label(self) -> str:
        return self.path.target_label

    @property
    def pattern_id(self) -> str:
        return self.path.pattern.pattern_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            **self.path.to_dict(),
            "final_score": round(self.final_score, 2),
            "score_breakdown": {k: round(v, 2) for k, v in self.score_breakdown.items()},
        }


@dataclass
class TargetScore:
    """
    Aggregated score for a target entity.

    Combines scores from all paths leading to this target.

    Attributes:
        target_id: ID of the target node.
        target_label: Display name.
        target_type: Node type (corporate, institution, person).
        total_score: Sum of all path scores.
        max_score: Highest single path score.
        path_count: Number of distinct paths.
        paths: List of scored paths to this target.
        best_hypothesis: Strongest hypothesis level found.
        best_evidence: Strongest evidence level found.
    """
    target_id: str
    target_label: str
    target_type: str
    total_score: float = 0.0
    max_score: float = 0.0
    path_count: int = 0
    paths: List[ScoredPath] = field(default_factory=list)
    best_hypothesis: Optional[Hypothesis] = None
    best_evidence: Optional[EvidenceLevel] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_id": self.target_id,
            "target_label": self.target_label,
            "target_type": self.target_type,
            "total_score": round(self.total_score, 2),
            "max_score": round(self.max_score, 2),
            "path_count": self.path_count,
            "best_hypothesis": self.best_hypothesis.value if self.best_hypothesis else None,
            "best_evidence": self.best_evidence.value if self.best_evidence else None,
            "paths": [p.to_dict() for p in self.paths],
        }


class PathScorer:
    """
    Scores and ranks paths by relationship strength.
    """

    def __init__(
        self,
        evidence_scores: Optional[Dict[EvidenceLevel, float]] = None,
        hypothesis_multipliers: Optional[Dict[Hypothesis, float]] = None,
        length_decay: float = PATH_LENGTH_DECAY,
    ):
        """
        Initialize scorer with custom weights if desired.

        Args:
            evidence_scores: Base scores by evidence level.
            hypothesis_multipliers: Multipliers by hypothesis.
            length_decay: Decay factor per edge in path.
        """
        self.evidence_scores = evidence_scores or EVIDENCE_BASE_SCORES
        self.hypothesis_multipliers = hypothesis_multipliers or HYPOTHESIS_MULTIPLIERS
        self.length_decay = length_decay

    def score_path(self, path: FoundPath) -> ScoredPath:
        """
        Calculate final score for a single path.

        Score formula:
            base_score = EVIDENCE_BASE_SCORES[evidence_level]
            hypothesis_mult = HYPOTHESIS_MULTIPLIERS[hypothesis]
            length_decay = DECAY ^ (path_length - 1)
            raw_bonus = log(1 + raw_score) * 5  # Bonus from edge weights

            final = base_score * hypothesis_mult * length_decay + raw_bonus

        Args:
            path: The FoundPath to score.

        Returns:
            ScoredPath with calculated score.
        """
        pattern = path.pattern

        # Base score from evidence level
        base_score = self.evidence_scores.get(pattern.evidence_level, 20.0)

        # Hypothesis multiplier
        hyp_mult = self.hypothesis_multipliers.get(pattern.hypothesis, 1.0)

        # Path length decay (longer = weaker)
        length = path.path_length
        length_mult = self.length_decay ** max(0, length - 1)

        # Bonus from raw edge weights (logarithmic to avoid runaway)
        import math
        raw_bonus = math.log(1 + path.raw_score) * 5

        # Final score
        final_score = (base_score * hyp_mult * length_mult) + raw_bonus

        breakdown = {
            "base_score": base_score,
            "hypothesis_multiplier": hyp_mult,
            "length_decay": length_mult,
            "raw_bonus": raw_bonus,
        }

        return ScoredPath(
            path=path,
            final_score=final_score,
            score_breakdown=breakdown,
        )

    def score_paths(self, paths: List[FoundPath]) -> List[ScoredPath]:
        """
        Score multiple paths.

        Args:
            paths: List of FoundPath instances.

        Returns:
            List of ScoredPath instances, sorted by score descending.
        """
        scored = [self.score_path(p) for p in paths]
        scored.sort(key=lambda x: x.final_score, reverse=True)
        return scored

    def aggregate_by_target(
        self,
        scored_paths: List[ScoredPath],
        min_score: float = 0.0
    ) -> List[TargetScore]:
        """
        Aggregate paths by target node.

        Args:
            scored_paths: List of ScoredPath instances.
            min_score: Minimum total score to include target.

        Returns:
            List of TargetScore instances, sorted by total_score descending.
        """
        by_target: Dict[str, TargetScore] = {}

        for sp in scored_paths:
            target_id = sp.target_id

            if target_id not in by_target:
                by_target[target_id] = TargetScore(
                    target_id=target_id,
                    target_label=sp.target_label,
                    target_type=sp.path.target_type,
                )

            ts = by_target[target_id]
            ts.paths.append(sp)
            ts.total_score += sp.final_score
            ts.max_score = max(ts.max_score, sp.final_score)
            ts.path_count += 1

            # Track best hypothesis/evidence
            hyp = sp.path.pattern.hypothesis
            ev = sp.path.pattern.evidence_level

            if ts.best_hypothesis is None or _hypothesis_rank(hyp) > _hypothesis_rank(ts.best_hypothesis):
                ts.best_hypothesis = hyp

            if ts.best_evidence is None or _evidence_rank(ev) > _evidence_rank(ts.best_evidence):
                ts.best_evidence = ev

        # Filter and sort
        results = [ts for ts in by_target.values() if ts.total_score >= min_score]
        results.sort(key=lambda x: x.total_score, reverse=True)

        return results

    def rank_targets(
        self,
        paths: List[FoundPath],
        min_score: float = 0.0,
        top_n: Optional[int] = None
    ) -> List[TargetScore]:
        """
        Score paths and rank targets by total relationship strength.

        Convenience method combining score_paths and aggregate_by_target.

        Args:
            paths: List of FoundPath instances.
            min_score: Minimum total score to include.
            top_n: Limit to top N targets (None = all).

        Returns:
            List of TargetScore instances.
        """
        scored = self.score_paths(paths)
        aggregated = self.aggregate_by_target(scored, min_score)

        if top_n:
            aggregated = aggregated[:top_n]

        return aggregated


def _hypothesis_rank(hyp: Hypothesis) -> int:
    """Higher rank = stronger hypothesis."""
    return {Hypothesis.H1: 3, Hypothesis.H2: 2, Hypothesis.H3: 1}.get(hyp, 0)


def _evidence_rank(ev: EvidenceLevel) -> int:
    """Higher rank = stronger evidence."""
    return {EvidenceLevel.HARD: 3, EvidenceLevel.MEDIUM: 2, EvidenceLevel.SOFT: 1}.get(ev, 0)


# =============================================================================
# Convenience Functions
# =============================================================================

def score_and_rank(
    paths: List[FoundPath],
    min_score: float = 0.0,
    top_n: Optional[int] = None
) -> List[TargetScore]:
    """
    Score paths and rank targets (convenience function).

    Args:
        paths: List of FoundPath instances.
        min_score: Minimum score threshold.
        top_n: Limit results.

    Returns:
        List of TargetScore instances.
    """
    scorer = PathScorer()
    return scorer.rank_targets(paths, min_score, top_n)


def get_top_connections(
    paths: List[FoundPath],
    target_type: Optional[str] = None,
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    Get top connected entities as simple dicts.

    Args:
        paths: List of FoundPath instances.
        target_type: Filter by type ("corporate", "institution", etc).
        top_n: Number of results.

    Returns:
        List of dicts with target info and scores.
    """
    targets = score_and_rank(paths)

    if target_type:
        targets = [t for t in targets if t.target_type == target_type]

    return [t.to_dict() for t in targets[:top_n]]
