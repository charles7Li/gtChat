from __future__ import annotations

import json
import hmac
import logging
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.agents.plan_agent import PlanAgent
from app.collectors.douyin_minimal import DEFAULT_COOKIE_PATH as DOUYIN_COOKIE_PATH
from app.data_sources import import_chanmama_file, run_data_source_import
from app.monitor import run_background_once, run_monitor_tick
from app.mobile_api import create_mobile_router
from app.mobile_api.request_context import reset_request_id, set_request_id
from app.notifications import build_monitor_digest
from app.video import analyze_local_video
from app.workflow import run_workflow

RUNS_DIR = Path("outputs/web_runs")
UPLOADS_DIR = Path("uploads")
MONITOR_DIR = Path("monitor_jobs")
REPORT_ROOT = Path("outputs")
XHS_COOKIE_PATH = Path(".profiles/xiaohongshu/default.cookies.json")
ALLOWED_UPLOAD_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".csv", ".json"}
JOB_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_REPORT_CACHE_LOCK = Lock()
_REPORT_CACHE: tuple[str, float, list[Path]] = ("", 0.0, [])
_API_LOGGER = logging.getLogger("mochi.mobile_api")
_AUTH_PROCESSES: dict[str, subprocess.Popen] = {}
_AUTH_SESSIONS: dict[str, dict[str, Any]] = {}
AUTH_SESSION_DIR = Path(".profiles/auth_sessions")
_AUTH_SESSION_TTL_SECONDS = 10 * 60
_RUN_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mochi-web-run")
_RUN_STATE_FILENAME = "run_state.json"


class ChatRunRequest(BaseModel):
    query: str
    output_dir: str | None = None
    allow_live: bool = False


class UploadAsset(BaseModel):
    asset_id: str
    filename: str
    content_type: str
    file_type: str
    path: str
    created_at: str


class VideoAnalyzeRequest(BaseModel):
    path: str
    output_dir: str | None = None
    max_keyframes: int = 20
    transcribe: bool = False


class ImportRequest(BaseModel):
    source: str = "chanmama"
    path: str | None = None


class MonitorTickRequest(BaseModel):
    keyword: str
    snapshot_path: str
    platform: str = "xiaohongshu"
    account: str = "default"
    state_dir: str = "monitor_state"
    queue_db: str = "events.db"
    require_auth: bool = False


class HotspotRuleModel(BaseModel):
    min_heat_score: float | None = None
    min_growth_rate: float | None = None
    min_rank: int | None = None
    min_engagement: int | None = None
    required_sources: list[str] = Field(default_factory=list)


class MonitorJobRequest(BaseModel):
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)
    name: str
    enabled: bool = True
    platforms: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    interval_seconds: int = 3600
    allow_live: bool = False
    rule: HotspotRuleModel = Field(default_factory=HotspotRuleModel)
    signals_path: str | None = None
    output_dir: str = "outputs/hotspot"


class LoginStateRequest(BaseModel):
    cookies: list[dict[str, Any]] = Field(min_length=1)


