from app.queue import SQLiteQueue


def test_sqlite_queue_dedupes_by_key(tmp_path):
    queue = SQLiteQueue(tmp_path / "events.db")

    first = queue.enqueue("report_requested", {"keyword": "pet"}, dedupe_key="xhs:pet")
    second = queue.enqueue("report_requested", {"keyword": "pet"}, dedupe_key="xhs:pet")

    assert second == first
    assert queue.get(first)["payload"] == {"keyword": "pet"}


def test_sqlite_queue_claims_and_marks_done(tmp_path):
    queue = SQLiteQueue(tmp_path / "events.db")
    job_id = queue.enqueue("research_requested", {"keyword": "pet"})

    claimed = queue.claim_next(["research_requested"])

    assert claimed["id"] == job_id
    assert claimed["status"] == "running"
    assert queue.claim_next(["research_requested"]) is None

    queue.mark_done(job_id)

    assert queue.get(job_id)["status"] == "done"


def test_sqlite_queue_retries_then_dead_letters(tmp_path):
    queue = SQLiteQueue(tmp_path / "events.db")
    job_id = queue.enqueue("notification_requested", {"message": "hi"})

    for _ in range(3):
        queue.mark_failed(job_id, "temporary")
        job = queue.get(job_id)
        assert job["status"] == "pending"

    queue.mark_failed(job_id, "still broken")

    job = queue.get(job_id)
    assert job["status"] == "dead_letter"
    assert job["retry_count"] == 4
    assert job["error"] == "still broken"
