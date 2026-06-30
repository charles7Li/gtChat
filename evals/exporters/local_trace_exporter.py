from __future__ import annotations

import json
from pathlib import Path


def export_node_eval_cases(trace_path: str | Path, output_path: str | Path | None = None) -> list[dict]:
    trace_file = Path(trace_path)
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    cases = [
        {
            "case_id": f"{trace.get('run_id', trace_file.stem)}::{node.get('name', index)}::{index}",
            "trace_path": str(trace_file),
            "route": trace.get("route", ""),
            "node_name": node.get("name", ""),
            "status": node.get("status", ""),
            "input_summary": node.get("input_summary", {}),
            "output_summary": node.get("output_summary", {}),
            "duration_ms": node.get("duration_ms", 0),
            "error": node.get("error", ""),
        }
        for index, node in enumerate(trace.get("nodes") or [])
    ]
    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + ("\n" if cases else ""), encoding="utf-8")
    return cases
