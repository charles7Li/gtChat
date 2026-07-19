from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


class SQLiteQueue:
    def __init__(self, db_path: str | Path = "events.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def enqueue(self, job_type: str, payload: dict, dedupe_key: str | None = None) -> str:
        now = _now()
        job_id = f"job_{uuid4().hex}"
        with self._connect() as conn:
            if dedupe_key:
                existing = conn.execute("select id from jobs where dedupe_key = ?", (dedupe_key,)).fetchone()
                if existing:
                    return str(existing["id"])
            conn.execute(
                """
                insert into jobs (id, type, payload_json, status, dedupe_key, run_after, retry_count, max_retries, error, created_at, updated_at)
                values (?, ?, ?, 'pending', ?, ?, 0, 3, null, ?, ?)
                """,
                (job_id, job_type, json.dumps(payload, ensure_ascii=False), dedupe_key, now, now, now),
            )
            self._add_event(conn, job_id, "enqueued", "")
        return job_id

    def claim_next(self, job_types: list[str], lease_seconds: int = 3600) -> dict | None:
        if not job_types:
            return None
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        placeholders = ",".join("?" for _ in job_types)
        with self._connect() as conn:
            conn.execute("begin immediate")
            conn.execute(
                """
                update jobs set status = 'pending', lease_until = null, updated_at = ?
                where status = 'running' and lease_until is not null and lease_until <= ?
                """,
                (now, now),
            )
            row = conn.execute(
                f"""
                select * from jobs
                where status = 'pending'
                  and (run_after is null or run_after <= ?)
                  and type in ({placeholders})
                order by created_at
                limit 1
                """,
                (now, *job_types),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "update jobs set status = 'running', lease_until = ?, updated_at = ? where id = ?",
                (lease_until, now, row["id"]),
            )
            self._add_event(conn, row["id"], "claimed", "")
            return self._row_to_job(row, status="running")

    def mark_done(self, job_id: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "update jobs set status = 'done', lease_until = null, error = null, updated_at = ? where id = ?",
                (now, job_id),
            )
            self._add_event(conn, job_id, "done", "")

    def mark_failed(self, job_id: str, error: str) -> None:
        now = _now()
        with self._connect() as conn:
            row = conn.execute("select retry_count, max_retries from jobs where id = ?", (job_id,)).fetchone()
            if row is None:
                return
            retry_count = int(row["retry_count"]) + 1
            max_retries = int(row["max_retries"])
            status = "pending" if retry_count <= max_retries else "dead_letter"
            run_after = (datetime.now(timezone.utc) + timedelta(seconds=retry_count)).isoformat()
            conn.execute(
                """
                update jobs
                set status = ?, retry_count = ?, run_after = ?, lease_until = null, error = ?, updated_at = ?
                where id = ?
                """,
                (status, retry_count, run_after, error[:1000], now, job_id),
            )
            self._add_event(conn, job_id, "failed" if status == "pending" else "dead_letter", error[:1000])

    def get(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("select * from jobs where id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists jobs (
                  id text primary key,
                  type text not null,
                  payload_json text not null,
                  status text not null,
                  dedupe_key text unique,
                  run_after text,
                  retry_count integer not null default 0,
                  max_retries integer not null default 3,
                  error text,
                  lease_until text,
                  created_at text not null,
                  updated_at text not null
                );
                create index if not exists idx_jobs_status_run_after on jobs(status, run_after);
                create table if not exists job_events (
                  id text primary key,
                  job_id text not null,
                  event_type text not null,
                  message text,
                  created_at text not null
                );
                """
            )
            columns = {str(row["name"]) for row in conn.execute("pragma table_info(jobs)")}
            if "lease_until" not in columns:
                conn.execute("alter table jobs add column lease_until text")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma journal_mode = wal")
        conn.execute("pragma busy_timeout = 10000")
        return conn

    def _add_event(self, conn: sqlite3.Connection, job_id: str, event_type: str, message: str) -> None:
        conn.execute(
            "insert into job_events (id, job_id, event_type, message, created_at) values (?, ?, ?, ?, ?)",
            (f"evt_{uuid4().hex}", job_id, event_type, message, _now()),
        )

    def _row_to_job(self, row: sqlite3.Row, *, status: str | None = None) -> dict:
        return {
            "id": row["id"],
            "type": row["type"],
            "payload": json.loads(row["payload_json"]),
            "status": status or row["status"],
            "dedupe_key": row["dedupe_key"],
            "run_after": row["run_after"],
            "retry_count": row["retry_count"],
            "max_retries": row["max_retries"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
