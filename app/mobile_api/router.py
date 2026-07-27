from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .auth import WeChatAuthError
from .media_moderation import MediaModerationError, MediaModerationRejected
from .service import LegalConsentRequired, MobileRuntime, UploadTooLarge
from .wechat_services import ContentSafetyRejected, WeChatApiError


class WeChatLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    size: int = Field(ge=0)


class JobCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    route: str
    asset_ids: list[str] = Field(default_factory=list, max_length=10)
    allow_live: bool = False


class ConsentRequest(BaseModel):
    granted: bool
    version: str = Field(default="v1", min_length=1, max_length=32)


class LegalConsentRequest(BaseModel):
    granted: bool
    version: str = Field(min_length=1, max_length=32)


bearer = HTTPBearer(auto_error=False)


def create_mobile_router(runtime: MobileRuntime | None = None) -> APIRouter:
    runtime = runtime or MobileRuntime()
    router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

    @router.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "wechat_auth_mode": runtime.settings.wechat_auth_mode,
            "accepting_new_jobs": runtime.settings.accept_new_jobs,
        }

    @router.get("/ready")
    def ready() -> dict[str, str]:
        try:
            available = runtime.store.ping()
        except Exception as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "数据库暂不可用", True) from exc
        if not available:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "数据库暂不可用", True)
        return {"status": "ready", "database": "ok"}

    @router.get("/internal/metrics", response_class=PlainTextResponse)
    def metrics(x_mochi_admin_token: str = Header(default="", alias="X-Mochi-Admin-Token")) -> PlainTextResponse:
        expected = os.getenv("MOCHI_WEB_ADMIN_TOKEN", "")
        if not expected or not hmac.compare_digest(x_mochi_admin_token, expected):
            raise _error(status.HTTP_401_UNAUTHORIZED, "ADMIN_AUTH_REQUIRED", "需要运维鉴权", False)
        values = runtime.store.operational_metrics()
        lines = [
            "# HELP mochi_mobile_jobs Current mobile jobs by status.",
            "# TYPE mochi_mobile_jobs gauge",
        ]
        for job_status, total in sorted(values["jobs"].items()):
            lines.append(f'mochi_mobile_jobs{{status="{job_status}"}} {total}')
        lines.extend(
            [
                "# TYPE mochi_mobile_outbox_pending gauge",
                f"mochi_mobile_outbox_pending {values['outbox_pending']}",
                "# TYPE mochi_mobile_outbox_oldest_age_seconds gauge",
                f"mochi_mobile_outbox_oldest_age_seconds {values['outbox_oldest_age_seconds']}",
                "# TYPE mochi_mobile_notifications gauge",
            ]
        )
        for notification_status, total in sorted(values["notifications"].items()):
            lines.append(f'mochi_mobile_notifications{{status="{notification_status}"}} {total}')
        lines.append("# TYPE mochi_mobile_worker_last_seen_age_seconds gauge")
        for worker in values["workers"]:
            lines.append(
                'mochi_mobile_worker_last_seen_age_seconds'
                f'{{worker_id="{worker["worker_id"]}",worker_type="{worker["worker_type"]}"}} '
                f'{worker["age_seconds"]}'
            )
        return PlainTextResponse("\n".join(lines) + "\n")

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> dict[str, Any]:
        if not credentials or credentials.scheme.lower() != "bearer":
            raise _error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED", "请先登录", True)
        user = runtime.store.resolve_access_token(credentials.credentials)
        if not user:
            raise _error(status.HTTP_401_UNAUTHORIZED, "SESSION_EXPIRED", "登录已过期", True)
        return user

    @router.post("/session/wechat")
    def login(request: WeChatLoginRequest, http_request: Request) -> dict[str, Any]:
        _enforce_rate_limit(
            runtime,
            "login",
            http_request.client.host if http_request.client else "unknown",
            runtime.settings.login_rate_limit_per_minute,
        )
        try:
            return runtime.login(request.code)
        except WeChatAuthError as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "WECHAT_LOGIN_FAILED", str(exc), True) from exc
        except PermissionError as exc:
            raise _error(status.HTTP_403_FORBIDDEN, "ACCOUNT_DISABLED", str(exc), False) from exc

    @router.post("/session/refresh")
    def refresh(request: RefreshRequest) -> dict[str, Any]:
        session = runtime.refresh(request.refresh_token)
        if not session:
            raise _error(status.HTTP_401_UNAUTHORIZED, "REFRESH_EXPIRED", "登录已过期", True)
        return session

    @router.post("/uploads/init", status_code=status.HTTP_201_CREATED)
    def init_upload(request: UploadInitRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        _enforce_rate_limit(runtime, "upload", user["id"], runtime.settings.upload_rate_limit_per_minute)
        try:
            asset = runtime.prepare_upload(user["id"], request.filename, request.content_type, request.size)
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", str(exc), False) from exc
        target = runtime.upload_target(asset)
        return {
            **asset,
            "upload_url": target.url,
            "upload_method": target.method,
            "upload_headers": target.headers or {},
            "upload_fields": target.fields or {},
            "direct_upload": target.direct,
        }

    @router.put("/uploads/{asset_id}/content")
    async def upload_content(
        asset_id: str, request: Request, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", "invalid content length", False) from exc
        if content_length > runtime.settings.max_upload_bytes:
            raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "UPLOAD_TOO_LARGE", "文件超过上传限制", False)
        try:
            return await runtime.write_upload_stream(user["id"], asset_id, request.stream())
        except FileNotFoundError as exc:
            raise _error(status.HTTP_404_NOT_FOUND, "ASSET_NOT_FOUND", str(exc), False) from exc
        except UploadTooLarge as exc:
            raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "UPLOAD_TOO_LARGE", str(exc), False) from exc
        except (ContentSafetyRejected, MediaModerationRejected) as exc:
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "CONTENT_REJECTED", str(exc), False) from exc
        except (WeChatApiError, MediaModerationError) as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "CONTENT_SAFETY_UNAVAILABLE", str(exc), True) from exc
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", str(exc), False) from exc

    @router.post("/uploads/{asset_id}/complete")
    def complete_upload(asset_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return runtime.complete_upload(user["id"], asset_id)
        except FileNotFoundError as exc:
            raise _error(status.HTTP_404_NOT_FOUND, "ASSET_NOT_FOUND", str(exc), False) from exc
        except (ContentSafetyRejected, MediaModerationRejected) as exc:
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "CONTENT_REJECTED", str(exc), False) from exc
        except (WeChatApiError, MediaModerationError) as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "CONTENT_SAFETY_UNAVAILABLE", str(exc), True) from exc
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", str(exc), False) from exc

    @router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: JobCreateRequest,
        response: Response,
        user: dict[str, Any] = Depends(current_user),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if not runtime.settings.accept_new_jobs:
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "NEW_JOBS_DISABLED",
                "系统维护中，暂不接受新任务",
                True,
            )
        _enforce_rate_limit(runtime, "job", user["id"], runtime.settings.job_rate_limit_per_minute)
        if not idempotency_key or len(idempotency_key) > 128:
            raise _error(status.HTTP_400_BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED", "缺少有效的幂等键", False)
        try:
            job, created = runtime.create_job(
                user["id"], request.query, request.route, request.asset_ids, request.allow_live, idempotency_key
            )
        except ContentSafetyRejected as exc:
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "CONTENT_REJECTED", str(exc), False) from exc
        except WeChatApiError as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "CONTENT_SAFETY_UNAVAILABLE", str(exc), True) from exc
        except LegalConsentRequired as exc:
            raise _error(status.HTTP_403_FORBIDDEN, "LEGAL_CONSENT_REQUIRED", str(exc), False) from exc
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_JOB", str(exc), False) from exc
        if not created:
            response.status_code = status.HTTP_200_OK
        return job

    @router.get("/jobs")
    def list_jobs(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        user: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        return runtime.store.list_jobs(user["id"], limit, offset)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        job = runtime.store.get_job(user["id"], job_id)
        if not job:
            raise _error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "任务不存在", False)
        return job

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        job = runtime.store.cancel_job(user["id"], job_id)
        if not job:
            raise _error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "任务不存在", False)
        return job

    @router.post("/jobs/{job_id}/retry")
    def retry_job(job_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            job = runtime.store.retry_job(user["id"], job_id)
        except ValueError as exc:
            raise _error(status.HTTP_409_CONFLICT, "JOB_NOT_RETRYABLE", str(exc), False) from exc
        if not job:
            raise _error(status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "任务不存在", False)
        return job

    @router.get("/reports")
    def list_reports(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        user: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        return runtime.store.list_reports(user["id"], limit, offset)

    @router.get("/reports/{report_id}")
    def get_report(report_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        report = runtime.store.get_report(user["id"], report_id)
        if not report:
            raise _error(status.HTTP_404_NOT_FOUND, "REPORT_NOT_FOUND", "报告不存在", False)
        runtime.store.record_audit(user["id"], "report_read", {"report_id": report_id})
        return report

    @router.post("/subscriptions/task-completed")
    def save_subscription(
        request: ConsentRequest, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        runtime.store.save_consent(user["id"], "task_completed", request.version, request.granted)
        return {"granted": request.granted, "version": request.version}

    @router.post("/consents/legal")
    def save_legal_consent(
        request: LegalConsentRequest, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        if request.version != runtime.settings.legal_consent_version:
            raise _error(status.HTTP_409_CONFLICT, "LEGAL_VERSION_OUTDATED", "协议版本已更新，请重新阅读", False)
        runtime.store.save_consent(user["id"], "terms_and_privacy", request.version, request.granted)
        return {"granted": request.granted, "version": request.version}

    @router.delete("/me/data", status_code=status.HTTP_204_NO_CONTENT)
    def delete_my_data(user: dict[str, Any] = Depends(current_user)) -> Response:
        runtime.delete_user_data(user["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/me/export")
    def export_my_data(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        exported = runtime.store.export_user_data(user["id"])
        if not exported:
            raise _error(status.HTTP_404_NOT_FOUND, "ACCOUNT_NOT_FOUND", "账号不存在", False)
        return exported

    @router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
    def delete_me(user: dict[str, Any] = Depends(current_user)) -> Response:
        runtime.delete_user(user["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _error(status_code: int, code: str, message: str, retryable: bool) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "retryable": retryable})


def _enforce_rate_limit(runtime: MobileRuntime, scope: str, subject: str, limit: int) -> None:
    if runtime.store.consume_rate_limit(scope, subject, limit, 60):
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "RATE_LIMITED", "message": "请求过于频繁，请稍后重试", "retryable": True},
        headers={"Retry-After": "60"},
    )
