from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from app.llm import finish_llm_trace, start_llm_trace
from app.workflow.state import WorkflowState

NodeFunc = Callable[..., WorkflowState]
NodeHook = Callable[[WorkflowState, "NodeContext"], None]
ProgressCallback = Callable[[dict], None]


@dataclass
class NodeContext:
    name: str
    started_at: str
    input_summary: dict
    warning_count: int
    metadata: dict = field(default_factory=dict)


def append_warning(state: WorkflowState, code: str, message: str, node: str | None = None) -> None:
    state.setdefault("warnings", []).append({"code": code, "message": message, "node": node})


def append_error(state: WorkflowState, code: str, message: str, node: str | None = None) -> None:
    state.setdefault("errors", []).append({"code": code, "message": message, "node": node})


def run_traced_node(
    state: WorkflowState,
    name: str,
    func: NodeFunc,
    *args,
    **kwargs,
) -> WorkflowState:
    return run_node(state, name, func, *args, **kwargs)


def run_node(
    state: WorkflowState,
    name: str,
    func: NodeFunc,
    *args,
    before: list[NodeHook] | None = None,
    after: list[NodeHook] | None = None,
    on_error: list[NodeHook] | None = None,
    progress_callback: ProgressCallback | None = None,
    **kwargs,
) -> WorkflowState:
    started_at = _now()
    started = perf_counter()
    context = NodeContext(
        name=name,
        started_at=started_at,
        input_summary=summarize_state(state),
        warning_count=len(state.get("warnings", [])),
    )
    llm_token = start_llm_trace()
    _emit_progress(
        progress_callback,
        {
            "phase": "start",
            "name": name,
            "started_at": started_at,
            "input_summary": context.input_summary,
        },
    )

    try:
        for hook in before or []:
            hook(state, context)
        new_state = func(state, *args, **kwargs)
        for hook in after or []:
            hook(new_state, context)
    except Exception as exc:
        llm_events = finish_llm_trace(llm_token)
        append_error(state, "node_failed", str(exc), name)
        for hook in on_error or []:
            hook(state, context)
        node = {
            "name": name,
            "status": "failed",
            "started_at": started_at,
            "ended_at": _now(),
            "duration_ms": _elapsed_ms(started),
            "input_summary": context.input_summary,
            "output_summary": summarize_state(state),
            "error": str(exc),
        }
        if llm_events:
            node["llm_events"] = llm_events
        _append_trace_node(state, node)
        _emit_progress(progress_callback, {"phase": "failed", **node})
        raise

    llm_events = finish_llm_trace(llm_token)
    status = "warning" if len(new_state.get("warnings", [])) > context.warning_count else "success"
    node = {
        "name": name,
        "status": status,
        "started_at": started_at,
        "ended_at": _now(),
        "duration_ms": _elapsed_ms(started),
        "input_summary": context.input_summary,
        "output_summary": summarize_state(new_state),
    }
    if llm_events:
        node["llm_events"] = llm_events
    _append_trace_node(new_state, node)
    _emit_progress(progress_callback, {"phase": "finish", **node})
    return new_state


def require_state_keys(*keys: str) -> NodeHook:
    def hook(state: WorkflowState, context: NodeContext) -> None:
        missing = [key for key in keys if key not in state]
        if missing:
            raise ValueError(f"{context.name} missing required state keys: {', '.join(missing)}")

    return hook


def warn_missing_outputs(*keys: str) -> NodeHook:
    def hook(state: WorkflowState, context: NodeContext) -> None:
        for key in keys:
            if key not in state:
                append_warning(state, "node_missing_output", f"{context.name} did not set state['{key}']", context.name)

    return hook


def warn_dict_missing_keys(state_key: str, *keys: str) -> NodeHook:
    def hook(state: WorkflowState, context: NodeContext) -> None:
        value = state.get(state_key)
        if not isinstance(value, dict):
            append_warning(state, "node_invalid_output", f"{context.name} output state['{state_key}'] is not a dict", context.name)
            return
        missing = [key for key in keys if key not in value or value.get(key) in (None, "", [], {})]
        if missing:
            append_warning(
                state,
                "node_incomplete_output",
                f"{context.name} output state['{state_key}'] missing useful keys: {', '.join(missing)}",
                context.name,
            )

    return hook


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
    if state.get("memory_context"):
        summary["memory_runs"] = len(state["memory_context"].get("keyword_runs") or state["memory_context"].get("recent_runs") or [])
    return {key: value for key, value in summary.items() if value is not None}


def _append_trace_node(state: WorkflowState, node: dict) -> None:
    state.setdefault("trace_nodes", []).append(node)


def _emit_progress(progress_callback: ProgressCallback | None, event: dict) -> None:
    if progress_callback is None:
        return
    progress_callback(event)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
