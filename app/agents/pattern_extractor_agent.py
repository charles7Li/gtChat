from __future__ import annotations


class PatternExtractorAgent:
    def run(self, clean_items: list[dict], trend_analysis: dict) -> dict:
        titles = [item.get("title", "") for item in clean_items if item.get("title")]
        bodies = [item.get("body_text", "") for item in clean_items if item.get("body_text")]
        topics = trend_analysis.get("top_topics") or []

        return {
            "title_patterns": self._title_patterns(titles),
            "opening_patterns": self._opening_patterns(bodies),
            "body_patterns": [
                "痛点场景 -> 解决方法 -> 结果反馈",
                "真实经历 -> 关键步骤 -> 避坑提醒",
            ],
            "visual_patterns": [
                self._visual_pattern(clean_items),
            ],
            "interaction_patterns": [
                "结尾提出低门槛问题，引导用户分享经验",
                "用清单式表达降低收藏成本",
            ],
            "replicable_templates": [
                f"围绕{topics[0] if topics else '热点主题'}：场景开头 + 3 个实操步骤 + 对比结果",
                "标题制造明确收益，正文补充真实过程和可复制动作",
            ],
        }

    def _title_patterns(self, titles: list[str]) -> list[str]:
        patterns = []
        if any("!" in title or "！" in title for title in titles):
            patterns.append("强情绪感叹标题")
        if any(any(char.isdigit() for char in title) for title in titles):
            patterns.append("数字清单型标题")
        if any("避坑" in title or "后悔" in title for title in titles):
            patterns.append("避坑提醒型标题")
        return patterns or ["结果前置型标题", "问题解决型标题"]

    def _opening_patterns(self, bodies: list[str]) -> list[str]:
        if not bodies:
            return ["直接抛出用户熟悉的痛点场景"]
        return ["先给结论，再解释过程", "用个人经历建立真实感"]

    def _visual_pattern(self, items: list[dict]) -> str:
        image_counts = [item.get("image_count", 0) for item in items]
        if image_counts and max(image_counts) >= 6:
            return "多图步骤拆解，首图突出结果或冲突点"
        return "首图明确主题，正文用少量图片补充细节"
