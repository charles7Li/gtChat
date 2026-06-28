from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.workflow.graph import (
    cleaner_node,
    collector_node,
    evidence_pack_node,
    imitation_plan_node,
    load_latest_search_results_node,
    memory_load_node,
    memory_write_node,
    pattern_extract_node,
    plan_node,
    report_node,
    review_node,
    storage_node,
    trace_writer_node,
    trend_analyze_node,
)
from app.workflow.router import route_from_state
from app.workflow.state import WorkflowState, create_initial_state
from app.workflow.trace import ProgressCallback, NodeHook, require_state_keys, run_node, warn_dict_missing_keys, warn_missing_outputs


NODE_CONTRACTS: dict[str, dict[str, list[NodeHook]]] = {
    "plan": {
        "before": [require_state_keys("user_query")],
        "after": [warn_missing_outputs("plan", "route", "keyword", "platform", "time_filter", "sort", "deep_limit")],
    },
    "route": {
        "before": [require_state_keys("plan")],
        "after": [warn_missing_outputs("route")],
    },
    "memory_load": {
        "after": [warn_missing_outputs("memory_context"), warn_dict_missing_keys("memory_context", "index")],
    },
    "collect": {
        "before": [require_state_keys("keyword", "sort", "deep_limit")],
        "after": [warn_missing_outputs("raw_items")],
    },
    "load_latest_search_results": {
        "after": [warn_missing_outputs("raw_items")],
    },
    "clean": {
        "before": [require_state_keys("raw_items")],
        "after": [warn_missing_outputs("clean_items", "dropped_items", "data_quality")],
    },
    "trend_analyze": {
        "before": [require_state_keys("clean_items")],
        "after": [warn_missing_outputs("trend_analysis"), warn_dict_missing_keys("trend_analysis", "top_topics", "summary")],
    },
    "pattern_extract": {
        "before": [require_state_keys("clean_items", "trend_analysis")],
        "after": [warn_missing_outputs("pattern_analysis"), warn_dict_missing_keys("pattern_analysis", "replicable_templates")],
    },
    "evidence_pack": {
        "before": [require_state_keys("clean_items", "trend_analysis", "data_quality")],
        "after": [warn_missing_outputs("evidence_pack"), warn_dict_missing_keys("evidence_pack", "top_items")],
    },
    "imitation_plan": {
        "before": [require_state_keys("trend_analysis", "pattern_analysis", "evidence_pack")],
        "after": [warn_missing_outputs("imitation_plans")],
    },
    "review": {
        "before": [require_state_keys("imitation_plans")],
        "after": [warn_missing_outputs("review_result"), warn_dict_missing_keys("review_result", "overall_score")],
    },
    "report": {
        "before": [require_state_keys("trend_analysis", "pattern_analysis", "evidence_pack")],
        "after": [warn_missing_outputs("final_report", "report_path", "manifest_path")],
    },
}


def langgraph_available() -> bool:
    try:
        import langgraph.graph  # noqa: F401
    except ImportError:
        return False
    return True


def build_langgraph_workflow(
    output_dir: str | Path = "outputs/final_package",
    progress_callback: ProgressCallback | None = None,
):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("plan", _traced("plan", plan_node, progress_callback=progress_callback))
    graph.add_node("route", _traced("route", _route_node, progress_callback=progress_callback))
    graph.add_node("memory_load", _traced("memory_load", memory_load_node, progress_callback=progress_callback))
    graph.add_node("collect", _traced("collect", collector_node, progress_callback=progress_callback))
    graph.add_node("load_latest_search_results", _traced("load_latest_search_results", load_latest_search_results_node, progress_callback=progress_callback))
    graph.add_node("clean", _traced("clean", cleaner_node, progress_callback=progress_callback))
    graph.add_node("store", _traced("store", storage_node, progress_callback=progress_callback))
    graph.add_node("trend_analyze", _traced("trend_analyze", trend_analyze_node, progress_callback=progress_callback))
    graph.add_node("pattern_extract", _traced("pattern_extract", pattern_extract_node, progress_callback=progress_callback))
    graph.add_node("evidence_pack", _traced("evidence_pack", evidence_pack_node, progress_callback=progress_callback))
    graph.add_node("imitation_plan", _traced("imitation_plan", imitation_plan_node, progress_callback=progress_callback))
    graph.add_node("review", _traced("review", review_node, progress_callback=progress_callback))
    graph.add_node("report", _traced("report", report_node, output_dir, progress_callback=progress_callback))
    graph.add_node("memory_write", _traced("memory_write", memory_write_node, progress_callback=progress_callback))
    graph.add_node("trace", lambda state: trace_writer_node(state, output_dir))

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "route")
    graph.add_edge("route", "memory_load")
    graph.add_conditional_edges(
        "memory_load",
        _route_selector,
        {
            "full_pipeline_path": "collect",
            "imitation_plan_path": "load_latest_search_results",
            "trend_report_path": "load_latest_search_results",
        },
    )

    graph.add_edge("collect", "clean")
    graph.add_edge("load_latest_search_results", "clean")
    graph.add_conditional_edges(
        "clean",
        _after_clean_selector,
        {
            "full_pipeline_path": "store",
            "imitation_plan_path": "trend_analyze",
            "trend_report_path": "trend_analyze",
        },
    )
    graph.add_edge("store", "trend_analyze")
    graph.add_edge("trend_analyze", "pattern_extract")
    graph.add_edge("pattern_extract", "evidence_pack")
    graph.add_conditional_edges(
        "evidence_pack",
        _after_evidence_selector,
        {
            "full_pipeline_path": "imitation_plan",
            "imitation_plan_path": "imitation_plan",
            "trend_report_path": "report",
        },
    )
    graph.add_edge("imitation_plan", "review")
    graph.add_edge("review", "report")
    graph.add_conditional_edges(
        "report",
        _after_report_selector,
        {
            "full_pipeline_path": "memory_write",
            "done": "trace",
        },
    )
    graph.add_edge("memory_write", "trace")
    graph.add_edge("trace", END)
    return graph.compile()


def run_workflow_langgraph(
    user_query: str,
    output_dir: str | Path = "outputs/final_package",
    progress_callback: ProgressCallback | None = None,
) -> WorkflowState:
    app = build_langgraph_workflow(output_dir, progress_callback=progress_callback)
    result = app.invoke(create_initial_state(user_query))
    return result


def _traced(
    name: str,
    func: Callable[..., WorkflowState],
    *args,
    progress_callback: ProgressCallback | None = None,
):
    def node(state: WorkflowState) -> WorkflowState:
        contract = NODE_CONTRACTS.get(name, {})
        return run_node(
            state,
            name,
            func,
            *args,
            before=contract.get("before"),
            after=contract.get("after"),
            progress_callback=progress_callback,
        )

    return node


def _route_node(state: WorkflowState) -> WorkflowState:
    state["route"] = route_from_state(state)
    return state


def _route_selector(state: WorkflowState) -> str:
    return route_from_state(state)


def _after_clean_selector(state: WorkflowState) -> str:
    return route_from_state(state)


def _after_evidence_selector(state: WorkflowState) -> str:
    return route_from_state(state)


def _after_report_selector(state: WorkflowState) -> str:
    if route_from_state(state) == "full_pipeline_path":
        return "full_pipeline_path"
    return "done"
