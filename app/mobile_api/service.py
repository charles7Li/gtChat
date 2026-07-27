from __future__ import annotations

import os
import shutil
from pathlib import Path
from threading import Event, Thread
from typing import Any, AsyncIterable, Callable
from uuid import uuid4

from app.workflow import run_workflow

from .auth import WeChatGateway
from .media_moderation import MediaModerationGateway, MediaModerationRejected
from .object_store import LocalObjectStore, S3ObjectStore, UploadTarget
from .postgres_store import PostgresMobileStore
from .settings import MobileSettings
from .store import MobileStore
from .wechat_services import ContentSafetyRejected, WeChatServerApi


ALLOWED_ROUTES = {
    "trend_report_path",
    "imitation_plan_path",
    "reference_video_imitation_path",
    "commercial_data_analysis_path",
    "hotspot_auto_analysis_path",
}
ALLOWED_UPLOADS = {
    ".mp4": "video",
    ".mov": "video",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".csv": "csv",
    ".json": "json",
}


class MobileRuntime:
    def __init__(
        self,
        settings: MobileSettings | None = None,
        *,
        workflow_runner: Callable[..., dict[str, Any]] = run_workflow,
        wechat_gateway: WeChatGateway | None = None,
        wechat_server_api: WeChatServerApi | None = None,
        media_moderation_gateway: MediaModerationGateway | None = None,
    ) -> None:
        self.settings = settings or MobileSettings.from_env()
        self.settings.validate()
        self.store = self._create_store()
        self.objects = self._create_object_store()
        self.wechat = wechat_gateway or WeChatGateway(self.settings)
        self.wechat_server = wechat_server_api or WeChatServerApi(self.settings)
        self.media_moderation = media_moderation_gateway or MediaModerationGateway(self.settings)
        self.workflow_runner = workflow_runner
        self.worker_id = f"mobile-{uuid4().hex[:12]}"
        self.settings.workflow_root.mkdir(parents=True, exist_ok=True)

    def _create_store(self) -> MobileStore | PostgresMobileStore:
        outbox_topic = self.settings.kafka_topic if self.settings.queue_backend == "kafka" else None
        notifications_enabled = bool(self.settings.wechat_task_template_id)
        if self.settings.database_url:
            return PostgresMobileStore(
                self.settings.database_url,
                self.settings.identity_secret,
                outbox_topic=outbox_topic,
                notifications_enabled=notifications_enabled,
                initialize_schema=self.settings.auto_migrate,
                previous_identity_secrets=self.settings.identity_previous_secrets,
            )
        return MobileStore(
            self.settings.db_path,
            self.settings.identity_secret,
            outbox_topic=outbox_topic,
            notifications_enabled=notifications_enabled,
            previous_identity_secrets=self.settings.identity_previous_secrets,
        )

    def _create_object_store(self) -> LocalObjectStore | S3ObjectStore:
        if self.settings.object_backend == "s3":
            return S3ObjectStore(
                bucket=self.settings.s3_bucket,
                region=self.settings.s3_region,
                endpoint_url=self.settings.s3_endpoint_url,
                access_key_id=self.settings.s3_access_key_id,
                secret_access_key=self.settings.s3_secret_access_key,
                session_token=self.settings.s3_session_token,
                prefix=self.settings.s3_prefix,
                presign_ttl_seconds=self.settings.upload_url_ttl_seconds,
                max_upload_bytes=self.settings.max_upload_bytes,
            )
        return LocalObjectStore(self.settings.object_root)

    def login(self, code: str) -> dict[str, Any]:
        identity = self.wechat.exchange_code(code)
        user = self.store.create_or_get_user(identity.openid)
        session = self.store.create_session(
            user["id"], self.settings.access_token_ttl_seconds, self.settings.refresh_token_ttl_seconds
        )
        self.store.record_audit(user["id"], "login_succeeded", {})
        return {**session, "user": {"id": user["id"], "status": user["status"]}}

    def refresh(self, refresh_token: str) -> dict[str, Any] | None:
        return self.store.rotate_session(
            refresh_token, self.settings.access_token_ttl_seconds, self.settings.refresh_token_ttl_seconds
        )

    def prepare_upload(self, user_id: str, filename: str, content_type: str, size: int) -> dict[str, Any]:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or suffix not in ALLOWED_UPLOADS:
            raise ValueError("unsupported file type")
        if size < 0 or size > self.settings.max_upload_bytes:
            raise ValueError("file exceeds upload limit")
        return self.store.create_asset(user_id, safe_name, content_type, ALLOWED_UPLOADS[suffix], size)

    def upload_target(self, asset: dict[str, Any]) -> UploadTarget:
        return self.objects.upload_target(
            asset["object_key"],
            asset["content_type"],
            proxy_url=f"/api/v1/mobile/uploads/{asset['id']}/content",
        )

    def write_upload(self, user_id: str, asset_id: str, content: bytes) -> dict[str, Any]:
        asset = self.store.get_asset(user_id, asset_id)
        if not asset:
            raise FileNotFoundError("asset not found")
        if len(content) > self.settings.max_upload_bytes:
            raise UploadTooLarge("file exceeds upload limit")
        if asset["size"] and len(content) != asset["size"]:
            raise ValueError("uploaded size does not match declared size")
        _validate_content(asset["file_type"], asset["filename"], content)
        if not isinstance(self.objects, LocalObjectStore):
            raise ValueError("proxy upload is disabled for cloud object storage")
        target = self.objects.path(asset["object_key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return self._finish_asset_upload(user_id, asset, target, len(content))

    async def write_upload_stream(
        self,
        user_id: str,
        asset_id: str,
        chunks: AsyncIterable[bytes],
    ) -> dict[str, Any]:
        asset = self.store.get_asset(user_id, asset_id)
        if not asset:
            raise FileNotFoundError("asset not found")
        if not isinstance(self.objects, LocalObjectStore):
            raise ValueError("direct upload is required for cloud object storage")
        target = self.objects.path(asset["object_key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.part")
        size = 0
        try:
            with temporary.open("wb") as handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise UploadTooLarge("file exceeds upload limit")
                    handle.write(chunk)
            if asset["size"] and size != asset["size"]:
                raise ValueError("uploaded size does not match declared size")
            _validate_file_content(asset["file_type"], asset["filename"], temporary)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return self._finish_asset_upload(user_id, asset, target, size)

    def complete_upload(self, user_id: str, asset_id: str) -> dict[str, Any]:
        asset = self.store.get_asset(user_id, asset_id)
        if not asset:
            raise FileNotFoundError("asset not found")
        if asset["status"] == "uploaded":
            return asset
        if asset["status"] != "pending":
            raise ValueError("asset is not awaiting completion")
        if not self.objects.exists(asset["object_key"]):
            raise ValueError("upload content is missing")
        actual_size = self.objects.size(asset["object_key"])
        if actual_size > self.settings.max_upload_bytes:
            self.objects.delete(asset["object_key"])
            raise ValueError("file exceeds upload limit")
        if asset["size"] and actual_size != asset["size"]:
            self.objects.delete(asset["object_key"])
            raise ValueError("uploaded size does not match declared size")
        verification = self.settings.workflow_root / ".upload-verification" / asset["id"] / asset["filename"]
        try:
            self.objects.materialize(asset["object_key"], verification)
            _validate_file_content(asset["file_type"], asset["filename"], verification)
            return self._finish_asset_upload(user_id, asset, verification, actual_size)
        finally:
            if verification.exists():
                verification.unlink()

    def _finish_asset_upload(
        self,
        user_id: str,
        asset: dict[str, Any],
        verification_path: Path,
        actual_size: int,
    ) -> dict[str, Any]:
        try:
            if self.settings.wechat_content_security_enabled and asset["file_type"] in {"csv", "json"}:
                openid = self.store.get_user_openid(user_id)
                if not openid:
                    raise RuntimeError("WeChat identity is unavailable for content safety")
                self.wechat_server.check_text(openid, verification_path.read_text(encoding="utf-8-sig"))
            if asset["file_type"] in {"image", "video"}:
                self.media_moderation.check(asset, self.objects.download_url(asset["object_key"]))
        except (ContentSafetyRejected, MediaModerationRejected):
            self.objects.delete(asset["object_key"])
            self.store.reject_asset(user_id, asset["id"])
            raise
        return self.store.complete_asset(user_id, asset["id"], actual_size) or asset

    def create_job(
        self,
        user_id: str,
        query: str,
        route: str,
        asset_ids: list[str],
        allow_live: bool,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        if route not in ALLOWED_ROUTES:
            raise ValueError("unsupported route")
        if self.settings.require_legal_consent and not self.store.has_consent(
            user_id, "terms_and_privacy", self.settings.legal_consent_version
        ):
            raise LegalConsentRequired("accept the current user agreement and privacy policy first")
        if allow_live:
            raise ValueError("live collection is not available in the mini program")
        for asset_id in asset_ids:
            asset = self.store.get_asset(user_id, asset_id)
            if not asset or asset["status"] != "uploaded":
                raise ValueError(f"asset is not ready: {asset_id}")
        if route == "reference_video_imitation_path" and not self._find_asset(user_id, asset_ids, {"video"}):
            raise ValueError("reference video route requires an uploaded video")
        if route == "commercial_data_analysis_path" and not self._find_asset(user_id, asset_ids, {"csv", "json"}):
            raise ValueError("commercial data route requires an uploaded CSV or JSON file")
        openid = self.store.get_user_openid(user_id)
        if self.settings.wechat_content_security_enabled:
            if not openid:
                raise RuntimeError("WeChat identity is unavailable for content safety")
            self.wechat_server.check_text(openid, query.strip())
        return self.store.create_job(user_id, query.strip(), route, asset_ids, False, idempotency_key)

    def run_next_job(self) -> dict[str, Any] | None:
        job = self.store.claim_next_job(self.worker_id, self.settings.worker_lease_seconds)
        if not job:
            return None
        return self._run_claimed_job(job)

    def run_job(self, job_id: str) -> dict[str, Any] | None:
        """Claim one Kafka-addressed job; duplicate deliveries are harmless."""
        job = self.store.claim_job(job_id, self.worker_id, self.settings.worker_lease_seconds)
        if not job:
            return None
        return self._run_claimed_job(job)

    def _run_claimed_job(self, job: dict[str, Any]) -> dict[str, Any] | None:
        output_dir = self.settings.workflow_root / job["user_id"] / job["id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        lease_stop = Event()
        lease_lost = Event()

        def keep_lease() -> None:
            interval = max(5.0, min(self.settings.worker_lease_seconds / 3, 30.0))
            while not lease_stop.wait(interval):
                try:
                    owned = self.store.renew_job_lease(
                        job["id"], self.worker_id, self.settings.worker_lease_seconds
                    )
                except Exception:
                    lease_lost.set()
                    return
                if not owned:
                    lease_lost.set()
                    return

        lease_thread = Thread(target=keep_lease, name=f"lease-{job['id']}", daemon=True)
        lease_thread.start()

        def progress(event: dict[str, Any]) -> None:
            if lease_lost.is_set():
                raise JobLeaseLost("job lease renewal failed")
            if self.store.is_cancel_requested(job["id"]):
                raise JobCancelled("job cancelled by user")
            stage = str(event.get("node") or event.get("stage") or "running")
            percent = int(event.get("percent") or 25)
            if not self.store.update_job_progress(
                job["id"], stage, percent, self.settings.worker_lease_seconds, self.worker_id
            ):
                raise JobLeaseLost("job lease is no longer owned by this worker")

        try:
            input_overrides: dict[str, str] = {}
            video_asset = self._find_asset(job["user_id"], job["asset_ids"], {"video"})
            data_asset = self._find_asset(job["user_id"], job["asset_ids"], {"csv", "json"})
            if video_asset:
                input_overrides["reference_video_path"] = str(self._materialize_asset(video_asset, output_dir))
            if data_asset:
                input_overrides["commercial_data_path"] = str(self._materialize_asset(data_asset, output_dir))
            state = self.workflow_runner(
                job["query"],
                output_dir,
                progress_callback=progress,
                route_override=job["route"],
                input_overrides=input_overrides,
            )
            if lease_lost.is_set():
                raise JobLeaseLost("job lease renewal failed")
            if self.store.is_cancel_requested(job["id"]):
                raise JobCancelled("job cancelled by user")
            report_path = Path(str(state.get("report_path") or output_dir / "trend_report.md"))
            if not report_path.is_file():
                raise RuntimeError("workflow completed without a report artifact")
            markdown = report_path.read_text(encoding="utf-8")
            if not markdown.strip():
                raise RuntimeError("workflow produced an empty report")
            if self.settings.wechat_content_security_enabled:
                openid = self.store.get_user_openid(job["user_id"])
                if not openid:
                    raise RuntimeError("WeChat identity is unavailable for content safety")
                self.wechat_server.check_text(openid, markdown)
            report = self.store.create_report(
                job["user_id"],
                job["id"],
                title=_report_title(job["query"]),
                markdown=markdown,
                summary=str(state.get("route") or job["route"]),
            )
            if not self.store.complete_job(job["id"], report["id"], self.worker_id):
                self.store.delete_report(job["user_id"], report["id"])
                if self.store.is_cancel_requested(job["id"]):
                    raise JobCancelled("job was cancelled before completion")
                raise JobLeaseLost("job lease is no longer owned by this worker")
        except JobCancelled:
            self.store.mark_job_cancelled(job["id"])
        except JobLeaseLost:
            pass
        except ContentSafetyRejected as exc:
            self.store.fail_job(job["id"], "CONTENT_REJECTED", str(exc), self.worker_id)
        except Exception as exc:
            self.store.fail_job(job["id"], "WORKFLOW_FAILED", _workflow_error_message(exc), self.worker_id)
        finally:
            lease_stop.set()
            lease_thread.join(timeout=1)
        return self.store.get_job(job["user_id"], job["id"])

    def delete_user(self, user_id: str) -> None:
        object_keys = self.store.delete_user(user_id)
        self._delete_objects(object_keys)
        self._delete_user_object_root(user_id)
        self._delete_workflow_data(user_id)

    def delete_user_data(self, user_id: str) -> None:
        object_keys = self.store.delete_user_data(user_id)
        self._delete_objects(object_keys)
        self._delete_user_object_root(user_id)
        self._delete_workflow_data(user_id)

    def _delete_objects(self, object_keys: list[str]) -> None:
        for object_key in object_keys:
            self.objects.delete(object_key)

    def _delete_workflow_data(self, user_id: str) -> None:
        root = self.settings.workflow_root.resolve()
        target = (root / user_id).resolve()
        if root not in target.parents:
            raise ValueError("unsafe workflow data path")
        if target.exists():
            shutil.rmtree(target)

    def _delete_user_object_root(self, user_id: str) -> None:
        if not isinstance(self.objects, LocalObjectStore):
            return
        root = self.objects.root.resolve()
        target = (root / "users" / user_id).resolve()
        if root not in target.parents:
            raise ValueError("unsafe user object path")
        if target.exists():
            shutil.rmtree(target)

    def object_path(self, object_key: str) -> Path:
        if not isinstance(self.objects, LocalObjectStore):
            raise RuntimeError("cloud objects do not have a persistent local path")
        return self.objects.path(object_key)

    def _materialize_asset(self, asset: dict[str, Any], output_dir: Path) -> Path:
        target = output_dir / "inputs" / asset["id"] / asset["filename"]
        return self.objects.materialize(asset["object_key"], target)

    def _find_asset(self, user_id: str, asset_ids: list[str], file_types: set[str]) -> dict[str, Any] | None:
        for asset_id in asset_ids:
            asset = self.store.get_asset(user_id, asset_id)
            if asset and asset["file_type"] in file_types and asset["status"] == "uploaded":
                return asset
        return None


def _report_title(query: str) -> str:
    normalized = " ".join(query.split())
    return normalized[:48] or "分析报告"


def _workflow_error_message(exc: Exception) -> str:
    if os.getenv("MOBILE_DEBUG_ERRORS", "").lower() in {"1", "true", "yes"}:
        return str(exc)
    return "workflow execution failed"


class JobCancelled(RuntimeError):
    pass


class JobLeaseLost(RuntimeError):
    pass


class UploadTooLarge(ValueError):
    pass


class LegalConsentRequired(PermissionError):
    pass


def _validate_content(file_type: str, filename: str, content: bytes) -> None:
    if not content:
        raise ValueError("uploaded file is empty")
    if file_type == "json":
        import json
        try:
            json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON content") from exc
    elif file_type == "csv":
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding") from exc
    elif Path(filename).suffix.lower() in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("file content does not match JPEG")
    elif Path(filename).suffix.lower() == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("file content does not match PNG")
    elif file_type == "video" and (len(content) < 12 or content[4:8] != b"ftyp"):
        raise ValueError("file content does not match MP4/MOV")


def _validate_file_content(file_type: str, filename: str, path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError("uploaded file is empty")
    if file_type == "json":
        import json
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                json.load(handle)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON content") from exc
        return
    if file_type == "csv":
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                handle.read(8192)
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding") from exc
        return
    with path.open("rb") as handle:
        header = handle.read(16)
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise ValueError("file content does not match JPEG")
    if suffix == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("file content does not match PNG")
    if file_type == "video" and (len(header) < 12 or header[4:8] != b"ftyp"):
        raise ValueError("file content does not match MP4/MOV")
