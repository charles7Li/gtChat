from __future__ import annotations

import argparse
import os
from pathlib import Path
from time import perf_counter

from app.workflow import run_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Mochi Scout agent workflow.")
    parser.add_argument("query", help="User query for the workflow")
    parser.add_argument("--output-dir", default="outputs/final_package", help="Where to write report and trace files")
    parser.add_argument("--env-file", default=".env", help="Local env file to load before running")
    parser.add_argument("--no-progress", action="store_true", help="Disable realtime workflow progress output")
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))
    progress = None if args.no_progress else ProgressPrinter()
    state = run_workflow(args.query, args.output_dir, progress_callback=progress)
    if progress:
        progress.finish()
    _print_summary(state)
    return 0 if not state.get("errors") else 1


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _print_summary(state: dict) -> None:
    print("")
    print(f"Run ID: {state.get('run_id', '')}")
    print(f"Route: {state.get('route', '')}")
    print(f"Keyword: {state.get('keyword', '')}")
    print("")
    print("Pipeline:")
    for node in state.get("trace_nodes", []):
        status = node.get("status", "unknown")
        duration = node.get("duration_ms", 0)
        llm_text = _llm_text(node.get("llm_events") or [])
        suffix = f" | {llm_text}" if llm_text else ""
        print(f"- {node.get('name', '')}: {status} ({duration}ms){suffix}")

    warnings = state.get("warnings") or []
    errors = state.get("errors") or []
    if warnings:
        print("")
        print("Warnings:")
        for warning in warnings:
            print(f"- [{warning.get('node', '')}] {warning.get('code', '')}: {warning.get('message', '')}")
    if errors:
        print("")
        print("Errors:")
        for error in errors:
            print(f"- [{error.get('node', '')}] {error.get('code', '')}: {error.get('message', '')}")

    print("")
    print(f"Report: {state.get('report_path', '')}")
    print(f"Trace: {state.get('trace_path', '')}")


def _llm_text(events: list[dict]) -> str:
    if not events:
        return ""
    parts = []
    for event in events:
        model = f"/{event.get('model')}" if event.get("model") else ""
        parts.append(f"llm:{event.get('prompt')}={event.get('status')}{model}")
    return ", ".join(parts)


class ProgressPrinter:
    PATH_TOTALS = {
        "trend_report_path": 9,
        "imitation_plan_path": 11,
        "full_pipeline_path": 13,
    }

    def __init__(self) -> None:
        self.started = perf_counter()
        self.completed = 0
        self.total: int | None = None

    def __call__(self, event: dict) -> None:
        phase = event.get("phase")
        name = event.get("name", "")
        if phase == "start":
            print(f"{self._prefix()} -> {name} ...", flush=True)
            return

        if phase in {"finish", "failed"}:
            self.completed += 1
            route = (event.get("output_summary") or {}).get("route")
            if route in self.PATH_TOTALS:
                self.total = self.PATH_TOTALS[route]
            status = event.get("status", phase)
            duration = event.get("duration_ms", 0)
            llm = _llm_text(event.get("llm_events") or [])
            suffix = f" | {llm}" if llm else ""
            print(f"{self._prefix()} {self._bar()} {name}: {status} ({duration}ms){suffix}", flush=True)

    def finish(self) -> None:
        elapsed = round((perf_counter() - self.started) * 1000)
        print(f"{self._prefix()} workflow finished in {elapsed}ms", flush=True)

    def _prefix(self) -> str:
        total = self.total if self.total is not None else "?"
        return f"[{self.completed}/{total}]"

    def _bar(self) -> str:
        if not self.total:
            return "[----------]"
        width = 10
        filled = min(width, round(width * self.completed / self.total))
        return "[" + "#" * filled + "-" * (width - filled) + "]"


if __name__ == "__main__":
    raise SystemExit(main())
