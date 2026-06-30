from __future__ import annotations


DEFAULT_ROUTE_BUDGET_MS = {
    "trend_report_path": 8000,
    "imitation_plan_path": 12000,
    "full_pipeline_path": 30000,
    "reference_video_imitation_path": 20000,
    "commercial_data_analysis_path": 5000,
}


def build_performance_summary(trace_nodes: list[dict], *, route: str, budget_ms: int | None = None) -> dict:
    node_timings = [
        {"name": node.get("name", ""), "status": node.get("status", ""), "duration_ms": _int(node.get("duration_ms"))}
        for node in trace_nodes
    ]
    llm_events = [event for node in trace_nodes for event in node.get("llm_events", []) if isinstance(event, dict)]
    llm_total_ms = sum(_int(event.get("latency_ms")) for event in llm_events)
    node_total_ms = sum(item["duration_ms"] for item in node_timings)
    budget = budget_ms if budget_ms is not None else DEFAULT_ROUTE_BUDGET_MS.get(route, 10000)
    slowest = max(node_timings, key=lambda item: item["duration_ms"], default={"name": "", "duration_ms": 0, "status": ""})
    return {
        "workflow_total_ms": node_total_ms,
        "node_total_ms": node_total_ms,
        "llm_total_ms": llm_total_ms,
        "tool_total_ms": 0,
        "artifact_total_ms": 0,
        "overhead_ms": 0,
        "slowest_node": slowest,
        "budget_ms": budget,
        "budget_passed": node_total_ms <= budget,
        "node_timings": node_timings,
        "llm_events": len(llm_events),
    }


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
