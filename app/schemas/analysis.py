from __future__ import annotations

from typing import TypedDict


class AnalysisResult(TypedDict, total=False):
    top_topics: list[str]
    hot_emotions: list[str]
    audience_pain_points: list[str]
    high_engagement_reasons: list[dict]
    content_type_distribution: dict[str, int]
    summary: str
