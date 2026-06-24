from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from app.workflow.state import WorkflowState


def append_warning(state: WorkflowState, code: str, message: str, node: str | None = None) -> None:
    state.setdefault("warnings", []).append({"code": code, "message": message, "node": node})


def append_error(state: WorkflowState, code: str, message: str, node: str | None = None) -> None:
    state.setdefault("errors", []).append({"code": code, "message": message, "node": node})


def run_traced_node(
    state: WorkflowState,
    name: str,
    func: Callable[..., WorkflowState],
    *args,
    **kwargs,
) -> WorkflowState:
    started_at = _now()
    started = perf_counter()
    warning_count = len(state.get("warnings", []))
    input_summary = summarize_state(state)

    try:
        new_state = func(state, *args, **kwargs)
    except Exception as exc:
        append_error(state, "node_failed", str(exc), name)
        _append_trace_node(
            state,
            {
                "name": name,
                "status": "failed",
                "started_at": started_at,
                "ended_at": _now(),
                "duration_ms": _elapsed_ms(started),
                "input_summary": input_summary,
                "output_summary": summarize_state(state),
                "error": str(exc),
            },
        )
        raise

    status = "warning" if len(new_state.get("warnings", [])) > warning_count else "success"
    _append_trace_node(
        new_state,
        {
            "name": name,
            "status": status,
            "started_at": started_at,
            "ended_at": _now(),
            "duration_ms": _elapsed_ms(started),
            "input_summary": input_summary,
            "output_summary": summarize_state(new_state),
        },
    )
    return new_state


def summarize_state(state: WorkflowState) -> dict:
    summary = {
        "route": state.get("route"),
        "keyword": state.get("keyword"),
    }
    for key in ("raw_items", "clean_items", "dropped_items", "imitation_plans"):
        if key in state:
            summary[key] = len(state.get(key) or [])
    if state.get("data_quality"):
        summary["quality_score"] = state["data_quality"].get("quality_score")
    if state.get("review_result"):
        summary["final_score"] = state["review_result"].get("overall_score")
    if state.get("evidence_pack"):
        summary["evidence_items"] = len(state["evidence_pack"].get("top_items", []))
    return {key: value for key, value in summary.items() if value is not None}


def _append_trace_node(state: WorkflowState, node: dict) -> None:
    state.setdefault("trace_nodes", []).append(node)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
