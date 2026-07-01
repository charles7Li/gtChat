from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.agents import JudgeSubAgent, ResearchPlannerSubAgent, SearchStrategySubAgent, VerifierSubAgent
from app.hotspots import HotspotRule, MonitorJobConfig, run_hotspot_monitor_once
from app.queue import SQLiteQueue


@dataclass(frozen=True)
class AuthStatus:
    status: str
    reason: str = ""
    next_step: str = ""


class AuthGate:
    def __init__(self, profile_root: str | Path = ".profiles") -> None:
        self.profile_root = Path(profile_root)

    def check(self, platform: str, account: str = "default") -> AuthStatus:
        if platform == "xiaohongshu":
            path = self.profile_root / "xhs" / account
            if path.exists():
                return AuthStatus("ok")
            return AuthStatus(
                "auth_required",
                "profile_missing",
                f"python -m app.collectors.xiaohongshu_minimal --login --profile-dir {path}",
            )
        if platform == "douyin":
            path = self.profile_root / "douyin" / f"{account}.cookies.json"
            if path.exists():
                return AuthStatus("ok")
            return AuthStatus("auth_required", "cookies_missing", f"refresh douyin cookies at {path}")
        return AuthStatus("ok")


class SignalDetector:
    def __init__(self, *, min_new_items: int = 3, min_engagement_growth: float = 0.5) -> None:
        self.min_new_items = min_new_items
        self.min_engagement_growth = min_engagement_growth

    def detect(self, previous_items: list[dict], current_items: list[dict], *, keyword: str, platform: str) -> dict:
        previous_ids = {str(item.get("id")) for item in previous_items if item.get("id") is not None}
        new_items = [item for item in current_items if str(item.get("id")) not in previous_ids]
        previous_engagement = _total_engagement(previous_items)
        current_engagement = _total_engagement(current_items)
        growth = 0.0 if previous_engagement <= 0 else (current_engagement - previous_engagement) / previous_engagement
        signal_score = min(100, len(new_items) * 20 + round(max(growth, 0) * 40))
        accepted = len(new_items) >= self.min_new_items or growth >= self.min_engagement_growth
        return {
            "accepted": accepted,
            "event_type": "trend_signal_detected",
            "platform": platform,
            "keyword": keyword,
            "new_item_count": len(new_items),
            "engagement_growth": round(growth, 4),
            "signal_score": signal_score,
            "dedupe_key": f"{platform}:{keyword}:trend_signal",
        }


def run_monitor_tick(
    *,
    keyword: str,
    snapshot_path: str | Path,
    platform: str = "xiaohongshu",
    account: str = "default",
    state_dir: str | Path = "monitor_state",
    queue_db: str | Path = "events.db",
    require_auth: bool = True,
) -> dict:
    auth = AuthGate().check(platform, account) if require_auth else AuthStatus("ok")
    queue = SQLiteQueue(queue_db)
    if auth.status != "ok":
        job_id = queue.enqueue(
            "auth_required",
            {"platform": platform, "account": account, "reason": auth.reason, "next_step": auth.next_step},
            dedupe_key=f"{platform}:{account}:auth_required",
        )
        _append_monitor_record(
            state_dir,
            "auth_required",
            {"platform": platform, "account": account, "job_id": job_id, "reason": auth.reason},
        )
        return {"status": auth.status, "job_id": job_id, "auth_reason": auth.reason, "next_step": auth.next_step}

    current_items = _load_items(snapshot_path)
    state_path = Path(state_dir) / f"{platform}_{_safe_name(keyword)}_latest.json"
    previous_items = _load_items(state_path) if state_path.exists() else []
    signal = SignalDetector().detect(previous_items, current_items, keyword=keyword, platform=platform)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(current_items, ensure_ascii=False, indent=2), encoding="utf-8")

    job_id = None
    if signal["accepted"]:
        job_id = queue.enqueue("trend_signal_detected", signal, dedupe_key=signal["dedupe_key"])
    _append_monitor_record(
        state_dir,
        "signal" if signal["accepted"] else "no_signal",
        {"platform": platform, "keyword": keyword, "job_id": job_id, "signal": signal},
    )
    return {"status": "signal" if signal["accepted"] else "no_signal", "job_id": job_id, "signal": signal}


