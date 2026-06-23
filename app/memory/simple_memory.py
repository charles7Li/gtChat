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

    def load(self) -> dict:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        return {
            "trend_memory": self._read_text(self.trend_file),
            "pattern_memory": self._read_text(self.pattern_file),
            "review_feedback": self._read_jsonl(self.review_file),
        }

    def write(self, state: dict) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        trend = state.get("trend_analysis") or {}
        pattern = state.get("pattern_analysis") or {}
        review = state.get("review_result") or {}
        plans = state.get("imitation_plans") or []
        best_index = review.get("best_plan_index") or 0
        best_plan = plans[best_index] if plans and best_index < len(plans) else {}
        keyword = state.get("keyword") or (state.get("plan") or {}).get("keyword", "宠物")
        created_at = datetime.now(timezone.utc).isoformat()

        with self.trend_file.open("a", encoding="utf-8") as file:
            file.write(f"\n## {created_at} {keyword}\n{trend.get('summary', '')}\n")
        with self.pattern_file.open("a", encoding="utf-8") as file:
            templates = pattern.get("replicable_templates") or []
            file.write(f"\n## {created_at} {keyword}\n" + "\n".join(f"- {item}" for item in templates) + "\n")
        with self.review_file.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "created_at": created_at,
                        "keyword": keyword,
                        "best_plan": best_plan,
                        "review_score": review.get("overall_score"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

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
