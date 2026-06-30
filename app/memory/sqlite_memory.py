from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SQLiteMemory:
    def __init__(self, db_path: str | Path = "memory/memory.db") -> None:
        self.db_path = Path(db_path)

    def load(self, keyword: str | None = None, limit: int = 5) -> dict:
        self._init_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            recent_runs = [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))]
            if keyword:
                keyword_runs = [
                    dict(row)
                    for row in conn.execute("SELECT * FROM runs WHERE keyword = ? ORDER BY created_at DESC LIMIT ?", (keyword, limit))
                ]
            else:
                keyword_runs = recent_runs
            index = {
                row["keyword"]: {"run_count": row["run_count"], "last_run_at": row["last_run_at"], "last_trend_summary": row["last_trend_summary"]}
                for row in conn.execute("SELECT * FROM keyword_index")
            }
        return {
            "trend_memory": "\n".join(run.get("trend_summary", "") for run in keyword_runs),
            "pattern_memory": "",
            "review_feedback": [{"keyword": run.get("keyword"), "review_score": run.get("review_score")} for run in keyword_runs],
            "recent_runs": [_decode_run(run) for run in recent_runs],
            "keyword_runs": [_decode_run(run) for run in keyword_runs],
            "summary": self._build_summary(keyword_runs),
            "index": {"version": 3, "keywords": index},
        }

    def write(self, state: dict) -> None:
        self._init_db()
        record = _record_from_state(state, datetime.now(timezone.utc).isoformat())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO runs(created_at, run_id, route, keyword, trend_summary, pattern_templates_json, best_plan_json, review_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["created_at"],
                    record["run_id"],
                    record["route"],
                    record["keyword"],
                    record["trend_summary"],
                    json.dumps(record["pattern_templates"], ensure_ascii=False),
                    json.dumps(record["best_plan"], ensure_ascii=False),
                    record["review_score"],
                ),
            )
            conn.execute(
                """
                INSERT INTO keyword_index(keyword, run_count, last_run_at, last_trend_summary)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(keyword) DO UPDATE SET
                    run_count = run_count + 1,
                    last_run_at = excluded.last_run_at,
                    last_trend_summary = excluded.last_trend_summary
                """,
                (record["keyword"], record["created_at"], record["trend_summary"]),
            )

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    run_id TEXT,
                    route TEXT,
                    keyword TEXT NOT NULL,
                    trend_summary TEXT,
                    pattern_templates_json TEXT,
                    best_plan_json TEXT,
                    review_score REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS keyword_index (
                    keyword TEXT PRIMARY KEY,
                    run_count INTEGER NOT NULL,
                    last_run_at TEXT,
                    last_trend_summary TEXT
                )
                """
            )

    def _build_summary(self, runs: list[dict]) -> str:
        return "\n".join(f"- {run.get('created_at', '')} {run.get('keyword', '')}: {run.get('trend_summary', '')}" for run in runs)


def _record_from_state(state: dict, created_at: str) -> dict:
    trend = state.get("trend_analysis") or {}
    pattern = state.get("pattern_analysis") or {}
    review = state.get("review_result") or {}
    plans = state.get("imitation_plans") or []
    best_index = review.get("best_plan_index") or 0
    best_plan = plans[best_index] if plans and best_index < len(plans) else {}
    return {
        "created_at": created_at,
        "run_id": state.get("run_id"),
        "route": state.get("route"),
        "keyword": state.get("keyword") or (state.get("plan") or {}).get("keyword", "pet"),
        "trend_summary": trend.get("summary", ""),
        "pattern_templates": pattern.get("replicable_templates") or [],
        "best_plan": best_plan,
        "review_score": review.get("overall_score"),
    }


def _decode_run(row: dict) -> dict:
    run = dict(row)
    run["pattern_templates"] = json.loads(run.pop("pattern_templates_json") or "[]")
    run["best_plan"] = json.loads(run.pop("best_plan_json") or "{}")
    return run