def process_one_research_job(*, queue_db: str | Path = "events.db", state_dir: str | Path = "monitor_state") -> dict:
    queue = SQLiteQueue(queue_db)
    job = queue.claim_next(["trend_signal_detected"])
    if job is None:
        _append_monitor_record(state_dir, "worker_idle", {"worker": "research"})
        return {"status": "idle"}

    signal = job["payload"]
    try:
        decision = JudgeSubAgent().run(signal, [signal])
        decision["keyword"] = signal.get("keyword", "")
        if decision["decision"] != "accept":
            queue.mark_done(job["id"])
            _append_monitor_record(state_dir, "research_decision", {"job_id": job["id"], "decision": decision})
            return {"status": "done", "job_id": job["id"], "decision": decision, "next_job_id": None}

        plan = ResearchPlannerSubAgent().run(decision, signal)
        strategy = SearchStrategySubAgent().run(plan)
        verification = VerifierSubAgent().run(_signal_analysis(signal), _signal_evidence(signal))
        next_type = "report_requested" if verification["decision"] in {"proceed", "limited_report"} else "research_requested"
        next_payload = {
            "source_job_id": job["id"],
            "platform": signal.get("platform"),
            "keyword": signal.get("keyword"),
            "decision": decision,
            "plan": plan,
            "strategy": strategy,
            "verification": verification,
            "max_iterations": 1,
        }
        next_job_id = queue.enqueue(
            next_type,
            next_payload,
            dedupe_key=f"{signal.get('platform')}:{signal.get('keyword')}:{next_type}",
        )
        queue.mark_done(job["id"])
        _append_monitor_record(
            state_dir,
            "research_decision",
            {
                "job_id": job["id"],
                "decision": decision,
                "verification": verification,
                "next_job_id": next_job_id,
                "next_job_type": next_type,
            },
        )
        return {
            "status": "done",
            "job_id": job["id"],
            "decision": decision,
            "verification": verification,
            "next_job_id": next_job_id,
            "next_job_type": next_type,
        }
    except Exception as exc:
        queue.mark_failed(job["id"], str(exc))
        _append_monitor_record(state_dir, "worker_failed", {"job_id": job["id"], "error": str(exc)})
        return {"status": "failed", "job_id": job["id"], "error": str(exc)}


def run_background_once(
    *,
    config_path: str | Path,
    signals_path: str | Path | None = None,
    queue_db: str | Path = "events.db",
    state_dir: str | Path = "monitor_state",
    output_dir: str | Path | None = None,
) -> dict:
    queue = SQLiteQueue(queue_db)
    config_data = _load_monitor_config_data(config_path)
    config = _monitor_config_from_data(config_data)
    signals = signals_path or config_data.get("signals_path")
    if not signals:
        raise ValueError("signals_path is required in config or --signals")
    target_output_dir = Path(output_dir or config_data.get("output_dir") or "outputs/hotspot")
    result = run_hotspot_monitor_once(config, _load_signals(signals))
    job_ids = []
    for payload in result["analysis_payloads"]:
        job_ids.append(
            queue.enqueue(
                "hotspot_analysis_requested",
                payload,
                dedupe_key=f"{config.job_id}:{payload.get('source')}:{payload.get('keyword')}:{payload.get('hotspot_signal', {}).get('signal_id')}",
            )
        )
    analysis_results = [
        process_one_hotspot_analysis_job(queue_db=queue_db, state_dir=state_dir, output_dir=target_output_dir)
        for _ in job_ids
    ]
    _append_monitor_record(
        state_dir,
        "background_run",
        {"job_id": config.job_id, "status": result["status"], "queued_job_ids": job_ids, "analysis_results": analysis_results},
    )
    return {"status": result["status"], "queued_job_ids": job_ids, "monitor": result, "analysis": analysis_results}


def process_one_hotspot_analysis_job(
    *,
    queue_db: str | Path = "events.db",
    state_dir: str | Path = "monitor_state",
    output_dir: str | Path = "outputs/hotspot",
) -> dict:
    queue = SQLiteQueue(queue_db)
    job = queue.claim_next(["hotspot_analysis_requested"])
    if job is None:
        return {"status": "idle"}

    payload = job["payload"]
    try:
        from app.workflow import run_workflow

        keyword = payload.get("keyword") or payload.get("topic") or "热点"
        state = run_workflow(f"热点自动分析 {keyword}", Path(output_dir) / job["id"])
        queue.mark_done(job["id"])
        result = {"status": "done", "job_id": job["id"], "report_path": state.get("report_path"), "trace_path": state.get("trace_path")}
        _append_monitor_record(state_dir, "hotspot_analysis_done", result)
        return result
    except Exception as exc:
        queue.mark_failed(job["id"], str(exc))
        _append_monitor_record(state_dir, "hotspot_analysis_failed", {"job_id": job["id"], "error": str(exc)})
        return {"status": "failed", "job_id": job["id"], "error": str(exc)}