def create_app() -> FastAPI:
    if os.getenv("MOCHI_ENV", "development").lower() == "production" and not os.getenv("MOCHI_WEB_ADMIN_TOKEN"):
        raise RuntimeError("MOCHI_WEB_ADMIN_TOKEN is required in production")
    app = FastAPI(title="Mochi Scout Web API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_mobile_router())

    @app.exception_handler(HTTPException)
    async def structured_http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/v1/mobile/") and isinstance(exc.detail, dict):
            detail = dict(exc.detail)
            detail.setdefault("request_id", getattr(request.state, "request_id", ""))
            exc = HTTPException(status_code=exc.status_code, detail=detail, headers=exc.headers)
        return await http_exception_handler(request, exc)

    @app.middleware("http")
    async def mobile_request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "").strip()[:128] or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        started = monotonic()
        context_token = set_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            if request.url.path.startswith("/api/v1/mobile/"):
                _API_LOGGER.info(
                    "mobile_request request_id=%s method=%s path=%s status=%s duration_ms=%d",
                    request_id,
                    request.method,
                    request.url.path,
                    response.status_code,
                    int((monotonic() - started) * 1000),
                )
            return response
        finally:
            reset_request_id(context_token)

    @app.middleware("http")
    async def protect_web_api(request: Request, call_next):
        token = os.getenv("MOCHI_WEB_ADMIN_TOKEN")
        if token and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/v1/mobile/"):
            supplied = request.headers.get("x-mochi-admin-token", "")
            if not hmac.compare_digest(supplied, token):
                return JSONResponse(status_code=401, content={"detail": "admin authentication required"})
        return await call_next(request)

    @app.post("/api/chat/runs")
    def create_chat_run(request: ChatRunRequest) -> dict[str, Any]:
        planned_route = PlanAgent().run(request.query).get("route")
        if planned_route == "full_pipeline_path" and not request.allow_live:
            raise HTTPException(status_code=400, detail="full_pipeline_path requires allow_live=true")
        run_id = _run_dir_name()
        output_dir = _managed_output_path(request.output_dir, RUNS_DIR, run_id)
        _write_run_state(output_dir, {
            "run_id": run_id,
            "query": request.query,
            "route": planned_route or "",
            "status": "queued",
            "stages": [],
            "created_at": _now(),
        })
        _RUN_EXECUTOR.submit(_execute_chat_run, request.query, output_dir, run_id)
        return _run_response({"run_id": run_id, "user_query": request.query, "route": planned_route or ""}, "queued", output_dir=output_dir)

    @app.get("/api/chat/runs/{run_id}")
    def get_chat_run(run_id: str) -> dict[str, Any]:
        output_dir = RUNS_DIR / run_id
        resolved_output = output_dir.resolve()
        resolved_root = RUNS_DIR.resolve()
        if not output_dir.is_dir() or (resolved_output != resolved_root and resolved_root not in resolved_output.parents):
            raise HTTPException(status_code=404, detail="run not found")
        state_path = output_dir / _RUN_STATE_FILENAME
        if state_path.exists():
            return json.loads(state_path.read_text(encoding="utf-8"))
        report = _find_run_dir(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _report_summary(report)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        report = _find_run_dir(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _report_summary(report)

    @app.post("/api/uploads")
    async def upload_asset(request: Request, filename: str = Query("upload.bin")) -> UploadAsset:
        asset_id = uuid4().hex
        filename = Path(filename).name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(status_code=400, detail="unsupported file type")
        target = UPLOADS_DIR / asset_id / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.part")
        size = 0
        max_bytes = _max_upload_bytes()
        try:
            with temporary.open("wb") as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(status_code=413, detail="file exceeds upload limit")
                    handle.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="uploaded file is empty")
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        content_type = request.headers.get("content-type") or "application/octet-stream"
        return UploadAsset(
            asset_id=asset_id,
            filename=filename,
            content_type=content_type,
            file_type=_file_type(filename, content_type),
            path=str(target),
            created_at=_now(),
        )

    @app.post("/api/video/analyze")
    def analyze_video(request: VideoAnalyzeRequest) -> dict[str, Any]:
        source_path = _managed_input_file(request.path, [UPLOADS_DIR, REPORT_ROOT])
        output_dir = _managed_output_path(
            request.output_dir,
            REPORT_ROOT / "video_analysis",
            _stamp(),
        )
        try:
            return analyze_local_video(
                str(source_path),
                output_dir=str(output_dir),
                max_keyframes=request.max_keyframes,
                transcribe=request.transcribe,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/imports")
    def create_import(request: ImportRequest) -> dict[str, Any]:
        managed_path = _managed_input_file(request.path, [UPLOADS_DIR]) if request.path else None
        if request.source == "chanmama" and managed_path and managed_path.is_file():
            record = import_chanmama_file(managed_path)
            return {"source": request.source, "record_count": record.get("record_count", 0), "records": [record], "provenance": [record.get("provenance", {})]}
        return run_data_source_import(request.source, path=managed_path)

    @app.post("/api/monitor/ticks")
    def create_monitor_tick(request: MonitorTickRequest) -> dict[str, Any]:
        data = request.model_dump()
        data["snapshot_path"] = str(_managed_input_file(request.snapshot_path, [UPLOADS_DIR, MONITOR_DIR]))
        data["state_dir"] = str(_managed_directory(request.state_dir, MONITOR_DIR / "state"))
        data["queue_db"] = str(_managed_file_path(request.queue_db, MONITOR_DIR / "events.db"))
        return run_monitor_tick(**data)

    @app.post("/api/monitor/jobs")
    def create_monitor_job(request: MonitorJobRequest) -> dict[str, Any]:
        data = request.model_dump()
        data["job_id"] = data["job_id"] or uuid4().hex[:12]
        data["output_dir"] = str(_managed_output_path(data.get("output_dir"), REPORT_ROOT / "hotspot", data["job_id"]))
        if data.get("signals_path"):
            data["signals_path"] = str(_managed_input_file(data["signals_path"], [UPLOADS_DIR, MONITOR_DIR]))
        path = _job_path(data["job_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    @app.get("/api/monitor/jobs")
    def list_monitor_jobs() -> list[dict[str, Any]]:
        if not MONITOR_DIR.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(MONITOR_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
            if not path.name.endswith(".signals.json")
        ]

    @app.post("/api/monitor/jobs/{job_id}/run-once")
    def run_monitor_job_once(job_id: str) -> dict[str, Any]:
        _validate_job_id(job_id)
        path = _job_path(job_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="job not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        signals_path = data.get("signals_path") or _empty_signals_file(job_id)
        result = run_background_once(
            config_path=path,
            signals_path=signals_path,
            output_dir=data.get("output_dir") or "outputs/hotspot",
        )
        _invalidate_report_cache()
        return result

    @app.get("/api/monitor/digest")
    def monitor_digest(state_dir: str = "state", limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
        return build_monitor_digest(_managed_directory(state_dir, MONITOR_DIR / "state"), limit=limit)

    @app.get("/api/auth/status")
    def auth_status() -> dict[str, Any]:
        return {
            "xiaohongshu": _login_state_summary("xiaohongshu", XHS_COOKIE_PATH),
            "douyin": _login_state_summary("douyin", DOUYIN_COOKIE_PATH),
        }

    @app.post("/api/auth/{platform}/login")
    def start_auth_login(platform: Literal["xiaohongshu", "douyin"]) -> dict[str, Any]:
        """Open a local interactive browser login controlled by the Web page."""
        process = _AUTH_PROCESSES.get(platform)
        if process is not None and process.poll() is None:
            existing = next((item for item in _AUTH_SESSIONS.values() if item.get("platform") == platform and item.get("status") in {"running", "completing"}), None)
            return {"platform": platform, "session_id": existing.get("session_id", "") if existing else "", "status": "running"}

        session_id = uuid4().hex
        completion_file = AUTH_SESSION_DIR / f"{session_id}.complete"
        if platform == "xiaohongshu":
            command = [
                sys.executable,
                "-m",
                "app.collectors.xiaohongshu_minimal",
                "--login",
                "--profile-dir",
                ".profiles/xiaohongshu/browser",
                "--cookie-path",
                str(XHS_COOKIE_PATH),
                "--completion-file",
                str(completion_file),
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "app.collectors.douyin_minimal",
                "--login",
                "--cookie-path",
                str(DOUYIN_COOKIE_PATH),
                "--completion-file",
                str(completion_file),
            ]

        kwargs: dict[str, Any] = {"cwd": str(Path.cwd())}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            kwargs["start_new_session"] = True
        try:
            _AUTH_PROCESSES[platform] = subprocess.Popen(command, **kwargs)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"unable to open login browser: {exc}") from exc
        _AUTH_SESSIONS[session_id] = {"session_id": session_id, "platform": platform, "completion_file": str(completion_file), "status": "running", "started_at": _now(), "started_monotonic": monotonic()}
        return {"platform": platform, "session_id": session_id, "status": "started"}

    @app.get("/api/auth/sessions/{session_id}")
    def get_auth_session(session_id: str) -> dict[str, Any]:
        state = _auth_session_state(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="login session not found")
        return state

    @app.post("/api/auth/sessions/{session_id}/complete")
    def complete_auth_login(session_id: str) -> dict[str, Any]:
        session = _AUTH_SESSIONS.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="login session not found")
        if monotonic() - float(session.get("started_monotonic", monotonic())) > _AUTH_SESSION_TTL_SECONDS:
            process = _AUTH_PROCESSES.get(session["platform"])
            if process is not None and process.poll() is None:
                process.terminate()
            session["status"] = "expired"
            raise HTTPException(status_code=410, detail="login session expired")
        completion_file = Path(session["completion_file"])
        completion_file.parent.mkdir(parents=True, exist_ok=True)
        completion_file.touch()
        session["status"] = "completing"
        return {"session_id": session_id, "platform": session["platform"], "status": "completing"}

    @app.put("/api/auth/{platform}")
    def save_auth_state(platform: Literal["xiaohongshu", "douyin"], request: LoginStateRequest) -> dict[str, Any]:
        path = XHS_COOKIE_PATH if platform == "xiaohongshu" else DOUYIN_COOKIE_PATH
        cookies = [_validated_cookie(cookie) for cookie in request.cookies]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return _login_state_summary(platform, path)

    @app.get("/api/reports")
    def list_reports(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        return [_report_summary(path) for path in _report_dirs()[offset : offset + limit]]

    @app.get("/api/reports/{run_id}")
    def get_report(run_id: str) -> dict[str, Any]:
        path = _find_run_dir(run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="report not found")
        summary = _report_summary(path)
        report_path = Path(summary["report_path"]) if summary.get("report_path") else path / "trend_report.md"
        summary["markdown"] = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        return summary

    @app.get("/api/reports/{run_id}/download")
    def download_report(run_id: str):
        path = _find_run_dir(run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="report not found")
        report_path = path / "trend_report.md"
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="trend_report.md not found")
        return FileResponse(report_path, media_type="text/markdown", filename=report_path.name)

    @app.get("/api/reports/{run_id}/artifacts/{artifact}")
    def get_report_artifact(run_id: str, artifact: str) -> dict[str, Any]:
        path = _find_run_dir(run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="report not found")
        filenames = {
            "trace": "agent_trace.json",
            "manifest": "manifest.json",
            "evidence": "evidence_pack.json",
        }
        filename = filenames.get(artifact)
        if not filename:
            raise HTTPException(status_code=404, detail="artifact not found")
        target = path / filename
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"{filename} not found")
        return json.loads(target.read_text(encoding="utf-8"))

    @app.get("/api/files")
    def read_file(path: str) -> PlainTextResponse:
        target = Path(path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        if not _is_readable_artifact(target):
            raise HTTPException(status_code=400, detail="file is outside readable artifacts")
        return PlainTextResponse(target.read_text(encoding="utf-8"))

    return app


app = create_app()


def _run_response(state: dict[str, Any], status: str, *, output_dir: Path | None = None) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id", ""),
        "query": state.get("user_query", ""),
        "route": state.get("route", ""),
        "status": status,
        "report_path": state.get("report_path"),
        "trace_path": state.get("trace_path"),
        "manifest_path": state.get("manifest_path"),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
        "created_at": _now(),
        "stages": state.get("stages", []),
    }


def _execute_chat_run(query: str, output_dir: Path, run_id: str) -> None:
    def progress(event: dict[str, Any]) -> None:
        current = _read_run_state(output_dir)
        stages = list(current.get("stages", []))
        name = event.get("name", "")
        if name and event.get("phase") == "start":
            stages = [stage for stage in stages if stage.get("name") != name]
            stages.append({"name": name, "status": "running", "started_at": event.get("started_at")})
        elif name and event.get("phase") in {"finish", "failed"}:
            stages = [stage for stage in stages if stage.get("name") != name]
            stages.append({"name": name, "status": "failed" if event.get("phase") == "failed" else event.get("status", "success"), "started_at": event.get("started_at"), "ended_at": event.get("ended_at"), "duration_ms": event.get("duration_ms")})
        _write_run_state(output_dir, {**current, "status": "running", "stages": stages, "updated_at": _now()})

    _write_run_state(output_dir, {**_read_run_state(output_dir), "status": "running", "updated_at": _now()})
    try:
        state = run_workflow(query, output_dir, progress_callback=progress)
        _write_run_state(output_dir, {**_run_response(state, "success"), "stages": _read_run_state(output_dir).get("stages", []), "updated_at": _now()})
        _invalidate_report_cache()
    except Exception as exc:
        current = _read_run_state(output_dir)
        _write_run_state(output_dir, {**current, "status": "failed", "error": _public_error("workflow failed", exc), "updated_at": _now()})


def _read_run_state(output_dir: Path) -> dict[str, Any]:
    path = output_dir / _RUN_STATE_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_run_state(output_dir: Path, state: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / f".{_RUN_STATE_FILENAME}.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_dir / _RUN_STATE_FILENAME)


def _report_summary(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    trace_path = path / "agent_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}
    return {
        "run_id": str(manifest.get("run_id") or trace.get("run_id") or path.name),
        "route": manifest.get("route") or trace.get("route") or "",
        "status": "success" if (path / "trend_report.md").exists() else "unknown",
        "created_at": manifest.get("created_at") or trace.get("created_at") or _mtime(path),
        "report_path": str(path / "trend_report.md") if (path / "trend_report.md").exists() else manifest.get("report"),
        "trace_path": str(trace_path) if trace_path.exists() else manifest.get("agent_trace"),
        "manifest_path": str(manifest_path) if manifest_path.exists() else "",
        "evidence_path": str(path / "evidence_pack.json") if (path / "evidence_pack.json").exists() else manifest.get("evidence_pack"),
        "warnings": trace.get("warnings", []),
    }


def _report_dirs() -> list[Path]:
    global _REPORT_CACHE
    if not REPORT_ROOT.exists():
        return []
    root_key = str(REPORT_ROOT.resolve())
    now = monotonic()
    with _REPORT_CACHE_LOCK:
        cached_root, cached_at, cached_paths = _REPORT_CACHE
        if cached_root == root_key and now - cached_at < 5:
            return list(cached_paths)
        paths = sorted(
            {path.parent for path in REPORT_ROOT.rglob("manifest.json")}
            | {path.parent for path in REPORT_ROOT.rglob("trend_report.md")},
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        _REPORT_CACHE = (root_key, now, paths)
        return list(paths)


def _invalidate_report_cache() -> None:
    global _REPORT_CACHE
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE = ("", 0.0, [])


def _find_run_dir(run_id: str) -> Path | None:
    for path in _report_dirs():
        summary = _report_summary(path)
        if summary["run_id"] == run_id or path.name == run_id:
            return path
    return None


def _job_path(job_id: str) -> Path:
    _validate_job_id(job_id)
    return MONITOR_DIR / f"{job_id}.json"


def _empty_signals_file(job_id: str) -> str:
    _validate_job_id(job_id)
    path = MONITOR_DIR / f"{job_id}.signals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({"signals": []}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _file_type(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}:
        return "video"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"} or content_type.startswith("image/"):
        return "image"
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return "other"


def _is_readable_artifact(path: Path) -> bool:
    resolved = path.resolve()
    roots = [REPORT_ROOT.resolve(), UPLOADS_DIR.resolve(), MONITOR_DIR.resolve()]
    return any(resolved == root or root in resolved.parents for root in roots)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _run_dir_name() -> str:
    return f"{_stamp()}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _validated_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    name = str(cookie.get("name") or "").strip()
    if not name or "value" not in cookie:
        raise HTTPException(status_code=422, detail="each cookie requires name and value")
    return {**cookie, "name": name, "value": str(cookie["value"])}


def _login_state_summary(platform: str, path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"platform": platform, "status": "auth_required", "cookie_count": 0, "updated_at": None}
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"platform": platform, "status": "invalid", "cookie_count": 0, "updated_at": _mtime(path)}
    count = len(cookies) if isinstance(cookies, list) else 0
    return {
        "platform": platform,
        "status": "saved" if count else "auth_required",
        "cookie_count": count,
        "updated_at": _mtime(path),
    }


def _auth_session_state(session_id: str) -> dict[str, Any] | None:
    session = _AUTH_SESSIONS.get(session_id)
    if session is None:
        return None
    platform = session["platform"]
    process = _AUTH_PROCESSES.get(platform)
    if session.get("status") in {"running", "completing"}:
        if monotonic() - float(session.get("started_monotonic", monotonic())) > _AUTH_SESSION_TTL_SECONDS:
            if process is not None and process.poll() is None:
                process.terminate()
            session["status"] = "expired"
        elif process is not None and process.poll() is not None:
            cookie_path = XHS_COOKIE_PATH if platform == "xiaohongshu" else DOUYIN_COOKIE_PATH
            session["status"] = "succeeded" if _login_state_summary(platform, cookie_path)["status"] == "saved" else "failed"
    return {key: value for key, value in session.items() if key != "completion_file" and key != "started_monotonic"}


def _managed_input_file(path: str | Path, roots: list[Path]) -> Path:
    target = Path(path).resolve()
    if not _allow_arbitrary_local_paths():
        resolved_roots = [root.resolve() for root in roots]
        if not any(target == root or root in target.parents for root in resolved_roots):
            raise HTTPException(status_code=400, detail="file is outside managed storage")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return target


def _managed_output_path(requested: str | Path | None, root: Path, default_name: str) -> Path:
    resolved_root = root.resolve()
    if requested is None:
        return resolved_root / default_name
    candidate = Path(requested)
    if not candidate.is_absolute():
        direct = candidate.resolve()
        candidate = direct if direct == resolved_root or resolved_root in direct.parents else resolved_root / candidate
    target = candidate.resolve()
    if not _allow_arbitrary_local_paths() and target != resolved_root and resolved_root not in target.parents:
        raise HTTPException(status_code=400, detail="output directory is outside managed storage")
    return target


def _managed_directory(requested: str | Path, default: Path) -> Path:
    root = default.parent.resolve()
    candidate = Path(requested)
    if not candidate.is_absolute():
        direct = candidate.resolve()
        candidate = direct if direct == root or root in direct.parents else root / candidate
    target = candidate.resolve()
    if not _allow_arbitrary_local_paths() and target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="directory is outside managed storage")
    return target


def _managed_file_path(requested: str | Path, default: Path) -> Path:
    root = default.parent.resolve()
    candidate = Path(requested)
    if not candidate.is_absolute():
        direct = candidate.resolve()
        candidate = direct if direct == root or root in direct.parents else root / candidate
    target = candidate.resolve()
    if not _allow_arbitrary_local_paths() and target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="file path is outside managed storage")
    return target


def _validate_job_id(job_id: str) -> None:
    if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
        raise HTTPException(status_code=400, detail="invalid job id")


def _max_upload_bytes() -> int:
    try:
        value = int(os.getenv("MOCHI_WEB_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    except ValueError as exc:
        raise RuntimeError("MOCHI_WEB_MAX_UPLOAD_BYTES must be an integer") from exc
    if value <= 0:
        raise RuntimeError("MOCHI_WEB_MAX_UPLOAD_BYTES must be positive")
    return value


def _allow_arbitrary_local_paths() -> bool:
    return os.getenv("MOCHI_WEB_ALLOW_ARBITRARY_LOCAL_PATHS", "").lower() in {"1", "true", "yes"}


def _is_production() -> bool:
    return os.getenv("MOCHI_ENV", "development").lower() == "production"


def _public_error(message: str, exc: Exception) -> str:
    if os.getenv("MOCHI_DEBUG", "").lower() in {"1", "true", "yes"}:
        return f"{message}: {exc}"
    return message
