from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import request

from app.queue import SQLiteQueue


def load_monitor_events(state_dir: str | Path = "monitor_state") -> list[dict]:
    path = Path(state_dir) / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event_type": "invalid_event", "raw": line})
    return events


def build_monitor_digest(state_dir: str | Path = "monitor_state", *, limit: int = 20) -> dict:
    events = load_monitor_events(state_dir)
    recent = events[-max(1, int(limit or 20)) :]
    auth_events = [event for event in recent if event.get("event_type") == "auth_required"]
    signal_events = [event for event in recent if event.get("event_type") == "signal"]
    decision_events = [event for event in recent if event.get("event_type") == "research_decision"]
    failed_events = [event for event in recent if event.get("event_type") == "worker_failed"]
    report_paths = [path for event in recent for path in _event_report_paths(event)]
    next_steps = [_login_prompt(event) for event in auth_events]
    return {
        "status": _status(auth_events, failed_events, signal_events, decision_events),
        "event_count": len(events),
        "recent_count": len(recent),
        "latest_event_type": recent[-1].get("event_type") if recent else "",
        "signals": len(signal_events),
        "decisions": [_decision_summary(event) for event in decision_events],
        "report_paths": report_paths,
        "next_steps": [step for step in next_steps if step],
        "messages": _messages(auth_events, failed_events, signal_events, decision_events, report_paths),
    }


def process_one_notification_job(
    *,
    queue_db: str | Path = "events.db",
    state_dir: str | Path = "monitor_state",
    output_path: str | Path | None = None,
) -> dict:
    queue = SQLiteQueue(queue_db)
    job = queue.claim_next(["notification_requested"])
    if job is None:
        return {"status": "idle"}
    try:
        payload = job.get("payload") or {}
        digest = build_monitor_digest(payload.get("state_dir") or state_dir, limit=int(payload.get("limit") or 20))
        target = Path(output_path or payload.get("output_path") or Path(state_dir) / "notification_digest.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
        push_result = send_notification(digest, webhook_url=payload.get("webhook_url"))
        queue.mark_done(job["id"])
        return {"status": "done", "job_id": job["id"], "output_path": str(target), "push": push_result, "digest": digest}
    except Exception as exc:
        queue.mark_failed(job["id"], str(exc))
        return {"status": "failed", "job_id": job["id"], "error": str(exc)}


def validate_notification_config(*, webhook_url: str | None = None) -> dict:
    url = webhook_url or os.getenv("NOTIFICATION_WEBHOOK_URL", "")
    return {"status": "ready" if url else "not_ready", "webhook_configured": bool(url)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize monitor events for local notification output")
    parser.add_argument("--state-dir", default="monitor_state")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--queue-db", default="events.db")
    parser.add_argument("--worker-once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(validate_notification_config(), ensure_ascii=False, indent=2))
        return 0
    if args.worker_once:
        print(json.dumps(process_one_notification_job(queue_db=args.queue_db, state_dir=args.state_dir), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(build_monitor_digest(args.state_dir, limit=args.limit), ensure_ascii=False, indent=2))
    return 0


def send_notification(digest: dict, *, webhook_url: str | None = None) -> dict:
    url = webhook_url or os.getenv("NOTIFICATION_WEBHOOK_URL", "")
    if not url:
        return {"status": "skipped", "reason": "webhook_not_configured"}
    body = json.dumps({"text": "\n".join(digest.get("messages") or []), "digest": digest}, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=10) as response:  # noqa: S310 - user-configured local notification webhook
        return {"status": "sent", "channel": "webhook", "status_code": getattr(response, "status", 200)}


def _status(auth_events: list[dict], failed_events: list[dict], signal_events: list[dict], decision_events: list[dict]) -> str:
    if auth_events:
        return "auth_required"
    if failed_events:
        return "failed"
    if decision_events:
        return "research_updated"
    if signal_events:
        return "signal_detected"
    return "idle"


def _messages(auth_events: list[dict], failed_events: list[dict], signal_events: list[dict], decision_events: list[dict], report_paths: list[str]) -> list[str]:
    messages = []
    for event in auth_events:
        messages.append(f"{event.get('platform', 'platform')} needs login: {event.get('reason', '')}".strip())
    for event in failed_events:
        messages.append(f"worker failed: {event.get('error', '')}".strip())
    if signal_events:
        messages.append(f"{len(signal_events)} signal event(s) detected")
    if decision_events:
        latest = _decision_summary(decision_events[-1])
        messages.append(f"latest research decision: {latest.get('decision', '')}")
    if report_paths:
        messages.append(f"latest report: {report_paths[-1]}")
    return messages


def _decision_summary(event: dict) -> dict:
    decision = event.get("decision") or {}
    verification = event.get("verification") or {}
    return {
        "job_id": event.get("job_id", ""),
        "decision": decision.get("decision", ""),
        "reason": decision.get("reason", ""),
        "verification": verification.get("decision", ""),
        "next_job_id": event.get("next_job_id", ""),
        "next_job_type": event.get("next_job_type", ""),
    }


def _login_prompt(event: dict) -> str:
    if event.get("next_step"):
        return str(event["next_step"])
    platform = event.get("platform", "")
    account = event.get("account", "default")
    if platform == "xiaohongshu":
        return f"python -m app.collectors.xiaohongshu_minimal --login --profile-dir .profiles/xhs/{account}"
    if platform == "douyin":
        return f"refresh douyin cookies at .profiles/douyin/{account}.cookies.json"
    return ""


def _event_report_paths(event: dict) -> list[str]:
    paths = []
    for key in ("report_path", "report_paths"):
        value = event.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(str(item) for item in value if item)
    payload = event.get("payload") or {}
    if isinstance(payload, dict) and payload.get("report_path"):
        paths.append(str(payload["report_path"]))
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
