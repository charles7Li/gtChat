from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.exporters import export_node_eval_cases


def run_trace_eval(trace_path: str | Path, output_dir: str | Path = "evals/reports") -> dict:
    output = Path(output_dir)
    cases = export_node_eval_cases(trace_path, output / "node_eval_cases.jsonl")
    failed = [case for case in cases if case.get("status") == "failed" or case.get("error")]
    missing_duration = [case for case in cases if not isinstance(case.get("duration_ms"), int)]
    report = {
        "status": "passed" if cases and not failed and not missing_duration else "failed",
        "trace_path": str(trace_path),
        "case_count": len(cases),
        "failed_count": len(failed),
        "missing_duration_count": len(missing_duration),
        "node_names": [case["node_name"] for case in cases],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "eval_report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict) -> str:
    lines = [
        "# gtChat Trace Eval",
        "",
        f"- status: {report['status']}",
        f"- case_count: {report['case_count']}",
        f"- failed_count: {report['failed_count']}",
        f"- missing_duration_count: {report['missing_duration_count']}",
        f"- trace_path: {report['trace_path']}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local trace eval from agent_trace.json.")
    parser.add_argument("trace_path")
    parser.add_argument("--output-dir", default="evals/reports")
    args = parser.parse_args(argv)
    print(json.dumps(run_trace_eval(args.trace_path, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
