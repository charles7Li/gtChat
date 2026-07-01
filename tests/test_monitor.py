import json

import app.workflow
from app.monitor import AuthGate, SignalDetector, process_one_hotspot_analysis_job, process_one_research_job, run_background_loop, run_background_once, run_monitor_tick
from app.queue import SQLiteQueue


def test_auth_gate_requires_missing_xhs_profile(tmp_path):
    status = AuthGate(tmp_path / ".profiles").check("xiaohongshu", "default")

    assert status.status == "auth_required"
    assert status.reason == "profile_missing"


def test_signal_detector_accepts_new_items():
    signal = SignalDetector(min_new_items=2).detect(
        [{"id": "old", "metrics": {"total_engagement": 10}}],
        [
            {"id": "old", "metrics": {"total_engagement": 10}},
            {"id": "new-1", "metrics": {"total_engagement": 20}},
            {"id": "new-2", "metrics": {"total_engagement": 30}},
        ],
        keyword="pet",
        platform="xiaohongshu",
    )

    assert signal["accepted"] is True
    assert signal["new_item_count"] == 2


def test_monitor_tick_enqueues_signal_from_snapshot(tmp_path):
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    state_dir = tmp_path / "state"
    queue_db = tmp_path / "events.db"
    previous.write_text(json.dumps([{"id": "old", "liked_count": 10}]), encoding="utf-8")
    current.write_text(
        json.dumps(
            [
                {"id": "old", "liked_count": 10},
                {"id": "new-1", "liked_count": 20},
                {"id": "new-2", "liked_count": 30},
                {"id": "new-3", "liked_count": 40},
            ]
        ),
        encoding="utf-8",
    )

    run_monitor_tick(keyword="pet", snapshot_path=previous, state_dir=state_dir, queue_db=queue_db, require_auth=False)
    result = run_monitor_tick(keyword="pet", snapshot_path=current, state_dir=state_dir, queue_db=queue_db, require_auth=False)
    job = SQLiteQueue(queue_db).claim_next(["trend_signal_detected"])

    assert result["status"] == "signal"
    assert job["payload"]["keyword"] == "pet"
    assert job["payload"]["new_item_count"] == 3


def test_research_worker_turns_accepted_signal_into_research_request(tmp_path):
    queue_db = tmp_path / "events.db"
    state_dir = tmp_path / "state"
    queue = SQLiteQueue(queue_db)
    job_id = queue.enqueue(
        "trend_signal_detected",
        {
            "platform": "xiaohongshu",
            "keyword": "pet",
            "signal_score": 90,
            "new_item_count": 5,
            "engagement_growth": 1.2,
        },
        dedupe_key="xiaohongshu:pet:trend_signal",
    )

    result = process_one_research_job(queue_db=queue_db, state_dir=state_dir)
    original = queue.get(job_id)
    next_job = queue.claim_next(["research_requested"])
    events = (state_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()

    assert result["status"] == "done"
    assert result["next_job_type"] == "research_requested"
    assert original["status"] == "done"
    assert next_job["payload"]["keyword"] == "pet"
    assert next_job["payload"]["max_iterations"] == 1
    assert len(next_job["payload"]["strategy"]["queries"]) == 3
    assert json.loads(events[-1])["event_type"] == "research_decision"


def test_background_once_enqueues_and_processes_hotspot_analysis(tmp_path, monkeypatch):
    config_path = tmp_path / "monitor.json"
    signals_path = tmp_path / "signals.json"
    queue_db = tmp_path / "events.db"
    state_dir = tmp_path / "state"
    config_path.write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "name": "pet monitor",
                "platforms": ["douyin_hot_board"],
                "keywords": ["pet"],
                "rule": {"min_heat_score": 80},
            }
        ),
        encoding="utf-8",
    )
    signals_path.write_text(
        json.dumps({"signals": [{"signal_id": "s1", "source": "douyin_hot_board", "keyword": "pet", "heat_score": 90}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(app.workflow, "run_workflow", lambda query, output_dir: {"report_path": str(output_dir / "report.md"), "trace_path": str(output_dir / "trace.json")})

    result = run_background_once(config_path=config_path, signals_path=signals_path, queue_db=queue_db, state_dir=state_dir, output_dir=tmp_path / "out")
    events = [json.loads(line) for line in (state_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result["status"] == "triggered"
    assert result["analysis"][0]["status"] == "done"
    assert SQLiteQueue(queue_db).get(result["queued_job_ids"][0])["status"] == "done"
    assert events[-1]["event_type"] == "background_run"


def test_hotspot_analysis_worker_is_idle_without_job(tmp_path):
    result = process_one_hotspot_analysis_job(queue_db=tmp_path / "events.db", state_dir=tmp_path / "state")

    assert result == {"status": "idle"}


def test_background_loop_uses_config_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "monitor.json"
    signals_path = tmp_path / "signals.json"
    queue_db = tmp_path / "events.db"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "out"
    signals_path.write_text(
        json.dumps({"signals": [{"signal_id": "s1", "source": "douyin_hot_board", "keyword": "pet", "heat_score": 90}]}),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "name": "pet monitor",
                "platforms": ["douyin_hot_board"],
                "keywords": ["pet"],
                "signals_path": str(signals_path),
                "output_dir": str(output_dir),
                "interval_seconds": 1,
                "rule": {"min_heat_score": 80},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app.workflow, "run_workflow", lambda query, output_dir: {"report_path": str(output_dir / "report.md"), "trace_path": str(output_dir / "trace.json")})

    result = run_background_loop(config_path=config_path, queue_db=queue_db, state_dir=state_dir, max_runs=1)

    assert result[0]["status"] == "triggered"
    assert result[0]["analysis"][0]["report_path"].startswith(str(output_dir))
