import json

from app.notifications import build_monitor_digest, load_monitor_events, process_one_notification_job, send_notification, validate_notification_config
from app.queue import SQLiteQueue


def test_build_monitor_digest_reports_auth_prompt(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "event_type": "auth_required",
                "platform": "xiaohongshu",
                "account": "default",
                "reason": "profile_missing",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    digest = build_monitor_digest(state_dir)

    assert digest["status"] == "auth_required"
    assert digest["next_steps"] == ["python -m app.collectors.xiaohongshu_minimal --login --profile-dir .profiles/xhs/default"]
    assert "xiaohongshu needs login" in digest["messages"][0]


def test_build_monitor_digest_summarizes_decision_and_report_path(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    events = [
        {"event_type": "signal", "platform": "xiaohongshu", "keyword": "pet"},
        {
            "event_type": "research_decision",
            "job_id": "job-1",
            "decision": {"decision": "accept", "reason": "strong"},
            "verification": {"decision": "needs_more_evidence"},
            "next_job_id": "job-2",
            "next_job_type": "research_requested",
        },
        {"event_type": "report_ready", "report_path": "outputs/final_package/trend_report.md"},
    ]
    (state_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events),
        encoding="utf-8",
    )

    digest = build_monitor_digest(state_dir)

    assert digest["status"] == "research_updated"
    assert digest["signals"] == 1
    assert digest["decisions"][0]["decision"] == "accept"
    assert digest["report_paths"] == ["outputs/final_package/trend_report.md"]


def test_load_monitor_events_keeps_invalid_lines(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "events.jsonl").write_text("{bad json}\n", encoding="utf-8")

    events = load_monitor_events(state_dir)

    assert events == [{"event_type": "invalid_event", "raw": "{bad json}"}]


def test_process_one_notification_job_writes_digest_and_marks_done(tmp_path):
    state_dir = tmp_path / "state"
    queue_db = tmp_path / "events.db"
    output_path = tmp_path / "digest.json"
    state_dir.mkdir()
    (state_dir / "events.jsonl").write_text(
        json.dumps({"event_type": "signal", "platform": "xiaohongshu", "keyword": "pet"}, ensure_ascii=False),
        encoding="utf-8",
    )
    queue = SQLiteQueue(queue_db)
    job_id = queue.enqueue("notification_requested", {"state_dir": str(state_dir), "output_path": str(output_path)})

    result = process_one_notification_job(queue_db=queue_db, state_dir=state_dir)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["status"] == "done"
    assert queue.get(job_id)["status"] == "done"
    assert saved["status"] == "signal_detected"
    assert saved["signals"] == 1


def test_send_notification_skips_without_webhook(monkeypatch):
    monkeypatch.delenv("NOTIFICATION_WEBHOOK_URL", raising=False)

    result = send_notification({"messages": ["hello"]})

    assert result == {"status": "skipped", "reason": "webhook_not_configured"}


def test_send_notification_posts_webhook(monkeypatch):
    seen = {}

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["body"] = req.data.decode("utf-8")
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.notifications.monitor_digest.request.urlopen", fake_urlopen)

    result = send_notification({"messages": ["hello"], "status": "signal_detected"}, webhook_url="https://example.test/hook")

    assert result == {"status": "sent", "channel": "webhook", "status_code": 204}
    assert seen["url"] == "https://example.test/hook"
    assert json.loads(seen["body"])["text"] == "hello"
    assert seen["timeout"] == 10


def test_validate_notification_config(monkeypatch):
    monkeypatch.delenv("NOTIFICATION_WEBHOOK_URL", raising=False)
    assert validate_notification_config()["status"] == "not_ready"

    monkeypatch.setenv("NOTIFICATION_WEBHOOK_URL", "https://example.test/hook")
    assert validate_notification_config()["status"] == "ready"
