from __future__ import annotations

from collections import Counter
import re

from app.llm import LLMError, structured_llm_call


class TrendAnalyzerAgent:
    def run(self, clean_items: list[dict]) -> dict:
        llm_result = self._try_llm_analysis(clean_items)
        if llm_result:
            return llm_result
        return self._rule_based_analysis(clean_items)

    def _try_llm_analysis(self, clean_items: list[dict]) -> dict:
        payload = {"clean_items": self._llm_items(clean_items)}
        try:
            result = structured_llm_call("trend_analyzer", payload)
        except LLMError:
            return {}
        return result if self._valid_analysis(result) else {}

    def _rule_based_analysis(self, clean_items: list[dict]) -> dict:
        tags = Counter()
        title_words = Counter()
        content_types = Counter()

        for item in clean_items:
            tags.update(item.get("tags") or [])
            title_words.update(self._keywords(item.get("title", "")))
            content_types[item.get("content_type") or "unknown"] += 1

        top_items = sorted(
            clean_items,
            key=lambda item: item.get("metrics", {}).get("liked_count", 0),
            reverse=True,
        )[:5]

        top_topics = [word for word, _ in (tags + title_words).most_common(10)]
        high_engagement = [
            {
                "title": item.get("title", ""),
                "liked_count": item.get("metrics", {}).get("liked_count", 0),
                "reason": "Clear title and strong engagement data",
            }
            for item in top_items
        ]

        return {
            "top_topics": top_topics,
            "hot_emotions": self._emotion_hints(clean_items),
            "audience_pain_points": self._pain_points(clean_items),
            "high_engagement_reasons": high_engagement,
            "content_type_distribution": dict(content_types),
            "summary": self._summary(clean_items, top_topics),
        }

    def _llm_items(self, items: list[dict], limit: int = 20) -> list[dict]:
        compact = []
        for item in items[:limit]:
            compact.append(
                {
                    "title": item.get("title", ""),
                    "body_text": (item.get("body_text", "") or "")[:800],
                    "tags": item.get("tags") or [],
                    "content_type": item.get("content_type") or "unknown",
                    "metrics": item.get("metrics") or {},
                }
            )
        return compact

    def _valid_analysis(self, result: object) -> bool:
        if not isinstance(result, dict):
            return False
        required_lists = ("top_topics", "hot_emotions", "audience_pain_points", "high_engagement_reasons")
        if not all(isinstance(result.get(key), list) and result.get(key) for key in required_lists):
            return False
        if not isinstance(result.get("content_type_distribution"), dict):
            return False
        return bool(result.get("summary"))

    def _keywords(self, text: str) -> list[str]:
        words = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text or "")
        stop = {"this", "that", "how", "what", "xiaohongshu"}
        return [word for word in words if word.lower() not in stop]

    def _emotion_hints(self, items: list[dict]) -> list[str]:
        text = " ".join((item.get("title", "") + " " + item.get("body_text", "")) for item in items).lower()
        hints = []
        for word in ("healing", "anxiety", "save money", "surprise", "real", "avoid"):
            if word in text:
                hints.append(word)
        return hints or ["authentic", "practical", "companionship"]

    def _pain_points(self, items: list[dict]) -> list[str]:
        text = " ".join(item.get("body_text", "") for item in items).lower()
        points = []
        for word in ("hard", "expensive", "mistake", "confusing", "trouble"):
            if word in text:
                points.append(word)
        return points or ["Users need lower-friction steps they can copy quickly"]

    def _summary(self, items: list[dict], topics: list[str]) -> str:
        if not items:
            return "No clean items are available yet. Collect or load recent search results first."
        topic_text = ", ".join(topics[:5]) if topics else "content experience"
        return f"Analyzed {len(items)} items. Current topics cluster around {topic_text}."
