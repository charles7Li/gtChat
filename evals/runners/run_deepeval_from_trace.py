from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.exporters import export_node_eval_cases
from .local_quality import evaluate_trace_quality


def run_trace_eval(
    trace_path: str | Path,
    output_dir: str | Path = "evals/reports",
    *,
    manifest_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> dict:
    output = Path(output_dir)
    cases = export_node_eval_cases(trace_path, output / "node_eval_cases.jsonl")
    failed = [case for case in cases if case.get("status") == "failed" or case.get("error")]
    missing_duration = [case for case in cases if not isinstance(case.get("duration_ms"), int)]
    quality = evaluate_trace_quality(trace_path, manifest_path=manifest_path, report_path=report_path)
    report = {
        "status": "passed" if cases and not failed and not missing_duration and quality["status"] == "passed" else "failed",
        "trace_path": str(trace_path),
        "case_count": len(cases),
        "failed_count": len(failed),
        "missing_duration_count": len(missing_duration),
        "node_names": [case["node_name"] for case in cases],
        "quality": quality,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "eval_report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict) -> str:
    lines = [
        "# Mochi Scout Trace Eval",
        "",
        f"- status: {report['status']}",
        f"- case_count: {report['case_count']}",
        f"- failed_count: {report['failed_count']}",
        f"- missing_duration_count: {report['missing_duration_count']}",
        f"- trace_path: {report['trace_path']}",
        f"- route: {report['quality']['route']}",
        f"- quality_score: {report['quality']['score']}",
        "",
        "## Coverage",
        "",
        f"- required_nodes: {report['quality']['coverage']['required_node_count']}",
        f"- observed_required_nodes: {report['quality']['coverage']['observed_required_node_count']}",
        f"- checks: {report['quality']['coverage']['passed_count']} passed / {report['quality']['coverage']['warning_count']} warnings / {report['quality']['coverage']['failed_count']} failed",
        "",
        "## Performance",
        "",
        f"- workflow_total_ms: {report['quality']['performance']['workflow_total_ms']}",
        f"- budget_ms: {report['quality']['performance']['budget_ms']}",
        f"- budget_passed: {report['quality']['performance']['budget_passed']}",
        f"- slowest_node: {report['quality']['performance']['slowest_node']['name']} ({report['quality']['performance']['slowest_node']['duration_ms']} ms)",
        "",
        "## Checks",
        "",
    ]
    for check in report["quality"]["checks"]:
        lines.append(f"- {check['status']}: {check['name']} - {check['detail']}")
    if report["quality"]["recommendations"]:
        lines.extend(["", "## Recommendations", ""])
        for item in report["quality"]["recommendations"]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local trace eval from agent_trace.json.")
    parser.add_argument("trace_path")
    parser.add_argument("--output-dir", default="evals/reports")
    parser.add_argument("--manifest-path", default=None)
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_trace_eval(args.trace_path, args.output_dir, manifest_path=args.manifest_path, report_path=args.report_path),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
