from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.agents.plan_agent import PlanAgent
from app.collectors.douyin_minimal import DEFAULT_COOKIE_PATH as DOUYIN_COOKIE_PATH
from app.data_sources import import_chanmama_file, run_data_source_import
from app.monitor import run_background_once, run_monitor_tick
from app.notifications import build_monitor_digest
from app.video import analyze_local_video
from app.workflow import run_workflow

RUNS_DIR = Path("outputs/web_runs")
UPLOADS_DIR = Path("uploads")
MONITOR_DIR = Path("monitor_jobs")
REPORT_ROOT = Path("outputs")
XHS_COOKIE_PATH = Path(".profiles/xiaohongshu/default.cookies.json")


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
    job_id: str | None = None
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
    app = FastAPI(title="Mochi Scout Web API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/chat/runs")
    def create_chat_run(request: ChatRunRequest) -> dict[str, Any]:
        planned_route = PlanAgent().run(request.query).get("route")
        if planned_route == "full_pipeline_path" and not request.allow_live:
            raise HTTPException(status_code=400, detail="full_pipeline_path requires allow_live=true")
        output_dir = Path(request.output_dir) if request.output_dir else RUNS_DIR / _run_dir_name()
        try:
            state = run_workflow(request.query, output_dir)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _run_response(state, "success")

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
        target = UPLOADS_DIR / asset_id / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await request.body())
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
        output_dir = request.output_dir or str(Path("outputs/video_analysis") / _stamp())
        try:
            return analyze_local_video(
                request.path,
                output_dir=output_dir,
                max_keyframes=request.max_keyframes,
                transcribe=request.transcribe,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/imports")
    def create_import(request: ImportRequest) -> dict[str, Any]:
        if request.source == "chanmama" and request.path and Path(request.path).is_file():
            record = import_chanmama_file(request.path)
            return {"source": request.source, "record_count": record.get("record_count", 0), "records": [record], "provenance": [record.get("provenance", {})]}
        return run_data_source_import(request.source, path=request.path)

    @app.post("/api/monitor/ticks")
    def create_monitor_tick(request: MonitorTickRequest) -> dict[str, Any]:
        return run_monitor_tick(**request.model_dump())

    @app.post("/api/monitor/jobs")
    def create_monitor_job(request: MonitorJobRequest) -> dict[str, Any]:
        data = request.model_dump()
        data["job_id"] = data["job_id"] or uuid4().hex[:12]
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
        path = _job_path(job_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="job not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        signals_path = data.get("signals_path") or _empty_signals_file(job_id)
        return run_background_once(
            config_path=path,
            signals_path=signals_path,
            output_dir=data.get("output_dir") or "outputs/hotspot",
        )

    @app.get("/api/monitor/digest")
    def monitor_digest(state_dir: str = "monitor_state", limit: int = 20) -> dict[str, Any]:
        return build_monitor_digest(state_dir, limit=limit)

    @app.get("/api/auth/status")
    def auth_status() -> dict[str, Any]:
        return {
            "xiaohongshu": _login_state_summary("xiaohongshu", XHS_COOKIE_PATH),
            "douyin": _login_state_summary("douyin", DOUYIN_COOKIE_PATH),
        }

    @app.put("/api/auth/{platform}")
    def save_auth_state(platform: Literal["xiaohongshu", "douyin"], request: LoginStateRequest) -> dict[str, Any]:
        path = XHS_COOKIE_PATH if platform == "xiaohongshu" else DOUYIN_COOKIE_PATH
        cookies = [_validated_cookie(cookie) for cookie in request.cookies]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return _login_state_summary(platform, path)

    @app.get("/api/reports")
    def list_reports() -> list[dict[str, Any]]:
        return [_report_summary(path) for path in _report_dirs()]

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


def _run_response(state: dict[str, Any], status: str) -> dict[str, Any]:
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
    }


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
    if not REPORT_ROOT.exists():
        return []
    return sorted(
        {path.parent for path in REPORT_ROOT.rglob("manifest.json")} | {path.parent for path in REPORT_ROOT.rglob("trend_report.md")},
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _find_run_dir(run_id: str) -> Path | None:
    for path in _report_dirs():
        summary = _report_summary(path)
        if summary["run_id"] == run_id or path.name == run_id:
            return path
    return None


def _job_path(job_id: str) -> Path:
    return MONITOR_DIR / f"{job_id}.json"


def _empty_signals_file(job_id: str) -> str:
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
