from __future__ import annotations

from app.llm import LLMError, structured_llm_call
from app.schemas.analysis import PatternExtractionResult


class PatternExtractorAgent:
    PATTERN_KEYS = (
        "title_patterns",
        "opening_patterns",
        "body_patterns",
        "visual_patterns",
        "interaction_patterns",
        "replicable_templates",
    )

    def run(self, clean_items: list[dict], trend_analysis: dict) -> dict:
        llm_result = self._try_llm_patterns(clean_items, trend_analysis)
        if llm_result:
            return llm_result
        return self._rule_based_patterns(clean_items, trend_analysis)

    def _try_llm_patterns(self, clean_items: list[dict], trend_analysis: dict) -> dict:
        payload = {
            "clean_items": self._llm_items(clean_items),
            "trend_analysis": trend_analysis,
        }
        try:
            result = structured_llm_call("pattern_extractor", payload, PatternExtractionResult)
        except LLMError:
            return {}
        return result if self._valid_patterns(result) else {}

    def _rule_based_patterns(self, clean_items: list[dict], trend_analysis: dict) -> dict:
        titles = [item.get("title", "") for item in clean_items if item.get("title")]
        bodies = [item.get("body_text", "") for item in clean_items if item.get("body_text")]
        topics = trend_analysis.get("top_topics") or []

        return {
            "title_patterns": self._title_patterns(titles),
            "opening_patterns": self._opening_patterns(bodies),
            "body_patterns": [
                "pain point scene -> practical method -> result feedback",
                "real experience -> key steps -> mistake avoidance reminder",
            ],
            "visual_patterns": [self._visual_pattern(clean_items)],
            "interaction_patterns": [
                "End with a low-friction question that invites comments",
                "Use checklist wording to make the post easy to save",
            ],
            "replicable_templates": [
                f"Around {topics[0] if topics else 'the hot topic'}: scene hook + 3 practical steps + contrast result",
                "Lead with a clear benefit in the title, then show a real process and copyable actions",
            ],
        }

    def _llm_items(self, items: list[dict], limit: int = 20) -> list[dict]:
        compact = []
        for item in items[:limit]:
            compact.append(
                {
                    "title": item.get("title", ""),
                    "body_text": (item.get("body_text", "") or "")[:800],
                    "tags": item.get("tags") or [],
                    "image_count": item.get("image_count", 0),
                    "metrics": item.get("metrics") or {},
                }
            )
        return compact

    def _valid_patterns(self, result: object) -> bool:
        if not isinstance(result, dict):
            return False
        return all(isinstance(result.get(key), list) and result.get(key) for key in self.PATTERN_KEYS)

    def _title_patterns(self, titles: list[str]) -> list[str]:
        patterns = []
        if any("!" in title or "?" in title for title in titles):
            patterns.append("emotion or question driven title")
        if any(any(char.isdigit() for char in title) for title in titles):
            patterns.append("numbered checklist title")
        if any("avoid" in title.lower() or "mistake" in title.lower() for title in titles):
            patterns.append("mistake avoidance title")
        return patterns or ["result-first title", "problem-solution title"]

    def _opening_patterns(self, bodies: list[str]) -> list[str]:
        if not bodies:
            return ["Open with a familiar pain point scene"]
        return ["Give the conclusion first, then explain the process", "Use personal experience to build trust"]

    def _visual_pattern(self, items: list[dict]) -> str:
        image_counts = [item.get("image_count", 0) for item in items]
        if image_counts and max(image_counts) >= 6:
            return "Multi-image step breakdown with the result or conflict in the first image"
        return "Clear first image topic, then a few supporting detail images"
