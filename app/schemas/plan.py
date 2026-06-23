from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionPlan:
    task_type: str = "trend_analysis_and_imitation_planning"
    route: str = "trend_report_path"
    platform: str = "xiaohongshu"
    keyword: str = "宠物"
    time_filter: str = "一周内"
    sort: str = "popularity_descending"
    deep_limit: int = 10
    need_collection: bool = False
    need_trend_analysis: bool = True
    need_pattern_extraction: bool = True
    need_imitation_planning: bool = False
    need_review: bool = False
    output_format: str = "markdown_report"
