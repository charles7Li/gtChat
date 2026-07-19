from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class MobileStore:
    def __init__(
        self,
        db_path: str | Path,
        identity_secret: str,
        *,
        outbox_topic: str | None = None,
        notifications_enabled: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.identity_secret = identity_secret.encode("utf-8")
        self.outbox_topic = outbox_topic
        self.notifications_enabled = notifications_enabled
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create_or_get_user(self, openid: str) -> dict[str, Any]:
        identity_hash = hmac.new(self.identity_secret, openid.encode("utf-8"), hashlib.sha256).hexdigest()
        openid_ciphertext = self._encrypt_openid(openid)
        now = _now()
        with self._connect() as conn:
            row = conn.execute("select * from users where identity_hash = ?", (identity_hash,)).fetchone()
            if row:
                if row["status"] != "active":
                    raise PermissionError("account is not active")
                if not row["openid_ciphertext"]:
                    conn.execute("update users set openid_ciphertext = ?, updated_at = ? where id = ?", (openid_ciphertext, now, row["id"]))
                return dict(row)
            user_id = f"usr_{uuid4().hex}"
            conn.execute(
                "insert into users (id, identity_hash, openid_ciphertext, status, created_at, updated_at) values (?, ?, ?, 'active', ?, ?)",
                (user_id, identity_hash, openid_ciphertext, now, now),
            )
            return {"id": user_id, "identity_hash": identity_hash, "status": "active", "created_at": now, "updated_at": now}

    def get_user_openid(self, user_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("select openid_ciphertext from users where id = ? and status = 'active'", (user_id,)).fetchone()
        if not row or not row["openid_ciphertext"]:
            return None
        return self._decrypt_openid(str(row["openid_ciphertext"]))

    def create_session(self, user_id: str, access_ttl: int, refresh_ttl: int) -> dict[str, Any]:
        with self._connect() as conn:
            return self._create_session(conn, user_id, access_ttl, refresh_ttl)

    def _create_session(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        access_ttl: int,
        refresh_ttl: int,
    ) -> dict[str, Any]:
        access_token = f"msa_{secrets.token_urlsafe(32)}"
        refresh_token = f"msr_{secrets.token_urlsafe(40)}"
        now = datetime.now(timezone.utc)
        session_id = f"ses_{uuid4().hex}"
        conn.execute(
            """
            insert into sessions
              (id, user_id, access_hash, refresh_hash, access_expires_at, refresh_expires_at, revoked_at, created_at)
            values (?, ?, ?, ?, ?, ?, null, ?)
            """,
            (
                session_id,
                user_id,
                _token_hash(access_token),
                _token_hash(refresh_token),
                (now + timedelta(seconds=access_ttl)).isoformat(),
                (now + timedelta(seconds=refresh_ttl)).isoformat(),
                now.isoformat(),
            ),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": access_ttl,
            "token_type": "bearer",
        }

    def resolve_access_token(self, token: str) -> dict[str, Any] | None:
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                """
                select users.* from sessions
                join users on users.id = sessions.user_id
                where sessions.access_hash = ? and sessions.revoked_at is null
                  and sessions.access_expires_at > ? and users.status = 'active'
                """,
                (_token_hash(token), now),
            ).fetchone()
            return dict(row) if row else None

    def rotate_session(self, refresh_token: str, access_ttl: int, refresh_ttl: int) -> dict[str, Any] | None:
        now = _now()
        with self._connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                """
                select * from sessions where refresh_hash = ? and revoked_at is null and refresh_expires_at > ?
                """,
                (_token_hash(refresh_token), now),
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                "update sessions set revoked_at = ? where id = ? and revoked_at is null",
                (now, row["id"]),
            ).rowcount
            if updated != 1:
                return None
            return self._create_session(conn, str(row["user_id"]), access_ttl, refresh_ttl)

    def create_asset(self, user_id: str, filename: str, content_type: str, file_type: str, size: int) -> dict[str, Any]:
        asset_id = f"ast_{uuid4().hex}"
        object_key = f"users/{user_id}/assets/{asset_id}/{filename}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                insert into assets (id, user_id, filename, content_type, file_type, size, object_key, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (asset_id, user_id, filename, content_type, file_type, size, object_key, now, now),
            )
        return self.get_asset(user_id, asset_id) or {}

    def get_asset(self, user_id: str, asset_id: str) -> dict[str, Any] | None:
        return self._owned_row("assets", user_id, asset_id)

    def complete_asset(self, user_id: str, asset_id: str, actual_size: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "update assets set status = 'uploaded', size = ?, updated_at = ? where id = ? and user_id = ?",
                (actual_size, _now(), asset_id, user_id),
            )
        return self.get_asset(user_id, asset_id)

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
        with self._connect() as conn:
            conn.execute("begin immediate")
            existing = conn.execute(
                "select * from jobs where user_id = ? and idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] and existing["request_hash"] != request_hash:
                    raise ValueError("idempotency key was already used for a different request")
                if not existing["request_hash"]:
                    conn.execute("update jobs set request_hash = ? where id = ?", (request_hash, existing["id"]))
                return _job_from_row(existing), False
            job_id = f"mjob_{uuid4().hex}"
            conn.execute(
                """
                insert into jobs
                  (id, user_id, query, route, asset_ids_json, allow_live, status, progress_json,
                   error_code, error_message, idempotency_key, request_hash, retry_count, cancel_requested,
                   worker_id, lease_until, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, 'queued', ?, null, null, ?, ?, 0, 0, null, null, ?, ?)
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
            )
            row = conn.execute("select * from jobs where id = ?", (job_id,)).fetchone()
            self._enqueue_job_event(conn, job_id, user_id, 0)
            return _job_from_row(row), True

    def list_jobs(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select * from jobs where user_id = ? order by created_at desc limit ? offset ?",
                (user_id, limit, offset),
            ).fetchall()
            return [_job_from_row(row) for row in rows]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("select * from jobs where id = ? and user_id = ?", (job_id, user_id)).fetchone()
            return _job_from_row(row) if row else None

    def cancel_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        now = _now()
        with self._connect() as conn:
            row = conn.execute("select status from jobs where id = ? and user_id = ?", (job_id, user_id)).fetchone()
            if not row:
                return None
            if row["status"] == "queued":
                conn.execute("update jobs set status = 'cancelled', updated_at = ? where id = ?", (now, job_id))
            elif row["status"] == "running":
                conn.execute("update jobs set cancel_requested = 1, updated_at = ? where id = ?", (now, job_id))
        return self.get_job(user_id, job_id)

    def retry_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        now = _now()
        with self._connect() as conn:
            row = conn.execute("select status, retry_count from jobs where id = ? and user_id = ?", (job_id, user_id)).fetchone()
            if not row:
                return None
            if row["status"] not in {"failed", "cancelled"}:
                raise ValueError("job is not retryable")
            conn.execute(
                """
                update jobs set status = 'queued', progress_json = ?, error_code = null, error_message = null,
                  retry_count = retry_count + 1, cancel_requested = 0, worker_id = null,
                  lease_until = null, updated_at = ? where id = ?
                """,
                (json.dumps({"stage": "queued", "percent": 0}), now, job_id),
            )
            self._enqueue_job_event(conn, job_id, user_id, int(row["retry_count"]) + 1)
        return self.get_job(user_id, job_id)

    def claim_job(self, job_id: str, worker_id: str = "local-worker", lease_seconds: int = 300) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute("begin immediate")
            updated = conn.execute(
                """
                update jobs set status = 'running', progress_json = ?, worker_id = ?, lease_until = ?, updated_at = ?
                where id = ? and status = 'queued'
                """,
                (json.dumps({"stage": "starting", "percent": 5}), worker_id, lease_until, now_text, job_id),
            ).rowcount
            if updated != 1:
                return None
            return _job_from_row(conn.execute("select * from jobs where id = ?", (job_id,)).fetchone())

    def claim_outbox(self, publisher_id: str, limit: int = 100, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        locked_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute("begin immediate")
            conn.execute(
                "update outbox_events set status = 'pending', publisher_id = null, locked_until = null "
                "where status = 'publishing' and locked_until <= ?",
                (now_text,),
            )
            rows = conn.execute(
                "select * from outbox_events where status = 'pending' and available_at <= ? order by created_at limit ?",
                (now_text, max(1, min(limit, 500))),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            for event_id in ids:
                conn.execute(
                    "update outbox_events set status = 'publishing', publisher_id = ?, locked_until = ?, attempts = attempts + 1 where id = ?",
                    (publisher_id, locked_until, event_id),
                )
            return [self._outbox_from_row(row) for row in rows]

    def mark_outbox_published(self, event_id: str, publisher_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "update outbox_events set status = 'published', published_at = ?, publisher_id = null, locked_until = null, last_error = null "
                "where id = ? and status = 'publishing' and publisher_id = ?",
                (_now(), event_id, publisher_id),
            )

    def release_outbox(self, event_id: str, publisher_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "update outbox_events set status = 'pending', publisher_id = null, locked_until = null, last_error = ? "
                "where id = ? and status = 'publishing' and publisher_id = ?",
                (error[:1000], event_id, publisher_id),
            )

    def claim_next_job(self, worker_id: str = "local-worker", lease_seconds: int = 300) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute("begin immediate")
            conn.execute(
                """
                update jobs set status = 'queued', worker_id = null, lease_until = null,
                  progress_json = ?, updated_at = ?
                where status = 'running' and lease_until is not null and lease_until <= ?
                """,
                (json.dumps({"stage": "recovered", "percent": 0}), now_text, now_text),
            )
            row = conn.execute("select * from jobs where status = 'queued' order by created_at limit 1").fetchone()
            if not row:
                return None
            conn.execute(
                """
                update jobs set status = 'running', progress_json = ?, worker_id = ?, lease_until = ?, updated_at = ?
                where id = ? and status = 'queued'
                """,
                (json.dumps({"stage": "starting", "percent": 5}), worker_id, lease_until, now_text, row["id"]),
            )
            claimed = conn.execute("select * from jobs where id = ?", (row["id"],)).fetchone()
            return _job_from_row(claimed)

    def update_job_progress(
        self,
        job_id: str,
        stage: str,
        percent: int,
        lease_seconds: int = 300,
        worker_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            sql = """
                update jobs set progress_json = ?, lease_until = ?, updated_at = ?
                where id = ? and status = 'running'
            """
            params: tuple[Any, ...] = (
                json.dumps({"stage": stage, "percent": max(0, min(percent, 99))}),
                lease_until,
                now.isoformat(),
                job_id,
            )
            if worker_id:
                sql += " and worker_id = ?"
                params += (worker_id,)
            updated = conn.execute(
                sql,
                params,
            ).rowcount
            return updated == 1

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("select cancel_requested from jobs where id = ?", (job_id,)).fetchone()
            return bool(row and row["cancel_requested"])

    def mark_job_cancelled(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                update jobs set status = 'cancelled', progress_json = ?, worker_id = null,
                  lease_until = null, updated_at = ? where id = ?
                """,
                (json.dumps({"stage": "cancelled", "percent": 100}), _now(), job_id),
            )

    def complete_job(self, job_id: str, report_id: str, worker_id: str | None = None) -> bool:
        with self._connect() as conn:
            sql = """
                update jobs set status = 'succeeded', progress_json = ?, report_id = ?,
                  worker_id = null, lease_until = null, updated_at = ?
                where id = ? and status = 'running' and cancel_requested = 0
            """
            params: tuple[Any, ...] = (
                json.dumps({"stage": "completed", "percent": 100}),
                report_id,
                _now(),
                job_id,
            )
            if worker_id:
                sql += " and worker_id = ?"
                params += (worker_id,)
            updated = conn.execute(
                sql,
                params,
            ).rowcount
            if updated == 1 and self.notifications_enabled:
                notification_id = f"ntf_{uuid4().hex}"
                now = _now()
                conn.execute(
                    """
                    insert into notification_outbox
                      (id, user_id, job_id, notification_type, consent_id, status, attempts,
                       available_at, worker_id, locked_until, sent_at, last_error, created_at)
                    select ?, user_id, id, 'task_completed', null, 'pending', 0,
                           ?, null, null, null, null, ? from jobs
                    where id = ? and not exists (
                      select 1 from notification_outbox where job_id = ? and notification_type = 'task_completed'
                    )
                    """,
                    (notification_id, now, now, job_id, job_id),
                )
            return updated == 1

    def fail_job(self, job_id: str, code: str, message: str, worker_id: str | None = None) -> None:
        with self._connect() as conn:
            sql = """
                update jobs set status = 'failed', error_code = ?, error_message = ?, progress_json = ?,
                  worker_id = null, lease_until = null, updated_at = ?
                where id = ? and status = 'running'
            """
            params: tuple[Any, ...] = (
                code,
                message[:1000],
                json.dumps({"stage": "failed", "percent": 100}),
                _now(),
                job_id,
            )
            if worker_id:
                sql += " and worker_id = ?"
                params += (worker_id,)
            conn.execute(
                sql,
                params,
            )

    def create_report(self, user_id: str, job_id: str, title: str, markdown: str, summary: str = "") -> dict[str, Any]:
        report_id = f"rpt_{uuid4().hex}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "insert into reports (id, user_id, job_id, title, summary, markdown, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                (report_id, user_id, job_id, title, summary, markdown, now),
            )
        return self.get_report(user_id, report_id) or {}

    def list_reports(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, user_id, job_id, title, summary, created_at from reports
                where user_id = ? order by created_at desc limit ? offset ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_report(self, user_id: str, report_id: str) -> dict[str, Any] | None:
        return self._owned_row("reports", user_id, report_id)

    def delete_report(self, user_id: str, report_id: str) -> None:
        with self._connect() as conn:
            conn.execute("delete from reports where id = ? and user_id = ?", (report_id, user_id))

    def save_consent(self, user_id: str, consent_type: str, version: str, granted: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "insert into consents (id, user_id, consent_type, version, granted, created_at) values (?, ?, ?, ?, ?, ?)",
                (f"cns_{uuid4().hex}", user_id, consent_type, version, int(granted), _now()),
            )

    def claim_notification(self, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        locked_until = (now + timedelta(seconds=max(lease_seconds, 30))).isoformat()
        with self._connect() as conn:
            conn.execute("begin immediate")
            conn.execute(
                "update notification_outbox set status = 'pending', worker_id = null, locked_until = null "
                "where status = 'sending' and locked_until <= ?",
                (now_text,),
            )
            row = conn.execute(
                "select * from notification_outbox where status = 'pending' and available_at <= ? order by created_at limit 1",
                (now_text,),
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                "update notification_outbox set status = 'sending', worker_id = ?, locked_until = ?, attempts = attempts + 1 "
                "where id = ? and status = 'pending'",
                (worker_id, locked_until, row["id"]),
            ).rowcount
            if updated != 1:
                return None
            claimed = conn.execute("select * from notification_outbox where id = ?", (row["id"],)).fetchone()
            return dict(claimed)

    def reserve_notification_consent(self, notification_id: str, worker_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute("begin immediate")
            notification = conn.execute(
                "select * from notification_outbox where id = ? and status = 'sending' and worker_id = ?",
                (notification_id, worker_id),
            ).fetchone()
            if not notification:
                return None
            if notification["consent_id"]:
                row = conn.execute("select * from consents where id = ?", (notification["consent_id"],)).fetchone()
                return dict(row) if row else None
            consent = conn.execute(
                """
                select * from consents where user_id = ? and consent_type = ? and granted = 1
                  and consumed_at is null order by created_at limit 1
                """,
                (notification["user_id"], notification["notification_type"]),
            ).fetchone()
            if not consent:
                return None
            now = _now()
            conn.execute(
                "update consents set consumed_at = ?, delivery_status = 'reserved' where id = ? and consumed_at is null",
                (now, consent["id"]),
            )
            conn.execute(
                "update notification_outbox set consent_id = ? where id = ? and worker_id = ?",
                (consent["id"], notification_id, worker_id),
            )
            return dict(consent)

    def get_job_internal(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("select * from jobs where id = ?", (job_id,)).fetchone()
            return _job_from_row(row) if row else None

    def finish_notification(self, notification_id: str, worker_id: str, status: str, error: str = "") -> None:
        if status not in {"sent", "skipped", "failed"}:
            raise ValueError("invalid notification status")
        with self._connect() as conn:
            row = conn.execute(
                "select consent_id from notification_outbox where id = ? and worker_id = ?",
                (notification_id, worker_id),
            ).fetchone()
            conn.execute(
                """
                update notification_outbox set status = ?, sent_at = ?, worker_id = null,
                  locked_until = null, last_error = ? where id = ? and status = 'sending' and worker_id = ?
                """,
                (status, _now() if status == "sent" else None, error[:1000] or None, notification_id, worker_id),
            )
            if row and row["consent_id"]:
                conn.execute(
                    "update consents set delivery_status = ? where id = ?",
                    (status, row["consent_id"]),
                )

    def retry_notification(self, notification_id: str, worker_id: str, error: str, delay_seconds: int = 30) -> None:
        available_at = (datetime.now(timezone.utc) + timedelta(seconds=max(delay_seconds, 1))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                update notification_outbox set status = 'pending', available_at = ?, worker_id = null,
                  locked_until = null, last_error = ? where id = ? and status = 'sending' and worker_id = ?
                """,
                (available_at, error[:1000], notification_id, worker_id),
            )

    def delete_user(self, user_id: str) -> list[str]:
        with self._connect() as conn:
            keys = [str(row["object_key"]) for row in conn.execute("select object_key from assets where user_id = ?", (user_id,))]
            conn.execute("delete from outbox_events where aggregate_id in (select id from jobs where user_id = ?)", (user_id,))
            conn.execute("delete from notification_outbox where user_id = ?", (user_id,))
            for table in ("consents", "reports", "jobs", "assets", "sessions"):
                conn.execute(f"delete from {table} where user_id = ?", (user_id,))
            conn.execute("delete from users where id = ?", (user_id,))
            return keys

    def delete_user_data(self, user_id: str) -> list[str]:
        with self._connect() as conn:
            keys = [str(row["object_key"]) for row in conn.execute("select object_key from assets where user_id = ?", (user_id,))]
            conn.execute("delete from outbox_events where aggregate_id in (select id from jobs where user_id = ?)", (user_id,))
            conn.execute("delete from notification_outbox where user_id = ?", (user_id,))
            for table in ("reports", "jobs", "assets"):
                conn.execute(f"delete from {table} where user_id = ?", (user_id,))
            return keys

    def _owned_row(self, table: str, user_id: str, object_id: str) -> dict[str, Any] | None:
        if table not in {"assets", "reports"}:
            raise ValueError("unsupported table")
        with self._connect() as conn:
            row = conn.execute(f"select * from {table} where id = ? and user_id = ?", (object_id, user_id)).fetchone()
            return dict(row) if row else None

    def _encrypt_openid(self, openid: str) -> str:
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(self.identity_secret).digest())
        return Fernet(key).encrypt(openid.encode("utf-8")).decode("ascii")

    def _decrypt_openid(self, ciphertext: str) -> str:
        from cryptography.fernet import Fernet, InvalidToken

        key = base64.urlsafe_b64encode(hashlib.sha256(self.identity_secret).digest())
        try:
            return Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("stored WeChat identity cannot be decrypted") from exc

    def _enqueue_job_event(self, conn: Any, job_id: str, user_id: str, retry_count: int) -> None:
        if not self.outbox_topic:
            return
        event_id = f"evt_{uuid4().hex}"
        now = _now()
        payload = {
            "schema_version": 1,
            "event_id": event_id,
            "event_type": "mobile.job.queued",
            "job_id": job_id,
            "user_id": user_id,
            "retry_count": retry_count,
            "occurred_at": now,
        }
        conn.execute(
            """
            insert into outbox_events
              (id, aggregate_id, event_type, topic, message_key, payload_json, status, attempts,
               available_at, publisher_id, locked_until, published_at, last_error, created_at)
            values (?, ?, 'mobile.job.queued', ?, ?, ?, 'pending', 0, ?, null, null, null, null, ?)
            """,
            (event_id, job_id, self.outbox_topic, job_id, json.dumps(payload, ensure_ascii=False), now, now),
        )

    @staticmethod
    def _outbox_from_row(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("pragma journal_mode = wal")
            conn.executescript(
                """
                create table if not exists users (
                  id text primary key, identity_hash text not null unique, openid_ciphertext text, status text not null,
                  created_at text not null, updated_at text not null, deleted_at text
                );
                create table if not exists sessions (
                  id text primary key, user_id text not null, access_hash text not null unique,
                  refresh_hash text not null unique, access_expires_at text not null, refresh_expires_at text not null,
                  revoked_at text, created_at text not null
                );
                create table if not exists assets (
                  id text primary key, user_id text not null, filename text not null, content_type text not null,
                  file_type text not null, size integer not null, object_key text not null unique, status text not null,
                  created_at text not null, updated_at text not null
                );
                create table if not exists jobs (
                  id text primary key, user_id text not null, query text not null, route text not null,
                  asset_ids_json text not null, allow_live integer not null, status text not null, progress_json text not null,
                  error_code text, error_message text, idempotency_key text not null, retry_count integer not null default 0,
                  cancel_requested integer not null default 0, report_id text, request_hash text,
                  worker_id text, lease_until text, created_at text not null, updated_at text not null,
                  unique(user_id, idempotency_key)
                );
                create index if not exists idx_mobile_jobs_user_created on jobs(user_id, created_at desc);
                create index if not exists idx_mobile_jobs_status on jobs(status, created_at);
                create table if not exists reports (
                  id text primary key, user_id text not null, job_id text not null, title text not null,
                  summary text not null, markdown text not null, created_at text not null
                );
                create table if not exists consents (
                  id text primary key, user_id text not null, consent_type text not null, version text not null,
                  granted integer not null, consumed_at text, delivery_status text, created_at text not null
                );
                create table if not exists notification_outbox (
                  id text primary key, user_id text not null, job_id text not null, notification_type text not null,
                  consent_id text, status text not null, attempts integer not null default 0, available_at text not null,
                  worker_id text, locked_until text, sent_at text, last_error text, created_at text not null,
                  unique(job_id, notification_type)
                );
                create index if not exists idx_mobile_notifications_pending
                  on notification_outbox(status, available_at, created_at);
                create table if not exists audit_events (
                  id text primary key, user_id text, event_type text not null, request_id text,
                  details_json text not null, created_at text not null
                );
                create table if not exists outbox_events (
                  id text primary key, aggregate_id text not null, event_type text not null,
                  topic text not null, message_key text not null, payload_json text not null,
                  status text not null, attempts integer not null default 0, available_at text not null,
                  publisher_id text, locked_until text, published_at text, last_error text, created_at text not null
                );
                create index if not exists idx_mobile_outbox_pending on outbox_events(status, available_at, created_at);
                """
            )
            self._ensure_column(conn, "jobs", "request_hash", "text")
            self._ensure_column(conn, "jobs", "worker_id", "text")
            self._ensure_column(conn, "jobs", "lease_until", "text")
            self._ensure_column(conn, "users", "openid_ciphertext", "text")
            self._ensure_column(conn, "consents", "consumed_at", "text")
            self._ensure_column(conn, "consents", "delivery_status", "text")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {str(row["name"]) for row in conn.execute(f"pragma table_info({table})")}
        if column not in columns:
            conn.execute(f"alter table {table} add column {column} {declaration}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        conn.execute("pragma busy_timeout = 10000")
        return conn


def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["asset_ids"] = json.loads(result.pop("asset_ids_json"))
    result["progress"] = json.loads(result.pop("progress_json"))
    result["allow_live"] = bool(result["allow_live"])
    result["cancel_requested"] = bool(result["cancel_requested"])
    return result


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _request_hash(query: str, route: str, asset_ids: list[str], allow_live: bool) -> str:
    payload = json.dumps(
        {"query": query, "route": route, "asset_ids": asset_ids, "allow_live": bool(allow_live)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
