import json
from pathlib import Path

from evals.exporters import export_node_eval_cases
from evals.runners import run_trace_eval


def test_export_node_eval_cases_from_agent_trace(tmp_path):
    trace_path = tmp_path / "agent_trace.json"
    output_path = tmp_path / "node_eval_cases.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "route": "trend_report_path",
                "nodes": [
                    {
                        "name": "plan",
                        "status": "success",
                        "duration_ms": 2,
                        "input_summary": {"route": "trend_report_path"},
                        "output_summary": {"keyword": "pet"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = export_node_eval_cases(trace_path, output_path)

    assert cases[0]["case_id"] == "run-1::plan::0"
    assert cases[0]["route"] == "trend_report_path"
    assert output_path.read_text(encoding="utf-8").count("\n") == 1


def test_run_trace_eval_writes_reports(tmp_path):
    trace_path = tmp_path / "agent_trace.json"
    report_dir = tmp_path / "reports"
    trace_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "route": "imitation_plan_path",
                "nodes": [
                    {"name": "plan", "status": "success", "duration_ms": 1},
                    {"name": "report", "status": "success", "duration_ms": 3},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_trace_eval(trace_path, report_dir)

    assert report["status"] == "passed"
    assert report["case_count"] == 2
    assert (report_dir / "node_eval_cases.jsonl").exists()
    assert json.loads((report_dir / "eval_report.json").read_text(encoding="utf-8"))["status"] == "passed"
    assert "# gtChat Trace Eval" in (report_dir / "eval_report.md").read_text(encoding="utf-8")


def test_workflow_eval_dataset_is_local_dry_run_only():
    rows = [
        json.loads(line)
        for line in Path("evals/datasets/workflow_eval_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row["route"] for row in rows} >= {"trend_report_path", "imitation_plan_path", "reference_video_imitation_path", "commercial_data_analysis_path"}
    assert all(row["requires_live"] is False for row in rows)
