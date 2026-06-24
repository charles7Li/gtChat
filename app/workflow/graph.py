from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.agents import (
    ImitationPlannerAgent,
    PatternExtractorAgent,
    PlanAgent,
    ReportWriterAgent,
    ReviewAgent,
    TrendAnalyzerAgent,
)
from app.cleaner import clean_items as clean_notes
from app.cleaner import clean_items_with_metadata
from app.memory import SimpleMemory
from app.utils import load_latest_search_results
from app.workflow.evidence import build_evidence_pack
from app.workflow.router import route_from_state
from app.workflow.state import WorkflowState, create_initial_state
from app.workflow.trace import append_warning, run_traced_node


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
    if not script.exists():
        append_warning(state, "collector_missing", f"Collector script not found: {script}", "collect")
        return load_latest_search_results_node(state)

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
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=300)
        state["collector_result"] = {
            "status": "success" if completed.returncode == 0 else "failed",
            "command": command,
            "exit_code": completed.returncode,
            "stdout_excerpt": (completed.stdout or "")[:1000],
            "stderr_excerpt": (completed.stderr or "")[:1000],
        }
        if completed.returncode != 0:
            append_warning(state, "collector_failed", f"Collector exited with {completed.returncode}", "collect")
    except Exception as exc:  # pragma: no cover - depends on local Playwright
        state["collector_result"] = {"status": "failed", "command": command, "message": str(exc)}
        append_warning(state, "collector_failed", str(exc), "collect")
    return load_latest_search_results_node(state)


def load_latest_search_results_node(state: WorkflowState, search_dir: str | Path | None = None) -> WorkflowState:
    state["raw_items"] = load_latest_search_results(search_dir) if search_dir else load_latest_search_results()
    return state


def cleaner_node(state: WorkflowState) -> WorkflowState:
    result = clean_items_with_metadata(state.get("raw_items", []))
    state["clean_items"] = result["clean_items"]
    state["dropped_items"] = result["dropped_items"]
    state["data_quality"] = result["data_quality"]
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


def evidence_pack_node(state: WorkflowState) -> WorkflowState:
    state["evidence_pack"] = build_evidence_pack(state)
    return state


def imitation_plan_node(state: WorkflowState) -> WorkflowState:
    state["imitation_plans"] = ImitationPlannerAgent().run(
        state.get("trend_analysis", {}),
        state.get("pattern_analysis", {}),
        state.get("evidence_pack", {}),
        state.get("memory_context", {}),
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
        "run_id": state.get("run_id"),
        "user_query": state.get("user_query", ""),
        "route": route,
        "selected_agents": _selected_agents(route),
        "execution_path": _execution_path(route),
        "nodes": state.get("trace_nodes", []),
        "data_quality": state.get("data_quality", {}),
        "final_score": (state.get("review_result") or {}).get("overall_score"),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state["agent_trace"] = trace
    trace_path = directory / "agent_trace.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    state["trace_path"] = str(trace_path)
    return state


def clean_items(raw_items: list[dict]) -> list[dict]:
    return clean_notes(raw_items)


def run_workflow(user_query: str, output_dir: str | Path = "outputs/final_package") -> WorkflowState:
    state = create_initial_state(user_query)
    state = run_traced_node(state, "plan", plan_node)
    route = route_from_state(state)
    state["route"] = route
    state = run_traced_node(state, "memory_load", memory_load_node)

    if route == "full_pipeline_path":
        state = run_traced_node(state, "collect", collector_node)
        state = run_traced_node(state, "clean", cleaner_node)
        state = run_traced_node(state, "store", storage_node)
        state = run_traced_node(state, "trend_analyze", trend_analyze_node)
        state = run_traced_node(state, "pattern_extract", pattern_extract_node)
        state = run_traced_node(state, "evidence_pack", evidence_pack_node)
        state = run_traced_node(state, "imitation_plan", imitation_plan_node)
        state = run_traced_node(state, "review", review_node)
        state = run_traced_node(state, "report", report_node, output_dir)
        state = run_traced_node(state, "memory_write", memory_write_node)
        return trace_writer_node(state, output_dir)

    state = run_traced_node(state, "load_latest_search_results", load_latest_search_results_node)
    state = run_traced_node(state, "clean", cleaner_node)
    state = run_traced_node(state, "trend_analyze", trend_analyze_node)
    state = run_traced_node(state, "pattern_extract", pattern_extract_node)
    state = run_traced_node(state, "evidence_pack", evidence_pack_node)
    if route == "imitation_plan_path":
        state = run_traced_node(state, "imitation_plan", imitation_plan_node)
        state = run_traced_node(state, "review", review_node)
    state = run_traced_node(state, "report", report_node, output_dir)
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
            "evidence_pack",
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
            "evidence_pack",
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
        "evidence_pack",
        "report",
        "trace",
    ]
