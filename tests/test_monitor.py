import json

from app.monitor import AuthGate, SignalDetector, process_one_research_job, run_monitor_tick
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
