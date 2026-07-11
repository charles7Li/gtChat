from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.workflow.route_manifest import load_route_manifests
from app.workflow.performance import build_performance_summary


PASSING = {"passed", "warn"}


def evaluate_trace_quality(
    trace_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    report_path: str | Path | None = None,
    manifest_dir: str | Path = "pipeline_defs",
) -> dict:
    trace_file = Path(trace_path)
    trace = _read_json(trace_file)
    manifest = _read_optional_json(manifest_path) or _read_optional_json(trace_file.with_name("manifest.json")) or {}
    report_text = _read_optional_text(report_path) or _read_report_from_manifest(manifest)

    route = str(trace.get("route") or manifest.get("route") or "")
    nodes = [node for node in trace.get("nodes") or [] if isinstance(node, dict)]
    node_names = [str(node.get("name", "")) for node in nodes]
    route_manifest = load_route_manifests(manifest_dir).get(route) if route else None
    required_nodes = [name for name in (route_manifest.stage_names if route_manifest else []) if name != "trace"]

    checks = [
        _check("trace_shape", bool(trace.get("run_id")) and bool(route) and bool(nodes), "Trace has run_id, route, and nodes."),
        _check("route_manifest", route_manifest is not None, f"Route manifest found for {route or '<missing>'}."),
        _required_nodes_check(node_names, required_nodes),
        _node_health_check(nodes),
        _duration_check(nodes),
        _data_quality_check(nodes, required_nodes),
        _evidence_check(nodes, manifest, required_nodes),
        _source_check(trace, manifest, report_text),
        _report_content_check(report_text, required_nodes),
        _review_reason_check(report_text, required_nodes),
    ]
    checks = [check for check in checks if check]
    failed = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warn"]
    passed = [check for check in checks if check["status"] == "passed"]
    score = round((len(passed) + 0.5 * len(warnings)) / len(checks) * 100) if checks else 0

    return {
        "status": "passed" if not failed else "failed",
        "score": score,
        "route": route,
        "run_id": trace.get("run_id", ""),
        "required_nodes": required_nodes,
        "observed_nodes": node_names,
        "coverage": {
            "required_node_count": len(required_nodes),
            "observed_required_node_count": len([name for name in required_nodes if name in node_names]),
            "check_count": len(checks),
            "passed_count": len(passed),
            "warning_count": len(warnings),
            "failed_count": len(failed),
        },
        "performance": build_performance_summary(nodes, route=route),
        "checks": checks,
        "recommendations": _recommendations(checks),
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: str | Path | None) -> dict | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    return _read_json(file_path)


def _read_optional_text(path: str | Path | None) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def _read_report_from_manifest(manifest: dict) -> str:
    for key in ("latest_report", "report"):
        text = _read_optional_text(manifest.get(key))
        if text:
            return text
    return ""


def _check(name: str, passed: bool, detail: str, *, warn: bool = False) -> dict:
    if passed:
        status = "passed"
    else:
        status = "warn" if warn else "failed"
    return {"name": name, "status": status, "detail": detail}


def _required_nodes_check(node_names: list[str], required_nodes: list[str]) -> dict:
    if not required_nodes:
        return _check("required_nodes", False, "No route manifest stages were available.", warn=True)
    missing = [name for name in required_nodes if name not in node_names]
    return _check(
        "required_nodes",
        not missing,
        "All route-required nodes are present." if not missing else f"Missing required nodes: {', '.join(missing)}.",
    )


def _node_health_check(nodes: list[dict]) -> dict:
    failed_nodes = [str(node.get("name", "")) for node in nodes if node.get("status") == "failed" or node.get("error")]
    return _check(
        "node_health",
        not failed_nodes,
        "No failed nodes or node errors." if not failed_nodes else f"Failed/error nodes: {', '.join(failed_nodes)}.",
    )


