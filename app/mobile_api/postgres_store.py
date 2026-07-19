from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import uuid4

from .store import MobileStore, _job_from_row, _now, _request_hash


class PostgresMobileStore(MobileStore):
    """PostgreSQL implementation of MobileStore with a transactional job queue."""

    def __init__(
        self,
        database_url: str,
        identity_secret: str,
        *,
        outbox_topic: str | None = None,
        notifications_enabled: bool = False,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
    ) -> None:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - depends on production extra
            raise RuntimeError("PostgreSQL mobile store requires the mobile-prod dependency extra") from exc
        self.database_url = database_url
        self.identity_secret = identity_secret.encode("utf-8")
        self.outbox_topic = outbox_topic
        self.notifications_enabled = notifications_enabled
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=pool_min_size,
            max_size=pool_max_size,
            kwargs={"autocommit": False},
            open=True,
        )
        self._init_db()

    def close(self) -> None:
        self.pool.close()

    def create_or_get_user(self, openid: str) -> dict[str, Any]:
        identity_hash = hmac.new(self.identity_secret, openid.encode("utf-8"), hashlib.sha256).hexdigest()
        openid_ciphertext = self._encrypt_openid(openid)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into users (id, identity_hash, openid_ciphertext, status, created_at, updated_at)
                values (?, ?, ?, 'active', ?, ?)
                on conflict (identity_hash) do update set
                  openid_ciphertext = coalesce(users.openid_ciphertext, excluded.openid_ciphertext),
                  updated_at = users.updated_at
                returning *
                """,
                (f"usr_{uuid4().hex}", identity_hash, openid_ciphertext, now, now),
            ).fetchone()
            if row["status"] != "active":
                raise PermissionError("account is not active")
            return dict(row)

    def create_job(
        self,
        user_id: str,
        query: str,
        route: str,
        asset_ids: list[str],
        allow_live: bool,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        request_hash = _request_hash(query, route, asset_ids, allow_live)
        job_id = f"mjob_{uuid4().hex}"
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into jobs
                  (id, user_id, query, route, asset_ids_json, allow_live, status, progress_json,
                   error_code, error_message, idempotency_key, request_hash, retry_count, cancel_requested,
                   worker_id, lease_until, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, 'queued', ?, null, null, ?, ?, 0, 0, null, null, ?, ?)
                on conflict (user_id, idempotency_key) do nothing
                returning *
                """,
                (
                    job_id,
                    user_id,
                    query,
                    route,
                    json.dumps(asset_ids),
                    int(allow_live),
                    json.dumps({"stage": "queued", "percent": 0}),
                    idempotency_key,
                    request_hash,
                    now,
                    now,
                ),
            ).fetchone()
            if row:
                self._enqueue_job_event(conn, job_id, user_id, 0)
                return _job_from_row(row), True
            existing = conn.execute(
                "select * from jobs where user_id = ? and idempotency_key = ? for update",
                (user_id, idempotency_key),
            ).fetchone()
            if not existing:
                raise RuntimeError("idempotent job insert lost without an existing row")
            if existing["request_hash"] and existing["request_hash"] != request_hash:
                raise ValueError("idempotency key was already used for a different request")
            if not existing["request_hash"]:
                conn.execute("update jobs set request_hash = ? where id = ?", (request_hash, existing["id"]))
            return _job_from_row(existing), False

    def claim_job(self, job_id: str, worker_id: str = "local-worker", lease_seconds: int = 300) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            claimed = conn.execute(
                """
                update jobs set status = 'running', progress_json = ?, worker_id = ?, lease_until = ?, updated_at = ?
                where id = ? and status = 'queued' returning *
                """,
                (json.dumps({"stage": "starting", "percent": 5}), worker_id, lease_until, now_text, job_id),
            ).fetchone()
            return _job_from_row(claimed) if claimed else None

    def claim_outbox(self, publisher_id: str, limit: int = 100, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        locked_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute(
                "update outbox_events set status = 'pending', publisher_id = null, locked_until = null "
                "where status = 'publishing' and locked_until <= ?",
                (now_text,),
            )
            rows = conn.execute(
                """
                select * from outbox_events where status = 'pending' and available_at <= ?
                order by created_at for update skip locked limit ?
                """,
                (now_text, max(1, min(limit, 500))),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "update outbox_events set status = 'publishing', publisher_id = ?, locked_until = ?, attempts = attempts + 1 where id = ?",
                    (publisher_id, locked_until, row["id"]),
                )
            return [self._outbox_from_row(row) for row in rows]

    def claim_notification(self, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        locked_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute(
                "update notification_outbox set status = 'pending', worker_id = null, locked_until = null "
                "where status = 'sending' and locked_until <= ?",
                (now_text,),
            )
            row = conn.execute(
                """
                select id from notification_outbox where status = 'pending' and available_at <= ?
                order by created_at for update skip locked limit 1
                """,
                (now_text,),
            ).fetchone()
            if not row:
                return None
            return conn.execute(
                """
                update notification_outbox set status = 'sending', worker_id = ?, locked_until = ?,
                  attempts = attempts + 1 where id = ? and status = 'pending' returning *
                """,
                (worker_id, locked_until, row["id"]),
            ).fetchone()

    def reserve_notification_consent(self, notification_id: str, worker_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            notification = conn.execute(
                "select * from notification_outbox where id = ? and status = 'sending' and worker_id = ? for update",
                (notification_id, worker_id),
            ).fetchone()
            if not notification:
                return None
            if notification["consent_id"]:
                return conn.execute("select * from consents where id = ?", (notification["consent_id"],)).fetchone()
            consent = conn.execute(
                """
                select * from consents where user_id = ? and consent_type = ? and granted = 1
                  and consumed_at is null order by created_at for update skip locked limit 1
                """,
                (notification["user_id"], notification["notification_type"]),
            ).fetchone()
            if not consent:
                return None
            now = _now()
            conn.execute(
                "update consents set consumed_at = ?, delivery_status = 'reserved' where id = ?",
                (now, consent["id"]),
            )
            conn.execute(
                "update notification_outbox set consent_id = ? where id = ? and worker_id = ?",
                (consent["id"], notification_id, worker_id),
            )
            return consent

    def claim_next_job(self, worker_id: str = "local-worker", lease_seconds: int = 300) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                update jobs set status = 'queued', worker_id = null, lease_until = null,
                  progress_json = ?, updated_at = ?
                where status = 'running' and lease_until is not null and lease_until <= ?
                """,
                (json.dumps({"stage": "recovered", "percent": 0}), now_text, now_text),
            )
            row = conn.execute(
                """
                select id from jobs where status = 'queued'
                order by created_at for update skip locked limit 1
                """
            ).fetchone()
            if not row:
                return None
            claimed = conn.execute(
                """
                update jobs set status = 'running', progress_json = ?, worker_id = ?, lease_until = ?, updated_at = ?
                where id = ? and status = 'queued' returning *
                """,
                (json.dumps({"stage": "starting", "percent": 5}), worker_id, lease_until, now_text, row["id"]),
            ).fetchone()
            return _job_from_row(claimed) if claimed else None

    def _init_db(self) -> None:
        with self._connect() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)

    @contextmanager
    def _connect(self) -> Iterator["_PostgresConnection"]:
        from psycopg.rows import dict_row

        with self.pool.connection() as raw:
            raw.row_factory = dict_row
            yield _PostgresConnection(raw)


class _PostgresConnection:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        normalized = " ".join(query.strip().lower().split())
        if normalized == "begin immediate":
            return self.connection.execute("select 1")
        return self.connection.execute(_postgres_placeholders(query), params)


def _postgres_placeholders(query: str) -> str:
    return query.replace("?", "%s")


_SCHEMA = (
    """
    create table if not exists users (
      id text primary key, identity_hash text not null unique, openid_ciphertext text, status text not null,
      created_at text not null, updated_at text not null, deleted_at text
    )
    """,
    "alter table users add column if not exists openid_ciphertext text",
    """
    create table if not exists sessions (
      id text primary key, user_id text not null references users(id) on delete cascade,
      access_hash text not null unique, refresh_hash text not null unique,
      access_expires_at text not null, refresh_expires_at text not null,
      revoked_at text, created_at text not null
    )
    """,
    """
    create table if not exists assets (
      id text primary key, user_id text not null references users(id) on delete cascade,
      filename text not null, content_type text not null, file_type text not null, size bigint not null,
      object_key text not null unique, status text not null, created_at text not null, updated_at text not null
    )
    """,
    """
    create table if not exists jobs (
      id text primary key, user_id text not null references users(id) on delete cascade,
      query text not null, route text not null, asset_ids_json text not null, allow_live integer not null,
      status text not null, progress_json text not null, error_code text, error_message text,
      idempotency_key text not null, retry_count integer not null default 0,
      cancel_requested integer not null default 0, report_id text, request_hash text,
      worker_id text, lease_until text, created_at text not null, updated_at text not null,
      unique(user_id, idempotency_key)
    )
    """,
    "create index if not exists idx_mobile_jobs_user_created on jobs(user_id, created_at desc)",
    "create index if not exists idx_mobile_jobs_status on jobs(status, created_at)",
    """
    create table if not exists reports (
      id text primary key, user_id text not null references users(id) on delete cascade,
      job_id text not null references jobs(id) on delete cascade,
      title text not null, summary text not null, markdown text not null, created_at text not null
    )
    """,
    """
    create table if not exists consents (
      id text primary key, user_id text not null references users(id) on delete cascade,
      consent_type text not null, version text not null, granted integer not null,
      consumed_at text, delivery_status text, created_at text not null
    )
    """,
    "alter table consents add column if not exists consumed_at text",
    "alter table consents add column if not exists delivery_status text",
    """
    create table if not exists notification_outbox (
      id text primary key, user_id text not null references users(id) on delete cascade,
      job_id text not null references jobs(id) on delete cascade, notification_type text not null,
      consent_id text references consents(id) on delete set null, status text not null,
      attempts integer not null default 0, available_at text not null, worker_id text,
      locked_until text, sent_at text, last_error text, created_at text not null,
      unique(job_id, notification_type)
    )
    """,
    "create index if not exists idx_mobile_notifications_pending on notification_outbox(status, available_at, created_at)",
    """
    create table if not exists audit_events (
      id text primary key, user_id text, event_type text not null, request_id text,
      details_json text not null, created_at text not null
    )
    """,
    """
    create table if not exists outbox_events (
      id text primary key, aggregate_id text not null, event_type text not null,
      topic text not null, message_key text not null, payload_json text not null,
      status text not null, attempts integer not null default 0, available_at text not null,
      publisher_id text, locked_until text, published_at text, last_error text, created_at text not null
    )
    """,
    "create index if not exists idx_mobile_outbox_pending on outbox_events(status, available_at, created_at)",
)
