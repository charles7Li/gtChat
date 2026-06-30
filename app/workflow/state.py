from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4


class WorkflowState(TypedDict, total=False):
    run_id: str
    user_query: str
    plan: dict
    route: str
    keyword: str
    platform: str
    time_filter: str
    sort: str
    deep_limit: int
    raw_items: list
    clean_items: list
    dropped_items: list
    data_quality: dict
    evidence_pack: dict
    trend_analysis: dict
    pattern_analysis: dict
    imitation_plans: list
    review_result: dict
    final_report: str
    report_path: str
    manifest_path: str
    trace_path: str
    agent_trace: dict
    trace_nodes: list
    errors: list
    warnings: list
    memory_context: dict
    reference_video_path: str
    reference_video_source_path: str
    video_analysis_brief: dict
    commercial_import_summary: dict


def create_initial_state(user_query: str) -> WorkflowState:
    return {
        "run_id": _new_run_id(),
        "user_query": user_query,
        "errors": [],
        "warnings": [],
        "trace_nodes": [],
    }


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid4().hex[:8]}"