def run_background_loop(
    *,
    config_path: str | Path,
    signals_path: str | Path | None = None,
    queue_db: str | Path = "events.db",
    state_dir: str | Path = "monitor_state",
    output_dir: str | Path | None = None,
    interval_seconds: float | None = None,
    max_runs: int | None = None,
) -> list[dict]:
    config_data = _load_monitor_config_data(config_path)
    interval = interval_seconds if interval_seconds is not None else float(config_data.get("interval_seconds") or 60)
    results = []
    runs = 0
    while max_runs is None or runs < max_runs:
        results.append(
            run_background_once(
                config_path=config_path,
                signals_path=signals_path,
                queue_db=queue_db,
                state_dir=state_dir,
                output_dir=output_dir,
            )
        )
        runs += 1
        if max_runs is None or runs < max_runs:
            time.sleep(interval)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--keyword", required=True)
    run_parser.add_argument("--snapshot", required=True)
    run_parser.add_argument("--platform", default="xiaohongshu")
    run_parser.add_argument("--account", default="default")
    run_parser.add_argument("--state-dir", default="monitor_state")
    run_parser.add_argument("--queue-db", default="events.db")
    run_parser.add_argument("--skip-auth", action="store_true")
    worker_parser = subparsers.add_parser("worker-once")
    worker_parser.add_argument("--queue-db", default="events.db")
    worker_parser.add_argument("--state-dir", default="monitor_state")
    hotspot_parser = subparsers.add_parser("hotspot-analysis-once")
    hotspot_parser.add_argument("--queue-db", default="events.db")
    hotspot_parser.add_argument("--state-dir", default="monitor_state")
    hotspot_parser.add_argument("--output-dir", default="outputs/hotspot")
    background_parser = subparsers.add_parser("background-once")
    background_parser.add_argument("--config", required=True)
    background_parser.add_argument("--signals")
    background_parser.add_argument("--queue-db", default="events.db")
    background_parser.add_argument("--state-dir", default="monitor_state")
    background_parser.add_argument("--output-dir")
    loop_parser = subparsers.add_parser("background-loop")
    loop_parser.add_argument("--config", required=True)
    loop_parser.add_argument("--signals")
    loop_parser.add_argument("--queue-db", default="events.db")
    loop_parser.add_argument("--state-dir", default="monitor_state")
    loop_parser.add_argument("--output-dir")
    loop_parser.add_argument("--interval-seconds", type=float)
    loop_parser.add_argument("--max-runs", type=int)
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_monitor_tick(
            keyword=args.keyword,
            snapshot_path=args.snapshot,
            platform=args.platform,
            account=args.account,
            state_dir=args.state_dir,
            queue_db=args.queue_db,
            require_auth=not args.skip_auth,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "worker-once":
        result = process_one_research_job(queue_db=args.queue_db, state_dir=args.state_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "hotspot-analysis-once":
        result = process_one_hotspot_analysis_job(queue_db=args.queue_db, state_dir=args.state_dir, output_dir=args.output_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "background-once":
        result = run_background_once(
            config_path=args.config,
            signals_path=args.signals,
            queue_db=args.queue_db,
            state_dir=args.state_dir,
            output_dir=args.output_dir,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "background-loop":
        result = run_background_loop(
            config_path=args.config,
            signals_path=args.signals,
            queue_db=args.queue_db,
            state_dir=args.state_dir,
            output_dir=args.output_dir,
            interval_seconds=args.interval_seconds,
            max_runs=args.max_runs,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    return 1


def _load_items(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "notes", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _load_monitor_config_data(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _monitor_config_from_data(data: dict) -> MonitorJobConfig:
    rule = HotspotRule(**(data.get("rule") or {}))
    return MonitorJobConfig(
        job_id=str(data["job_id"]),
        name=str(data.get("name") or data["job_id"]),
        platforms=tuple(data.get("platforms") or ()),
        keywords=tuple(data.get("keywords") or ()),
        allow_live=bool(data.get("allow_live", False)),
        rule=rule,
    )


def _load_signals(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("signals", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _total_engagement(items: list[dict]) -> int:
    total = 0
    for item in items:
        metrics = item.get("metrics") or {}
        total += int(metrics.get("total_engagement") or item.get("total_engagement") or item.get("liked_count") or 0)
    return total


def _signal_analysis(signal: dict) -> dict:
    keyword = signal.get("keyword")
    return {"top_topics": [keyword] if keyword else []}


def _signal_evidence(signal: dict) -> dict:
    item_count = int(signal.get("item_count") or signal.get("clean_count") or signal.get("new_item_count") or 0)
    quality_score = int(signal.get("quality_score") or signal.get("signal_score") or 0)
    return {"item_count": item_count, "quality_score": quality_score}


def _append_monitor_record(state_dir: str | Path, event_type: str, payload: dict) -> None:
    path = Path(state_dir) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "event_type": event_type, **payload}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _safe_name(text: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in text) or "keyword"


if __name__ == "__main__":
    raise SystemExit(main())
