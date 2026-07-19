from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.mobile_api import MobileRuntime, MobileSettings, create_mobile_router
from app.mobile_api.kafka_bus import OutboxPublisher, consumer_config, decode_job_event, producer_config
from app.mobile_api.notification_worker import NotificationWorker
from app.mobile_api.store import MobileStore
from app.mobile_api.wechat_services import ContentSafetyRejected
from app.workflow.graph import plan_node
from app.workflow.state import create_initial_state


def _runtime(tmp_path: Path, workflow_runner=None, settings_overrides=None, wechat_server_api=None) -> MobileRuntime:
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
