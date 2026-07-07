import json

from fastapi.testclient import TestClient

import app.web_api as web_api


def test_chat_run_returns_workflow_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api, "RUNS_DIR", tmp_path / "runs")

    def fake_run_workflow(query, output_dir):
        output_dir.mkdir(parents=True)
        (output_dir / "trend_report.md").write_text("# Report", encoding="utf-8")
        return {
            "run_id": "run-1",
            "user_query": query,
            "route": "trend_report_path",
            "report_path": str(output_dir / "trend_report.md"),
            "trace_path": str(output_dir / "agent_trace.json"),
            "manifest_path": str(output_dir / "manifest.json"),
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr(web_api, "run_workflow", fake_run_workflow)
    response = TestClient(web_api.create_app()).post("/api/chat/runs", json={"query": "trend report"})

    assert response.status_code == 200
    assert response.json()["run_id"] == "run-1"
    assert response.json()["report_path"].endswith("trend_report.md")


def test_chat_run_default_output_dir_is_unique():
    assert web_api._run_dir_name() != web_api._run_dir_name()


def test_chat_run_rejects_full_pipeline_without_live(monkeypatch):
    monkeypatch.setattr(web_api.PlanAgent, "run", lambda self, query: {"route": "full_pipeline_path"})
    response = TestClient(web_api.create_app()).post("/api/chat/runs", json={"query": "full"})

    assert response.status_code == 400
    assert "allow_live" in response.json()["detail"]


def test_upload_asset_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api, "UPLOADS_DIR", tmp_path / "uploads")
    response = TestClient(web_api.create_app()).post(
        "/api/uploads?filename=items.json",
        content=b"{\"items\": []}",
        headers={"content-type": "application/json"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["file_type"] == "json"
    assert (tmp_path / "uploads" / payload["asset_id"] / "items.json").exists()


def test_video_analyze_calls_local_analyzer(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    calls = {}

    def fake_analyze(path, **kwargs):
        calls["path"] = path
        calls.update(kwargs)
        return {"_analysis_meta": {"output_path": str(tmp_path / "brief.json")}}

    monkeypatch.setattr(web_api, "analyze_local_video", fake_analyze)
    response = TestClient(web_api.create_app()).post("/api/video/analyze", json={"path": str(video), "max_keyframes": 2})

    assert response.status_code == 200
    assert calls["path"] == str(video)
    assert calls["max_keyframes"] == 2


def test_imports_accept_uploaded_chanmama_file(tmp_path):
    export = tmp_path / "items.json"
    export.write_text(json.dumps({"items": [{"video_id": "v1", "视频标题": "title"}]}), encoding="utf-8")

    response = TestClient(web_api.create_app()).post("/api/imports", json={"source": "chanmama", "path": str(export)})

    payload = response.json()
    assert response.status_code == 200
    assert payload["record_count"] == 1
    assert payload["records"][0]["detected_entity_type"] == "video"


def test_monitor_tick_uses_offline_snapshot(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps([{"id": "1", "liked_count": 10}]), encoding="utf-8")
    response = TestClient(web_api.create_app()).post(
        "/api/monitor/ticks",
        json={
            "keyword": "pet",
            "snapshot_path": str(snapshot),
            "platform": "local_fixture",
            "state_dir": str(tmp_path / "state"),
            "queue_db": str(tmp_path / "events.db"),
            "require_auth": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"signal", "no_signal"}


def test_reports_list_run_lookup_and_preview(monkeypatch, tmp_path):
    output = tmp_path / "outputs" / "run-1"
    output.mkdir(parents=True)
    (output / "trend_report.md").write_text("# Report", encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps({"run_id": "run-1", "route": "trend_report_path", "created_at": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (output / "agent_trace.json").write_text(json.dumps({"run_id": "run-1", "nodes": []}), encoding="utf-8")
    (output / "evidence_pack.json").write_text(json.dumps({"top_items": []}), encoding="utf-8")
    monkeypatch.setattr(web_api, "REPORT_ROOT", tmp_path / "outputs")

    client = TestClient(web_api.create_app())
    assert client.get("/api/reports").json()[0]["run_id"] == "run-1"
    assert client.get("/api/runs/run-1").json()["run_id"] == "run-1"
    assert client.get("/api/reports/run-1").json()["markdown"] == "# Report"
    assert client.get("/api/reports/run-1/artifacts/trace").json()["nodes"] == []
    assert client.get("/api/reports/run-1/artifacts/manifest").json()["route"] == "trend_report_path"
    assert client.get("/api/reports/run-1/artifacts/evidence").json()["top_items"] == []
    download = client.get("/api/reports/run-1/download")
    assert download.status_code == 200
    assert download.text == "# Report"
    assert download.headers["content-type"].startswith("text/markdown")


def test_monitor_job_run_once_uses_empty_signals(monkeypatch, tmp_path):
    monkeypatch.setattr(web_api, "MONITOR_DIR", tmp_path / "monitor_jobs")
    calls = {}

    def fake_run_background_once(**kwargs):
        calls.update(kwargs)
        return {"status": "skipped"}

    monkeypatch.setattr(web_api, "run_background_once", fake_run_background_once)
    client = TestClient(web_api.create_app())
    created = client.post(
        "/api/monitor/jobs",
        json={
            "job_id": "job-1",
            "name": "Pet",
            "rule": {"min_heat_score": 80, "min_growth_rate": 0.3, "min_rank": 20, "min_engagement": 500},
        },
    )

    assert created.status_code == 200
    saved = client.get("/api/monitor/jobs").json()[0]
    assert saved["job_id"] == "job-1"
    assert saved["rule"] == {"min_heat_score": 80.0, "min_growth_rate": 0.3, "min_rank": 20, "min_engagement": 500, "required_sources": []}
    assert client.post("/api/monitor/jobs/job-1/run-once").json() == {"status": "skipped"}
    assert calls["signals_path"].endswith("job-1.signals.json")


def test_monitor_digest_summarizes_events(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "events.jsonl").write_text(
        json.dumps({"created_at": "2026-01-01T00:00:00+00:00", "event_type": "signal", "platform": "local"}) + "\n",
        encoding="utf-8",
    )

    response = TestClient(web_api.create_app()).get(f"/api/monitor/digest?state_dir={state_dir}")

    assert response.status_code == 200
    assert response.json()["status"] == "signal_detected"


def test_files_endpoint_reads_only_artifact_roots(monkeypatch, tmp_path):
    output = tmp_path / "outputs" / "video_analysis" / "video_analysis_brief.json"
    output.parent.mkdir(parents=True)
    output.write_text("{\"ok\": true}", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(web_api, "REPORT_ROOT", tmp_path / "outputs")
    monkeypatch.setattr(web_api, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web_api, "MONITOR_DIR", tmp_path / "monitor_jobs")

    client = TestClient(web_api.create_app())

    allowed = client.get("/api/files", params={"path": str(output)})
    blocked = client.get("/api/files", params={"path": str(outside)})
    assert allowed.status_code == 200
    assert allowed.text == "{\"ok\": true}"
    assert blocked.status_code == 400
