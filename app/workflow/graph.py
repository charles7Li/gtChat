from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from app.agents import (
    ImitationPlannerAgent,
    PatternExtractorAgent,
    PlanAgent,
    ReportWriterAgent,
    ReviewAgent,
    TrendAnalyzerAgent,
)
from app.memory import SimpleMemory
from app.utils import load_latest_search_results, parse_count, parse_timestamp_ms
from app.workflow.router import route_from_state


class WorkflowState(TypedDict, total=False):
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
    trend_analysis: dict
    pattern_analysis: dict
    imitation_plans: list
    review_result: dict
    final_report: str
    agent_trace: dict
    errors: list
    memory_context: dict


def plan_node(state: WorkflowState) -> WorkflowState:
    plan = PlanAgent().run(state.get("user_query", ""))
    state.update(
        {
            "plan": plan,
            "route": plan["route"],
            "keyword": plan["keyword"],
            "platform": plan["platform"],
            "time_filter": plan["time_filter"],
            "sort": plan["sort"],
            "deep_limit": plan["deep_limit"],
        }
    )
    return state


def memory_load_node(state: WorkflowState, memory: SimpleMemory | None = None) -> WorkflowState:
    state["memory_context"] = (memory or SimpleMemory()).load()
    return state


def collector_node(state: WorkflowState) -> WorkflowState:
    script = Path.home() / ".xiaohongshu-cli" / "playwright_search.py"
    if script.exists():
        command = [
            "python",
            str(script),
            "--keyword",
            state.get("keyword", "宠物"),
            "--sort",
            state.get("sort", "popularity_descending"),
            "--time-filter",
            state.get("time_filter", "一周内"),
            "--deep",
            "--deep-limit",
            str(state.get("deep_limit", 10)),
        ]
        try:
            subprocess.run(command, check=False, timeout=300)
        except Exception as exc:  # pragma: no cover - depends on local Playwright
            state.setdefault("errors", []).append(f"collector failed: {exc}")
    return load_latest_search_results_node(state)


def load_latest_search_results_node(state: WorkflowState, search_dir: str | Path | None = None) -> WorkflowState:
    state["raw_items"] = load_latest_search_results(search_dir) if search_dir else load_latest_search_results()
    return state


def cleaner_node(state: WorkflowState) -> WorkflowState:
    state["clean_items"] = clean_items(state.get("raw_items", []))
    return state


def storage_node(state: WorkflowState, output_dir: str | Path = "outputs/storage") -> WorkflowState:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "clean_items.json").write_text(
        json.dumps(state.get("clean_items", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state


def trend_analyze_node(state: WorkflowState) -> WorkflowState:
    state["trend_analysis"] = TrendAnalyzerAgent().run(state.get("clean_items", []))
    return state


def pattern_extract_node(state: WorkflowState) -> WorkflowState:
    state["pattern_analysis"] = PatternExtractorAgent().run(
        state.get("clean_items", []),
        state.get("trend_analysis", {}),
    )
    return state


def imitation_plan_node(state: WorkflowState) -> WorkflowState:
    state["imitation_plans"] = ImitationPlannerAgent().run(
        state.get("trend_analysis", {}),
        state.get("pattern_analysis", {}),
    )
    return state


def review_node(state: WorkflowState) -> WorkflowState:
    state["review_result"] = ReviewAgent().run(state.get("imitation_plans", []))
    return state


def report_node(state: WorkflowState, output_dir: str | Path = "outputs/final_package") -> WorkflowState:
    return ReportWriterAgent(output_dir).run(state)


def memory_write_node(state: WorkflowState, memory: SimpleMemory | None = None) -> WorkflowState:
    (memory or SimpleMemory()).write(state)
    return state


def trace_writer_node(state: WorkflowState, output_dir: str | Path = "outputs/final_package") -> WorkflowState:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    route = state.get("route", "trend_report_path")
    trace = {
        "user_query": state.get("user_query", ""),
        "route": route,
        "selected_agents": _selected_agents(route),
        "execution_path": _execution_path(route),
        "final_score": (state.get("review_result") or {}).get("overall_score"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state["agent_trace"] = trace
    (directory / "agent_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def clean_items(raw_items: list[dict]) -> list[dict]:
    cleaned = []
    for raw in raw_items:
        title = raw.get("title") or raw.get("note_title") or ""
        body = raw.get("body_text") or raw.get("desc") or raw.get("content") or ""
        if not title and not body:
            continue
        cleaned.append(
            {
                "id": str(raw.get("id") or raw.get("note_id") or raw.get("url") or ""),
                "title": title,
                "body_text": body,
                "tags": raw.get("tags") or raw.get("tag_list") or [],
                "metrics": {
                    "liked_count": parse_count(raw.get("liked_count") or raw.get("likes")),
                    "collected_count": parse_count(raw.get("collected_count") or raw.get("collects")),
                    "comment_count": parse_count(raw.get("comment_count") or raw.get("comments")),
                },
                "content_type": raw.get("content_type") or raw.get("type") or "image_note",
                "image_count": parse_count(raw.get("image_count") or len(raw.get("images") or [])),
                "author": raw.get("author") or raw.get("nickname") or "",
                "url": raw.get("url") or raw.get("link") or "",
                "created_at": parse_timestamp_ms(raw.get("created_at") or raw.get("time") or raw.get("timestamp")),
            }
        )
    return cleaned


def run_workflow(user_query: str, output_dir: str | Path = "outputs/final_package") -> WorkflowState:
    state: WorkflowState = {"user_query": user_query, "errors": []}
    state = plan_node(state)
    route = route_from_state(state)
    state["route"] = route
    state = memory_load_node(state)

    if route == "full_pipeline_path":
        state = collector_node(state)
        state = cleaner_node(state)
        state = storage_node(state)
        state = trend_analyze_node(state)
        state = pattern_extract_node(state)
        state = imitation_plan_node(state)
        state = review_node(state)
        state = report_node(state, output_dir)
        state = memory_write_node(state)
        return trace_writer_node(state, output_dir)

    state = load_latest_search_results_node(state)
    state = cleaner_node(state)
    state = trend_analyze_node(state)
    state = pattern_extract_node(state)
    if route == "imitation_plan_path":
        state = imitation_plan_node(state)
        state = review_node(state)
    state = report_node(state, output_dir)
    return trace_writer_node(state, output_dir)


def _selected_agents(route: str) -> list[str]:
    agents = ["TrendAnalyzerAgent", "PatternExtractorAgent"]
    if route in {"imitation_plan_path", "full_pipeline_path"}:
        agents.extend(["ImitationPlannerAgent", "ReviewAgent"])
    agents.append("ReportWriterAgent")
    return agents


def _execution_path(route: str) -> list[str]:
    if route == "full_pipeline_path":
        return [
            "plan",
            "memory_load",
            "collect",
            "clean",
            "store",
            "trend_analyze",
            "pattern_extract",
            "imitation_plan",
            "review",
            "report",
            "memory_write",
            "trace",
        ]
    if route == "imitation_plan_path":
        return [
            "plan",
            "memory_load",
            "load_latest_search_results",
            "clean",
            "trend_analyze",
            "pattern_extract",
            "imitation_plan",
            "review",
            "report",
            "trace",
        ]
    return [
        "plan",
        "memory_load",
        "load_latest_search_results",
        "clean",
        "trend_analyze",
        "pattern_extract",
        "report",
        "trace",
    ]
