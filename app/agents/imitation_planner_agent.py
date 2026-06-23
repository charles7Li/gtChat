from __future__ import annotations


class ImitationPlannerAgent:
    def run(self, trend_analysis: dict, pattern_analysis: dict) -> list[dict]:
        topics = trend_analysis.get("top_topics") or ["宠物"]
        templates = pattern_analysis.get("replicable_templates") or ["场景开头 + 实操步骤 + 结果反馈"]
        plans = []

        for index in range(3):
            topic = topics[index % len(topics)]
            template = templates[index % len(templates)]
            plans.append(
                {
                    "idea_title": f"{topic}主题的可执行仿拍选题 {index + 1}",
                    "reference_pattern": template,
                    "shooting_scene": "家中/门店/户外的真实使用场景，保留自然光和过程细节",
                    "content_structure": [
                        "开头 3 秒展示痛点或结果",
                        "中段拆成 3 个可复制步骤",
                        "结尾给出差异化提醒并引导评论",
                    ],
                    "differentiation_point": "换成自己的场景、对象和具体经验，不复刻原笔记表达。",
                    "required_props": ["手机", "自然光", "场景道具"],
                    "estimated_difficulty": "low" if index == 0 else "medium",
                }
            )
        return plans
