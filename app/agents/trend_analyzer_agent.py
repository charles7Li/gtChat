from __future__ import annotations

from collections import Counter
import re


class TrendAnalyzerAgent:
    def run(self, clean_items: list[dict]) -> dict:
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
                "reason": "标题明确且互动数据高",
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

    def _keywords(self, text: str) -> list[str]:
        words = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text or "")
        stop = {"一个", "这个", "真的", "如何", "什么", "小红书"}
        return [word for word in words if word not in stop]

    def _emotion_hints(self, items: list[dict]) -> list[str]:
        text = " ".join((item.get("title", "") + " " + item.get("body_text", "")) for item in items)
        hints = []
        for word in ("治愈", "焦虑", "省钱", "惊喜", "真实", "避坑"):
            if word in text:
                hints.append(word)
        return hints or ["真实感", "实用性", "陪伴感"]

    def _pain_points(self, items: list[dict]) -> list[str]:
        text = " ".join(item.get("body_text", "") for item in items)
        points = []
        for word in ("不会", "困难", "踩坑", "贵", "麻烦", "不知道"):
            if word in text:
                points.append(word)
        return points or ["用户需要更低门槛的执行方法"]

    def _summary(self, items: list[dict], topics: list[str]) -> str:
        if not items:
            return "暂无可分析数据，建议先补充近期搜索结果。"
        topic_text = "、".join(topics[:5]) if topics else "内容体验"
        return f"本次共分析 {len(items)} 条内容，热点集中在 {topic_text}。"
