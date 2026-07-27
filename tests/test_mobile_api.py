from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.mobile_api import MobileRuntime, MobileSettings, create_mobile_router
from app.mobile_api.kafka_bus import OutboxPublisher, consumer_config, decode_job_event, producer_config
from app.mobile_api.notification_worker import NotificationWorker
from app.mobile_api.object_store import S3ObjectStore
from app.mobile_api.store import MobileStore
from app.mobile_api.wechat_services import ContentSafetyRejected
from app.workflow.graph import plan_node
from app.workflow.state import create_initial_state


def _runtime(
    tmp_path: Path,
    workflow_runner=None,
    settings_overrides=None,
    wechat_server_api=None,
    media_moderation_gateway=None,
) -> MobileRuntime:
    settings_values = dict(
        db_path=tmp_path / "mobile.db",
        object_root=tmp_path / "objects",
        workflow_root=tmp_path / "runs",
        wechat_auth_mode="mock",
        identity_secret="test-secret",
        max_upload_bytes=1024,
    )
    settings_values.update(settings_overrides or {})
    settings = MobileSettings(**settings_values)
    kwargs = {"settings": settings}
    if workflow_runner is not None:
        kwargs["workflow_runner"] = workflow_runner
    if wechat_server_api is not None:
        kwargs["wechat_server_api"] = wechat_server_api
    if media_moderation_gateway is not None:
        kwargs["media_moderation_gateway"] = media_moderation_gateway
    return MobileRuntime(**kwargs)


def _client(runtime: MobileRuntime) -> TestClient:
    app = FastAPI()
    app.include_router(create_mobile_router(runtime))
    return TestClient(app)


def _login(client: TestClient, code: str = "user-a") -> tuple[dict, dict[str, str]]:
    payload = client.post("/api/v1/mobile/session/wechat", json={"code": code}).json()
    return payload, {"authorization": f"Bearer {payload['access_token']}"}


