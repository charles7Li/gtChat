from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class SimpleMemory:
    def __init__(self, memory_dir: str | Path = "memory") -> None:
        self.memory_dir = Path(memory_dir)
        self.trend_file = self.memory_dir / "trend_memory.md"
        self.pattern_file = self.memory_dir / "pattern_memory.md"
        self.review_file = self.memory_dir / "review_feedback.jsonl"
        self.runs_file = self.memory_dir / "runs.jsonl"
        self.index_file = self.memory_dir / "index.json"

    def load(self, keyword: str | None = None, limit: int = 5) -> dict:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        runs = self._read_jsonl(self.runs_file)
        recent_runs = list(reversed(runs[-limit:]))
        keyword_runs = [run for run in reversed(runs) if not keyword or run.get("keyword") == keyword][:limit]
        return {
            "trend_memory": self._read_text(self.trend_file),
            "pattern_memory": self._read_text(self.pattern_file),
            "review_feedback": self._read_jsonl(self.review_file),
            "recent_runs": recent_runs,
            "keyword_runs": keyword_runs,
            "summary": self._build_summary(keyword_runs or recent_runs),
            "index": self._read_index(),
        }

    def write(self, state: dict) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        record = self._record_from_state(state, datetime.now(timezone.utc).isoformat())
        keyword = record["keyword"]
        created_at = record["created_at"]

        with self.trend_file.open("a", encoding="utf-8") as file:
            file.write(f"\n## {created_at} {keyword}\n{record['trend_summary']}\n")
        with self.pattern_file.open("a", encoding="utf-8") as file:
            file.write(f"\n## {created_at} {keyword}\n" + "\n".join(f"- {item}" for item in record["pattern_templates"]) + "\n")
        self._append_jsonl(
            self.review_file,
            {
                "created_at": created_at,
                "keyword": keyword,
                "best_plan": record["best_plan"],
                "review_score": record["review_score"],
            },
        )
        self._append_jsonl(self.runs_file, record)
        self._update_index(record)

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _append_jsonl(self, path: Path, row: dict) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _read_index(self) -> dict:
        if not self.index_file.exists():
            return {"version": 2, "keywords": {}}
        return json.loads(self.index_file.read_text(encoding="utf-8"))

    def _write_index(self, index: dict) -> None:
        self.index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record_from_state(self, state: dict, created_at: str) -> dict:
        trend = state.get("trend_analysis") or {}
        pattern = state.get("pattern_analysis") or {}
        review = state.get("review_result") or {}
        plans = state.get("imitation_plans") or []
        best_index = review.get("best_plan_index") or 0
        best_plan = plans[best_index] if plans and best_index < len(plans) else {}
        return {
            "version": 2,
            "created_at": created_at,
            "run_id": state.get("run_id"),
            "route": state.get("route"),
            "keyword": state.get("keyword") or (state.get("plan") or {}).get("keyword", "pet"),
            "trend_summary": trend.get("summary", ""),
            "pattern_templates": pattern.get("replicable_templates") or [],
            "best_plan": best_plan,
            "review_score": review.get("overall_score"),
        }

    def _update_index(self, record: dict) -> None:
        index = self._read_index()
        keyword = record["keyword"]
        keywords = index.setdefault("keywords", {})
        item = keywords.setdefault(keyword, {"run_count": 0, "score_total": 0})
        item["run_count"] += 1
        item["last_run_at"] = record["created_at"]
        item["last_trend_summary"] = record["trend_summary"]
        score = record.get("review_score")
        if isinstance(score, (int, float)):
            item["score_total"] += score
            item["average_review_score"] = round(item["score_total"] / item["run_count"], 2)
        item["last_review_score"] = score
        self._write_index(index)

    def _build_summary(self, runs: list[dict]) -> str:
        lines = []
        for run in runs:
            score = run.get("review_score")
            score_text = f" score={score}" if score is not None else ""
            lines.append(f"- {run.get('created_at', '')} {run.get('keyword', '')}: {run.get('trend_summary', '')}{score_text}")
        return "\n".join(lines)