def _duration_check(nodes: list[dict]) -> dict:
    missing = [str(node.get("name", "")) for node in nodes if not isinstance(node.get("duration_ms"), int)]
    return _check(
        "node_durations",
        not missing,
        "Every node has integer duration_ms." if not missing else f"Nodes missing integer duration_ms: {', '.join(missing)}.",
    )


def _data_quality_check(nodes: list[dict], required_nodes: list[str]) -> dict | None:
    if "clean" not in required_nodes:
        return None
    clean_summary = _node_summary(nodes, "clean")
    has_counts = _positive_int(clean_summary.get("clean_items")) or isinstance(clean_summary.get("quality_score"), int)
    return _check(
        "data_quality",
        has_counts,
        "Clean node exposes clean item counts or quality score.",
    )


def _evidence_check(nodes: list[dict], manifest: dict, required_nodes: list[str]) -> dict | None:
    if "evidence_pack" not in required_nodes and "video_pattern_extract" not in required_nodes:
        return None
    evidence_summary = _node_summary(nodes, "evidence_pack") or _node_summary(nodes, "video_pattern_extract")
    evidence_path = manifest.get("evidence_pack")
    evidence = _read_optional_json(evidence_path) if evidence_path else None
    has_evidence = _positive_int(evidence_summary.get("evidence_items"))
    if evidence:
        has_evidence = has_evidence or _positive_int(evidence.get("item_count")) or bool(evidence.get("top_items"))
    return _check("evidence", bool(has_evidence), "Evidence pack has count or top item samples.")


def _source_check(trace: dict, manifest: dict, report_text: str) -> dict:
    source_summary = trace.get("source_summary") or manifest.get("source_summary") or {}
    has_sources = bool(source_summary.get("sources"))
    lowered = report_text.lower()
    has_report_source = "source" in lowered or "数据来源" in report_text or "来源" in report_text
    return _check("source_visibility", has_sources or has_report_source, "Source/provenance is visible in trace, manifest, or report.")


def _report_content_check(report_text: str, required_nodes: list[str]) -> dict:
    if not report_text:
        return _check("report_content", False, "Report text was not found.")
    lowered = report_text.lower()
    expected_terms = ["trend", "趋势", "evidence", "证据", "source", "来源"]
    if "imitation_plan" in required_nodes:
        expected_terms.extend(["imitation", "仿拍"])
    hits = [term for term in expected_terms if term in lowered or term in report_text]
    return _check(
        "report_content",
        len(hits) >= 3,
        f"Report includes {len(hits)} expected quality terms.",
    )


def _review_reason_check(report_text: str, required_nodes: list[str]) -> dict | None:
    if "review" not in required_nodes:
        return None
    lowered = report_text.lower()
    has_score = "score" in lowered or "评分" in report_text or "总分" in report_text
    has_reason = "reason" in lowered or "理由" in report_text or "建议" in report_text
    return _check("review_reasoning", has_score and has_reason, "Review report includes score and reasoning.")


def _node_summary(nodes: list[dict], name: str) -> dict[str, Any]:
    for node in nodes:
        if node.get("name") == name:
            summary = node.get("output_summary") or {}
            return summary if isinstance(summary, dict) else {}
    return {}


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def _recommendations(checks: list[dict]) -> list[str]:
    messages = {
        "required_nodes": "Run the full route fixture or update the route manifest if the workflow shape changed intentionally.",
        "data_quality": "Expose clean_items and quality_score from the clean node output summary.",
        "evidence": "Write evidence_items in trace and keep evidence_pack.json linked from manifest.",
        "source_visibility": "Add source_summary or a report source section so provenance is auditable.",
        "report_content": "Include source, evidence samples, and route-specific findings in the Markdown report.",
        "review_reasoning": "Include both numeric review score and concise scoring reasons.",
        "node_durations": "Ensure every run_node hook records duration_ms as an integer.",
        "node_health": "Inspect failed nodes before comparing content quality.",
    }
    return [messages.get(check["name"], check["detail"]) for check in checks if check["status"] == "failed"]