def test_mobile_login_refresh_and_auth_required(tmp_path):
    client = _client(_runtime(tmp_path))

    assert client.get("/api/v1/mobile/ready").json() == {"status": "ready", "database": "ok"}
    assert client.get("/api/v1/mobile/jobs").status_code == 401
    session, headers = _login(client)
    assert session["user"]["id"].startswith("usr_")
    assert client.get("/api/v1/mobile/jobs", headers=headers).json() == []

    refreshed = client.post(
        "/api/v1/mobile/session/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != session["access_token"]
    assert client.get("/api/v1/mobile/jobs", headers=headers).status_code == 401


def test_mobile_upload_is_bounded_and_owned(tmp_path):
    client = _client(_runtime(tmp_path))
    _, owner_headers = _login(client, "owner")
    _, other_headers = _login(client, "other")

    initialized = client.post(
        "/api/v1/mobile/uploads/init",
        headers=owner_headers,
        json={"filename": "brief.json", "content_type": "application/json", "size": 2},
    )
    assert initialized.status_code == 201
    asset_id = initialized.json()["id"]

    assert client.put(
        f"/api/v1/mobile/uploads/{asset_id}/content", headers=other_headers, content=b"{}"
    ).status_code == 404
    uploaded = client.put(
        f"/api/v1/mobile/uploads/{asset_id}/content", headers=owner_headers, content=b"{}"
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["status"] == "uploaded"

    too_large = client.post(
        "/api/v1/mobile/uploads/init",
        headers=owner_headers,
        json={"filename": "large.mp4", "content_type": "video/mp4", "size": 2048},
    )
    assert too_large.status_code == 400
    assert too_large.json()["detail"]["code"] == "INVALID_UPLOAD"

    forged = client.post(
        "/api/v1/mobile/uploads/init",
        headers=owner_headers,
        json={"filename": "fake.png", "content_type": "image/png", "size": 4},
    ).json()
    rejected = client.put(
        f"/api/v1/mobile/uploads/{forged['id']}/content", headers=owner_headers, content=b"fake"
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "INVALID_UPLOAD"


def test_mobile_jobs_are_idempotent_and_tenant_isolated(tmp_path):
    client = _client(_runtime(tmp_path))
    _, owner_headers = _login(client, "owner")
    _, other_headers = _login(client, "other")
    request = {
        "query": "分析宠物内容趋势",
        "route": "trend_report_path",
        "asset_ids": [],
        "allow_live": False,
    }

    missing_key = client.post("/api/v1/mobile/jobs", headers=owner_headers, json=request)
    assert missing_key.status_code == 400

    headers = {**owner_headers, "Idempotency-Key": "same-request"}
    created = client.post("/api/v1/mobile/jobs", headers=headers, json=request)
    duplicate = client.post("/api/v1/mobile/jobs", headers=headers, json=request)
    assert created.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == created.json()["id"]
    assert len(client.get("/api/v1/mobile/jobs", headers=owner_headers).json()) == 1
    assert client.get(
        f"/api/v1/mobile/jobs/{created.json()['id']}", headers=other_headers
    ).status_code == 404

    live_request = {**request, "allow_live": True}
    live = client.post(
        "/api/v1/mobile/jobs",
        headers={**owner_headers, "Idempotency-Key": "live-request"},
        json=live_request,
    )
    assert live.status_code == 400
    assert live.json()["detail"]["code"] == "INVALID_JOB"


def test_mobile_worker_creates_owned_report(tmp_path):
    calls = {}

    def fake_workflow(query, output_dir, progress_callback, **kwargs):
        calls.update(kwargs)
        progress_callback({"node": "trend_analyze", "percent": 60})
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "trend_report.md"
        report.write_text(f"# 报告\n\n{query}", encoding="utf-8")
        return {"report_path": str(report), "route": "trend_report_path"}

    runtime = _runtime(tmp_path, fake_workflow)
    client = _client(runtime)
    _, owner_headers = _login(client, "owner")
    _, other_headers = _login(client, "other")
    created = client.post(
        "/api/v1/mobile/jobs",
        headers={**owner_headers, "Idempotency-Key": "worker-request"},
        json={"query": "宠物趋势", "route": "trend_report_path"},
    ).json()

    completed = runtime.run_next_job()
    assert completed["status"] == "succeeded"
    assert completed["progress"] == {"stage": "completed", "percent": 100}
    assert calls["route_override"] == "trend_report_path"

    reports = client.get("/api/v1/mobile/reports", headers=owner_headers).json()
    assert len(reports) == 1
    report_id = reports[0]["id"]
    report = client.get(f"/api/v1/mobile/reports/{report_id}", headers=owner_headers)
    assert report.status_code == 200
    assert "# 报告" in report.json()["markdown"]
    assert client.get(f"/api/v1/mobile/reports/{report_id}", headers=other_headers).status_code == 404


def test_mobile_cancel_retry_and_account_deletion(tmp_path):
    runtime = _runtime(tmp_path)
    client = _client(runtime)
    session, headers = _login(client, "owner")
    created = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "cancel-request"},
        json={"query": "宠物趋势", "route": "trend_report_path"},
    ).json()

    cancelled = client.post(f"/api/v1/mobile/jobs/{created['id']}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancelled"
    retried = client.post(f"/api/v1/mobile/jobs/{created['id']}/retry", headers=headers)
    assert retried.json()["status"] == "queued"
    assert retried.json()["retry_count"] == 1

    consent = client.post(
        "/api/v1/mobile/subscriptions/task-completed",
        headers=headers,
        json={"granted": True, "version": "v1"},
    )
    assert consent.status_code == 200

    exported = client.get("/api/v1/mobile/me/export", headers=headers)
    assert exported.status_code == 200
    assert len(exported.json()["jobs"]) == 1
    assert "identity_hash" not in exported.json()["user"]
    assert "openid" not in exported.text.lower()

    data_deleted = client.delete("/api/v1/mobile/me/data", headers=headers)
    assert data_deleted.status_code == 204
    assert client.get("/api/v1/mobile/jobs", headers=headers).json() == []

    deleted = client.delete("/api/v1/mobile/me", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/mobile/jobs", headers=headers).status_code == 401
    assert client.post(
        "/api/v1/mobile/session/refresh", json={"refresh_token": session["refresh_token"]}
    ).status_code == 401


def test_workflow_route_and_inputs_can_be_overridden_internally():
    state = create_initial_state(
        "普通描述",
        route_override="imitation_plan_path",
        input_overrides={"reference_video_path": "uploads/reference.mp4", "unsafe": "ignored"},
    )

    planned = plan_node(state)

    assert planned["route"] == "imitation_plan_path"
    assert planned["plan"]["route"] == "imitation_plan_path"
    assert planned["reference_video_path"] == "uploads/reference.mp4"
    assert "unsafe" not in planned


def test_idempotency_key_rejects_a_different_request(tmp_path):
    client = _client(_runtime(tmp_path))
    _, headers = _login(client)
    request_headers = {**headers, "Idempotency-Key": "same-key"}

    first = client.post(
        "/api/v1/mobile/jobs",
        headers=request_headers,
        json={"query": "first", "route": "trend_report_path"},
    )
    second = client.post(
        "/api/v1/mobile/jobs",
        headers=request_headers,
        json={"query": "second", "route": "trend_report_path"},
    )

    assert first.status_code == 202
    assert second.status_code == 400
    assert "different request" in second.json()["detail"]["message"]


def test_delete_user_data_removes_workflow_artifacts_but_keeps_session(tmp_path):
    runtime = _runtime(tmp_path)
    client = _client(runtime)
    session, headers = _login(client)
    user_id = session["user"]["id"]
    artifact_dir = runtime.settings.workflow_root / user_id / "job"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "trend_report.md").write_text("private", encoding="utf-8")

    response = client.delete("/api/v1/mobile/me/data", headers=headers)

    assert response.status_code == 204
    assert not (runtime.settings.workflow_root / user_id).exists()
    assert client.get("/api/v1/mobile/jobs", headers=headers).status_code == 200


def test_kafka_outbox_is_transactional_and_idempotently_published(tmp_path):
    store = MobileStore(tmp_path / "outbox.db", "secret", outbox_topic="mobile.jobs")
    user = store.create_or_get_user("openid")
    job, created = store.create_job(user["id"], "query", "trend_report_path", [], False, "key")
    duplicate, duplicate_created = store.create_job(user["id"], "query", "trend_report_path", [], False, "key")
    producer = _FakeProducer()
    publisher = OutboxPublisher(store, producer, publisher_id="test-publisher")

    assert created is True
    assert duplicate_created is False
    assert duplicate["id"] == job["id"]
    assert publisher.publish_once() == 1
    assert publisher.publish_once() == 0
    topic, key, value = producer.messages[0]
    assert topic == "mobile.jobs"
    assert key == job["id"].encode()
    assert decode_job_event(value)["job_id"] == job["id"]


def test_kafka_configuration_disables_auto_commit_and_enables_idempotence(tmp_path):
    settings = MobileSettings(
        database_url="postgresql://db/mobile",
        object_root=tmp_path / "objects",
        workflow_root=tmp_path / "runs",
        queue_backend="kafka",
        kafka_bootstrap_servers="kafka:9092",
    )

    assert producer_config(settings)["enable.idempotence"] is True
    assert producer_config(settings)["acks"] == "all"
    assert consumer_config(settings)["enable.auto.commit"] is False
    assert consumer_config(settings)["max.poll.interval.ms"] == 3_600_000


class _FakeProducer:
    def __init__(self):
        self.messages = []
        self._callbacks = []

    def produce(self, *, topic, key, value, headers, on_delivery):
        self.messages.append((topic, key, value))
        self._callbacks.append(on_delivery)

    def flush(self, _timeout):
        for callback in self._callbacks:
            callback(None, None)
        self._callbacks.clear()
        return 0


def test_wechat_content_safety_checks_user_input_and_generated_report(tmp_path):
    safety = _FakeWeChatServer()

    def fake_workflow(query, output_dir, progress_callback, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "trend_report.md"
        report.write_text("# safe report", encoding="utf-8")
        return {"report_path": str(report), "route": kwargs["route_override"]}

    runtime = _runtime(
        tmp_path,
        fake_workflow,
        settings_overrides={"wechat_content_security_enabled": True},
        wechat_server_api=safety,
    )
    client = _client(runtime)
    _, headers = _login(client, "safe-user")

    created = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "safe"},
        json={"query": "safe query", "route": "trend_report_path"},
    )
    assert created.status_code == 202
    assert runtime.run_next_job()["status"] == "succeeded"
    assert safety.checked == [("mock:safe-user", "safe query"), ("mock:safe-user", "# safe report")]

    rejected = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "rejected"},
        json={"query": "unsafe query", "route": "trend_report_path"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "CONTENT_REJECTED"


def test_one_time_subscription_consent_is_sent_from_notification_outbox(tmp_path):
    sender = _FakeWeChatServer()

    def fake_workflow(query, output_dir, progress_callback, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "trend_report.md"
        report.write_text("# report", encoding="utf-8")
        return {"report_path": str(report), "route": kwargs["route_override"]}

    runtime = _runtime(
        tmp_path,
        fake_workflow,
        settings_overrides={"wechat_task_template_id": "template-id"},
        wechat_server_api=sender,
    )
    client = _client(runtime)
    _, headers = _login(client, "subscriber")
    assert client.post(
        "/api/v1/mobile/subscriptions/task-completed",
        headers=headers,
        json={"granted": True, "version": "v1"},
    ).status_code == 200

    for index in range(2):
        created = client.post(
            "/api/v1/mobile/jobs",
            headers={**headers, "Idempotency-Key": f"notification-{index}"},
            json={"query": f"job {index}", "route": "trend_report_path"},
        )
        assert created.status_code == 202
        assert runtime.run_next_job()["status"] == "succeeded"
        assert NotificationWorker(runtime, sender).run_once() is True

    assert [(openid, job["query"]) for openid, job in sender.sent] == [("mock:subscriber", "job 0")]


def test_mobile_login_rate_limit_is_persisted(tmp_path):
    client = _client(_runtime(tmp_path, settings_overrides={"login_rate_limit_per_minute": 1}))

    assert client.post("/api/v1/mobile/session/wechat", json={"code": "first"}).status_code == 200
    limited = client.post("/api/v1/mobile/session/wechat", json={"code": "second"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.json()["detail"]["code"] == "RATE_LIMITED"


def test_uploaded_media_must_pass_configured_moderation(tmp_path):
    moderation = _FakeMediaModeration()
    runtime = _runtime(
        tmp_path,
        settings_overrides={
            "media_moderation_mode": "webhook",
            "media_moderation_url": "https://moderation.invalid/check",
        },
        media_moderation_gateway=moderation,
    )
    client = _client(runtime)
    _, headers = _login(client)
    png = b"\x89PNG\r\n\x1a\n"

    accepted = client.post(
        "/api/v1/mobile/uploads/init",
        headers=headers,
        json={"filename": "accepted.png", "content_type": "image/png", "size": len(png)},
    ).json()
    accepted_upload = client.put(
        f"/api/v1/mobile/uploads/{accepted['id']}/content", headers=headers, content=png
    )
    assert accepted_upload.status_code == 200
    assert accepted_upload.json()["status"] == "uploaded"

    rejected = client.post(
        "/api/v1/mobile/uploads/init",
        headers=headers,
        json={"filename": "rejected.png", "content_type": "image/png", "size": len(png)},
    ).json()
    rejected_upload = client.put(
        f"/api/v1/mobile/uploads/{rejected['id']}/content", headers=headers, content=png
    )
    assert rejected_upload.status_code == 422
    assert rejected_upload.json()["detail"]["code"] == "CONTENT_REJECTED"
    rejected_asset = runtime.store.get_asset(accepted["user_id"], rejected["id"])
    assert rejected_asset["status"] == "rejected"
    assert not runtime.object_path(rejected_asset["object_key"]).exists()


def test_public_mobile_errors_include_request_id_header_and_body():
    from app.web_api import create_app

    response = TestClient(create_app()).get("/api/v1/mobile/jobs", headers={"x-request-id": "request-test"})

    assert response.status_code == 401
    assert response.headers["x-request-id"] == "request-test"
    assert response.json()["detail"]["request_id"] == "request-test"


def test_mobile_operational_metrics_require_admin_token(tmp_path):
    previous = os.environ.get("MOCHI_WEB_ADMIN_TOKEN")
    os.environ["MOCHI_WEB_ADMIN_TOKEN"] = "metrics-secret"
    try:
        runtime = _runtime(tmp_path)
        runtime.store.heartbeat("worker-test", "test-worker")
        client = _client(runtime)
        assert client.get("/api/v1/mobile/internal/metrics").status_code == 401
        response = client.get(
            "/api/v1/mobile/internal/metrics",
            headers={"X-Mochi-Admin-Token": "metrics-secret"},
        )
        assert response.status_code == 200
        assert "mochi_mobile_outbox_pending 0" in response.text
        assert "mochi_mobile_notifications" in response.text
        assert 'worker_type="test-worker"' in response.text
    finally:
        if previous is None:
            os.environ.pop("MOCHI_WEB_ADMIN_TOKEN", None)
        else:
            os.environ["MOCHI_WEB_ADMIN_TOKEN"] = previous


def test_production_settings_fail_closed_without_media_moderation(tmp_path):
    values = dict(
        environment="production",
        database_url="postgresql://db/mobile",
        object_backend="s3",
        s3_bucket="bucket",
        object_root=tmp_path / "objects",
        workflow_root=tmp_path / "runs",
        wechat_auth_mode="wechat",
        wechat_app_id="appid",
        wechat_app_secret="secret",
        identity_secret="production-secret",
        wechat_task_template_id="template",
        wechat_content_security_enabled=True,
        queue_backend="kafka",
        kafka_bootstrap_servers="kafka:9092",
        require_legal_consent=True,
    )
    try:
        MobileSettings(**values).validate()
    except ValueError as exc:
        assert "MEDIA_MODERATION" in str(exc)
    else:
        raise AssertionError("unsafe production settings were accepted")

    MobileSettings(
        **values,
        media_moderation_mode="webhook",
        media_moderation_url="https://moderation.example/check",
    ).validate()


def test_wechat_identity_secret_rotation_preserves_the_user(tmp_path):
    database = tmp_path / "rotation.db"
    original = MobileStore(database, "old-secret")
    user = original.create_or_get_user("openid-rotation")

    rotated = MobileStore(database, "new-secret", previous_identity_secrets=("old-secret",))
    migrated = rotated.create_or_get_user("openid-rotation")

    assert migrated["id"] == user["id"]
    assert rotated.get_user_openid(user["id"]) == "openid-rotation"
    assert len(rotated.list_jobs(user["id"])) == 0


def test_current_legal_consent_is_required_before_production_jobs(tmp_path):
    runtime = _runtime(
        tmp_path,
        settings_overrides={"require_legal_consent": True, "legal_consent_version": "legal-v2"},
    )
    client = _client(runtime)
    _, headers = _login(client)
    request = {"query": "query", "route": "trend_report_path"}

    denied = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "before-consent"},
        json=request,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "LEGAL_CONSENT_REQUIRED"

    outdated = client.post(
        "/api/v1/mobile/consents/legal",
        headers=headers,
        json={"granted": True, "version": "legal-v1"},
    )
    assert outdated.status_code == 409

    accepted = client.post(
        "/api/v1/mobile/consents/legal",
        headers=headers,
        json={"granted": True, "version": "legal-v2"},
    )
    assert accepted.status_code == 200
    created = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "after-consent"},
        json=request,
    )
    assert created.status_code == 202


def test_s3_upload_uses_bounded_presigned_post_without_loading_file_memory():
    calls = []

    class FakeS3Client:
        def generate_presigned_post(self, **kwargs):
            calls.append(kwargs)
            return {"url": "https://objects.example/upload", "fields": {"key": kwargs["Key"], "policy": "signed"}}

    previous = sys.modules.get("boto3")
    sys.modules["boto3"] = SimpleNamespace(client=lambda *_args, **_kwargs: FakeS3Client())
    try:
        store = S3ObjectStore(bucket="bucket", prefix="prefix", max_upload_bytes=1234)
        target = store.upload_target("users/user/file.mp4", "video/mp4", proxy_url="/unused")
    finally:
        if previous is None:
            sys.modules.pop("boto3", None)
        else:
            sys.modules["boto3"] = previous

    assert target.method == "POST"
    assert target.direct is True
    assert target.fields["policy"] == "signed"
    assert calls[0]["Conditions"][-1] == ["content-length-range", 1, 1234]


def test_expired_worker_lease_is_recovered_without_duplicate_completion(tmp_path):
    store = MobileStore(tmp_path / "lease.db", "secret")
    user = store.create_or_get_user("lease-user")
    job, _ = store.create_job(user["id"], "query", "trend_report_path", [], False, "lease-key")
    assert store.claim_job(job["id"], "dead-worker", 30)["status"] == "running"
    with store._connect() as conn:
        conn.execute("update jobs set lease_until = ? where id = ?", ("2000-01-01T00:00:00+00:00", job["id"]))

    recovered = store.claim_next_job("replacement-worker", 30)
    assert recovered["id"] == job["id"]
    assert recovered["worker_id"] == "replacement-worker"
    assert store.complete_job(job["id"], "report-id", "dead-worker") is False


def test_kafka_outbox_requeues_and_republishes_expired_job(tmp_path):
    store = MobileStore(tmp_path / "kafka-recovery.db", "secret", outbox_topic="mobile.jobs")
    user = store.create_or_get_user("recovery-user")
    job, _ = store.create_job(user["id"], "query", "trend_report_path", [], False, "recovery-key")
    producer = _FakeProducer()
    publisher = OutboxPublisher(store, producer, publisher_id="recovery-publisher")
    assert publisher.publish_once() == 1
    assert store.claim_job(job["id"], "dead-worker", 30)
    assert store.renew_job_lease(job["id"], "dead-worker", 30) is True
    assert store.renew_job_lease(job["id"], "other-worker", 30) is False
    with store._connect() as conn:
        conn.execute("update jobs set lease_until = ? where id = ?", ("2000-01-01T00:00:00+00:00", job["id"]))

    assert publisher.publish_once() == 1
    recovered = store.get_job(user["id"], job["id"])
    assert recovered["status"] == "queued"
    assert recovered["progress"]["stage"] == "recovered"
    assert len(producer.messages) == 2
    assert decode_job_event(producer.messages[-1][2])["job_id"] == job["id"]


def test_new_job_kill_switch_keeps_read_api_available(tmp_path):
    runtime = _runtime(tmp_path, settings_overrides={"accept_new_jobs": False})
    client = _client(runtime)
    _, headers = _login(client)
    response = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "maintenance"},
        json={"query": "query", "route": "trend_report_path"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "NEW_JOBS_DISABLED"
    assert client.get("/api/v1/mobile/jobs", headers=headers).status_code == 200


def test_upload_completion_is_idempotent_after_content_scan(tmp_path):
    moderation = _FakeMediaModeration()
    runtime = _runtime(tmp_path, media_moderation_gateway=moderation)
    client = _client(runtime)
    _, headers = _login(client)
    content = b"\x89PNG\r\n\x1a\nimage"
    asset = client.post(
        "/api/v1/mobile/uploads/init",
        headers=headers,
        json={"filename": "image.png", "content_type": "image/png", "size": len(content)},
    ).json()
    assert client.put(f"/api/v1/mobile/uploads/{asset['id']}/content", headers=headers, content=content).status_code == 200
    assert client.post(f"/api/v1/mobile/uploads/{asset['id']}/complete", headers=headers).status_code == 200
    assert client.post(f"/api/v1/mobile/uploads/{asset['id']}/complete", headers=headers).status_code == 200
    assert len(moderation.checked) == 1


def test_reference_video_route_uploads_and_injects_owned_video(tmp_path):
    calls = {}

    def fake_workflow(query, output_dir, progress_callback, **kwargs):
        calls.update(kwargs)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "trend_report.md"
        report.write_text("# reference", encoding="utf-8")
        return {"report_path": str(report), "route": kwargs["route_override"]}

    runtime = _runtime(tmp_path, fake_workflow)
    client = _client(runtime)
    _, headers = _login(client)
    video = b"\x00\x00\x00\x18ftypisom"
    asset = client.post(
        "/api/v1/mobile/uploads/init",
        headers=headers,
        json={"filename": "reference.mp4", "content_type": "video/mp4", "size": len(video)},
    ).json()
    assert client.put(
        f"/api/v1/mobile/uploads/{asset['id']}/content", headers=headers, content=video
    ).status_code == 200
    created = client.post(
        "/api/v1/mobile/jobs",
        headers={**headers, "Idempotency-Key": "reference-job"},
        json={
            "query": "analyze reference",
            "route": "reference_video_imitation_path",
            "asset_ids": [asset["id"]],
        },
    )
    assert created.status_code == 202
    assert runtime.run_next_job()["status"] == "succeeded"
    assert calls["route_override"] == "reference_video_imitation_path"
    assert Path(calls["input_overrides"]["reference_video_path"]).is_file()


class _FakeWeChatServer:
    def __init__(self):
        self.checked = []
        self.sent = []

    def check_text(self, openid, content, *, scene=2):
        self.checked.append((openid, content))
        if "unsafe" in content:
            raise ContentSafetyRejected("unsafe content")

    def send_job_completed(self, openid, job):
        self.sent.append((openid, job))


class _FakeMediaModeration:
    def __init__(self):
        self.checked = []

    def check(self, asset, object_url):
        from app.mobile_api.media_moderation import MediaModerationRejected

        self.checked.append((asset["filename"], object_url))
        if asset["filename"].startswith("rejected"):
            raise MediaModerationRejected("rejected media")
