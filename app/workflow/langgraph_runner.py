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
from app.workflow.trace import run_traced_node


def langgraph_available() -> bool:
    try:
        import langgraph.graph  # noqa: F401
    except ImportError:
        return False
    return True


def build_langgraph_workflow(output_dir: str | Path = "outputs/final_package"):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("plan", _traced("plan", plan_node))
    graph.add_node("route", _traced("route", _route_node))
    graph.add_node("memory_load", _traced("memory_load", memory_load_node))
    graph.add_node("collect", _traced("collect", collector_node))
    graph.add_node("load_latest_search_results", _traced("load_latest_search_results", load_latest_search_results_node))
    graph.add_node("clean", _traced("clean", cleaner_node))
    graph.add_node("store", _traced("store", storage_node))
    graph.add_node("trend_analyze", _traced("trend_analyze", trend_analyze_node))
    graph.add_node("pattern_extract", _traced("pattern_extract", pattern_extract_node))
    graph.add_node("evidence_pack", _traced("evidence_pack", evidence_pack_node))
    graph.add_node("imitation_plan", _traced("imitation_plan", imitation_plan_node))
    graph.add_node("review", _traced("review", review_node))
    graph.add_node("report", _traced("report", report_node, output_dir))
    graph.add_node("memory_write", _traced("memory_write", memory_write_node))
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
) -> WorkflowState:
    app = build_langgraph_workflow(output_dir)
    result = app.invoke(create_initial_state(user_query))
    return result


def _traced(name: str, func: Callable[..., WorkflowState], *args):
    def node(state: WorkflowState) -> WorkflowState:
        return run_traced_node(state, name, func, *args)

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
