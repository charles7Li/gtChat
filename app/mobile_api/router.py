from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .auth import WeChatAuthError
from .service import MobileRuntime, UploadTooLarge
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


bearer = HTTPBearer(auto_error=False)


def create_mobile_router(runtime: MobileRuntime | None = None) -> APIRouter:
    runtime = runtime or MobileRuntime()
    router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "wechat_auth_mode": runtime.settings.wechat_auth_mode}

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
    def login(request: WeChatLoginRequest) -> dict[str, Any]:
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
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", str(exc), False) from exc

    @router.post("/uploads/{asset_id}/complete")
    def complete_upload(asset_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return runtime.complete_upload(user["id"], asset_id)
        except FileNotFoundError as exc:
            raise _error(status.HTTP_404_NOT_FOUND, "ASSET_NOT_FOUND", str(exc), False) from exc
        except ValueError as exc:
            raise _error(status.HTTP_400_BAD_REQUEST, "INVALID_UPLOAD", str(exc), False) from exc

    @router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        request: JobCreateRequest,
        response: Response,
        user: dict[str, Any] = Depends(current_user),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        if not idempotency_key or len(idempotency_key) > 128:
            raise _error(status.HTTP_400_BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED", "缺少有效的幂等键", False)
        try:
            job, created = runtime.create_job(
                user["id"], request.query, request.route, request.asset_ids, request.allow_live, idempotency_key
            )
        except ContentSafetyRejected as exc:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "CONTENT_REJECTED", str(exc), False) from exc
        except WeChatApiError as exc:
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "CONTENT_SAFETY_UNAVAILABLE", str(exc), True) from exc
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
        return report

    @router.post("/subscriptions/task-completed")
    def save_subscription(
        request: ConsentRequest, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        runtime.store.save_consent(user["id"], "task_completed", request.version, request.granted)
        return {"granted": request.granted, "version": request.version}

    @router.delete("/me/data", status_code=status.HTTP_204_NO_CONTENT)
    def delete_my_data(user: dict[str, Any] = Depends(current_user)) -> Response:
        runtime.delete_user_data(user["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
    def delete_me(user: dict[str, Any] = Depends(current_user)) -> Response:
        runtime.delete_user(user["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _error(status_code: int, code: str, message: str, retryable: bool) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "retryable": retryable})
