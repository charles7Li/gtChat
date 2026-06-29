from __future__ import annotations

import asyncio
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
from app.collectors import collect_xiaohongshu
from app.memory import SimpleMemory
from app.utils import load_latest_search_results
from app.workflow.evidence import build_evidence_pack
from app.workflow.router import route_from_state
from app.workflow.state import WorkflowState, create_initial_state
from app.workflow.trace import NODE_CONTRACTS, ProgressCallback, append_warning, run_node


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
    keyword = state.get("keyword") or (state.get("plan") or {}).get("keyword")
    state["memory_context"] = (memory or SimpleMemory()).load(keyword=keyword)
    return state


def collector_node(state: WorkflowState) -> WorkflowState:
    try:
        items = asyncio.run(
            collect_xiaohongshu(
                state.get("keyword", "宠物"),
                sort=state.get("sort", "popularity_descending"),
                time_filter=state.get("time_filter", ""),
                limit=state.get("deep_limit", 10),
            )
        )
        state["collector_result"] = {"status": "success", "source": "app.collectors.xiaohongshu_minimal", "count": len(items)}
        state["raw_items"] = items
        return state
    except Exception as exc:  # pragma: no cover - depends on local Playwright and login state
        append_warning(state, "collector_failed", f"Minimal collector failed: {exc}", "collect")

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
        state.get("time_filter", ""),
        "--deep",
        "--deep-limit",
        str(state.get("deep_limit", 10)),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=300)
        state["collector_result"] = {
            "status": "success" if completed.returncode == 0 else "failed",
            "source": "external_playwright_search",
            "command": command,
            "exit_code": completed.returncode,
            "stdout_excerpt": (completed.stdout or "")[:1000],
            "stderr_excerpt": (completed.stderr or "")[:1000],
        }
        if completed.returncode != 0:
            append_warning(state, "collector_failed", f"Collector exited with {completed.returncode}", "collect")
    except Exception as exc:  # pragma: no cover - depends on local Playwright
        state["collector_result"] = {"status": "failed", "source": "external_playwright_search", "command": command, "message": str(exc)}
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


def local_video_analyze_node(state: WorkflowState) -> WorkflowState:
    path = (state.get("plan") or {}).get("reference_video_path") or state.get("reference_video_path")
    if not path:
        raise ValueError("reference video route requires a video_analysis_brief.json path")
    brief_path = Path(path)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    state["reference_video_path"] = str(brief_path)
    state["video_analysis_brief"] = brief
    return state


def video_pattern_extract_node(state: WorkflowState) -> WorkflowState:
    brief = state.get("video_analysis_brief") or {}
    source = brief.get("source") or {}
    transcript = brief.get("transcript") or {}
    structure = brief.get("structure_analysis") or {}
    guidance = brief.get("replication_guidance") or {}
    style = brief.get("style_profile") or {}
    scenes = structure.get("scenes") or []
    topic = guidance.get("topic") or source.get("title") or "参考视频"
    scene_count = structure.get("total_scenes") or len(scenes)

    state["trend_analysis"] = {
        "top_topics": [topic],
        "hot_emotions": guidance.get("emotions") or [],
        "audience_pain_points": guidance.get("pain_points") or [],
        "high_engagement_reasons": [],
        "content_type_distribution": {"video": 1},
        "summary": f"Analyzed reference video brief with {scene_count} scenes and {transcript.get('word_count', 0)} transcript words.",
    }
    state["pattern_analysis"] = {
        "title_patterns": guidance.get("title_patterns") or ["reference-video result-first title"],
        "opening_patterns": guidance.get("opening_patterns") or ["first 3 seconds show the conflict or result"],
        "body_patterns": guidance.get("body_patterns") or ["scene sequence -> key action -> result proof"],
        "visual_patterns": style.get("visual_patterns") or ["reuse the strongest keyframe framing and pacing"],
        "interaction_patterns": guidance.get("interaction_patterns") or ["end with a low-friction remake prompt"],
        "replicable_templates": guidance.get("replicable_templates") or [
            f"{topic}: opening frame -> repeatable action steps -> differentiated result"
        ],
    }
    state["evidence_pack"] = {
        "run_id": state.get("run_id"),
        "keyword": topic,
        "item_count": 1,
        "top_items": [
            {
                "id": "reference_video",
                "title": topic,
                "body_excerpt": transcript.get("full_text", "")[:500],
                "metrics": {"total_engagement": 0},
                "detail_status": "video_brief",
            }
        ],
        "topic_candidates": [topic],
        "data_quality": {"total_raw": 1, "total_clean": 1, "quality_score": 100 if scene_count else 60},
    }
    state["data_quality"] = state["evidence_pack"]["data_quality"]
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


def run_workflow_legacy(user_query: str, output_dir: str | Path = "outputs/final_package") -> WorkflowState:
    state = create_initial_state(user_query)
    state = _run_workflow_node(state, "plan", plan_node)
    route = route_from_state(state)
    state["route"] = route
    if route == "reference_video_imitation_path":
        state = _run_workflow_node(state, "local_video_analyze", local_video_analyze_node)
        state = _run_workflow_node(state, "video_pattern_extract", video_pattern_extract_node)
        state = _run_workflow_node(state, "imitation_plan", imitation_plan_node)
        state = _run_workflow_node(state, "review", review_node)
        state = _run_workflow_node(state, "report", report_node, output_dir)
        return trace_writer_node(state, output_dir)

    state = _run_workflow_node(state, "memory_load", memory_load_node)

    if route == "full_pipeline_path":
        state = _run_workflow_node(state, "collect", collector_node)
        state = _run_workflow_node(state, "clean", cleaner_node)
        state = _run_workflow_node(state, "store", storage_node)
        state = _run_workflow_node(state, "trend_analyze", trend_analyze_node)
        state = _run_workflow_node(state, "pattern_extract", pattern_extract_node)
        state = _run_workflow_node(state, "evidence_pack", evidence_pack_node)
        state = _run_workflow_node(state, "imitation_plan", imitation_plan_node)
        state = _run_workflow_node(state, "review", review_node)
        state = _run_workflow_node(state, "report", report_node, output_dir)
        state = _run_workflow_node(state, "memory_write", memory_write_node)
        return trace_writer_node(state, output_dir)

    state = _run_workflow_node(state, "load_latest_search_results", load_latest_search_results_node)
    state = _run_workflow_node(state, "clean", cleaner_node)
    state = _run_workflow_node(state, "trend_analyze", trend_analyze_node)
    state = _run_workflow_node(state, "pattern_extract", pattern_extract_node)
    state = _run_workflow_node(state, "evidence_pack", evidence_pack_node)
    if route == "imitation_plan_path":
        state = _run_workflow_node(state, "imitation_plan", imitation_plan_node)
        state = _run_workflow_node(state, "review", review_node)
    state = _run_workflow_node(state, "report", report_node, output_dir)
    return trace_writer_node(state, output_dir)


def _run_workflow_node(state: WorkflowState, name: str, func, *args) -> WorkflowState:
    contract = NODE_CONTRACTS.get(name, {})
    return run_node(
        state,
        name,
        func,
        *args,
        before=contract.get("before"),
        after=contract.get("after"),
        on_error=contract.get("on_error"),
    )


def run_workflow(
    user_query: str,
    output_dir: str | Path = "outputs/final_package",
    progress_callback: ProgressCallback | None = None,
) -> WorkflowState:
    from app.workflow.langgraph_runner import run_workflow_langgraph

    return run_workflow_langgraph(user_query, output_dir, progress_callback=progress_callback)


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


