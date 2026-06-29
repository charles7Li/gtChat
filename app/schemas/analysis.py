from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel


class AnalysisResult(TypedDict, total=False):
    top_topics: list[str]
    hot_emotions: list[str]
    audience_pain_points: list[str]
    high_engagement_reasons: list[dict]
    content_type_distribution: dict[str, int]
    summary: str


class PatternExtractionResult(BaseModel):
    title_patterns: list[str]
    opening_patterns: list[str]
    body_patterns: list[str]
    visual_patterns: list[str]
    interaction_patterns: list[str]
    replicable_templates: list[str]


class ReviewScores(BaseModel):
    trend_relevance: int
    platform_fit: int
    shooting_feasibility: int
    originality: int
    conversion_potential: int


class ReviewResult(BaseModel):
    overall_score: int
    scores: ReviewScores
    best_plan_index: int | None
    issues: list[str]
    revision_suggestions: list[str]
