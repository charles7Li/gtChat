import json
from pathlib import Path

from evals.exporters import export_node_eval_cases
from evals.runners import run_trace_eval
from evals.runners.local_quality import evaluate_trace_quality


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
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "trend_report.md"
    report_dir = tmp_path / "reports"
    report_path.write_text(
        "# Trend Report\n\nSource: local fixture.\n\nEvidence: top samples are present.\n\nTrend: pet care is rising.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"route": "trend_report_path", "latest_report": str(report_path), "source_summary": {"sources": [{"source": "fixture"}]}}),
        encoding="utf-8",
    )
    trace_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "route": "trend_report_path",
                "nodes": [
                    {"name": "plan", "status": "success", "duration_ms": 1},
                    {"name": "route", "status": "success", "duration_ms": 1},
                    {"name": "memory_load", "status": "success", "duration_ms": 1},
                    {"name": "load_latest_search_results", "status": "success", "duration_ms": 1, "output_summary": {"raw_items": 2}},
                    {"name": "clean", "status": "success", "duration_ms": 1, "output_summary": {"clean_items": 2, "quality_score": 95}},
                    {"name": "trend_analyze", "status": "success", "duration_ms": 1},
                    {"name": "pattern_extract", "status": "success", "duration_ms": 1},
                    {"name": "evidence_pack", "status": "success", "duration_ms": 1, "output_summary": {"evidence_items": 2}},
                    {"name": "report", "status": "success", "duration_ms": 3},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_trace_eval(trace_path, report_dir, manifest_path=manifest_path, report_path=report_path)

    assert report["status"] == "passed"
    assert report["case_count"] == 9
    assert report["quality"]["score"] >= 90
    assert (report_dir / "node_eval_cases.jsonl").exists()
    assert json.loads((report_dir / "eval_report.json").read_text(encoding="utf-8"))["status"] == "passed"
    markdown = (report_dir / "eval_report.md").read_text(encoding="utf-8")
    assert "# Mochi Scout Trace Eval" in markdown
    assert "## Checks" in markdown


def test_trace_quality_flags_missing_evidence_and_report_source(tmp_path):
    trace_path = tmp_path / "agent_trace.json"
    report_path = tmp_path / "trend_report.md"
    report_path.write_text("# Trend Report\n\nA short report without audit details.\n", encoding="utf-8")
    trace_path.write_text(
        json.dumps(
            {
                "run_id": "run-2",
                "route": "trend_report_path",
                "nodes": [
                    {"name": "plan", "status": "success", "duration_ms": 1},
                    {"name": "route", "status": "success", "duration_ms": 1},
                    {"name": "memory_load", "status": "success", "duration_ms": 1},
                    {"name": "load_latest_search_results", "status": "success", "duration_ms": 1},
                    {"name": "clean", "status": "success", "duration_ms": 1, "output_summary": {"clean_items": 2}},
                    {"name": "trend_analyze", "status": "success", "duration_ms": 1},
                    {"name": "pattern_extract", "status": "success", "duration_ms": 1},
                    {"name": "evidence_pack", "status": "success", "duration_ms": 1, "output_summary": {"evidence_items": 0}},
                    {"name": "report", "status": "success", "duration_ms": 1},
                ],
            }
        ),
        encoding="utf-8",
    )

    quality = evaluate_trace_quality(trace_path, report_path=report_path)

    assert quality["status"] == "failed"
    failed_names = {check["name"] for check in quality["checks"] if check["status"] == "failed"}
    assert {"evidence", "source_visibility"} <= failed_names
    assert quality["recommendations"]


def test_workflow_eval_dataset_is_local_dry_run_only():
    rows = [
        json.loads(line)
        for line in Path("evals/datasets/workflow_eval_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row["route"] for row in rows} >= {
        "trend_report_path",
        "imitation_plan_path",
        "reference_video_imitation_path",
        "commercial_data_analysis_path",
        "hotspot_auto_analysis_path",
    }
    assert all(row["requires_live"] is False for row in rows)
