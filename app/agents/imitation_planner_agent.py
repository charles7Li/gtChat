from __future__ import annotations

from app.llm import LLMError, structured_llm_call


class ImitationPlannerAgent:
    def run(
        self,
        trend_analysis: dict,
        pattern_analysis: dict,
        evidence_pack: dict | None = None,
        memory_context: dict | None = None,
    ) -> list[dict]:
        llm_plans = self._try_llm_plans(
            trend_analysis,
            pattern_analysis,
            evidence_pack or {},
            memory_context or {},
        )
        if llm_plans:
            return llm_plans

        return self._rule_based_plans(trend_analysis, pattern_analysis)

    def _try_llm_plans(
        self,
        trend_analysis: dict,
        pattern_analysis: dict,
        evidence_pack: dict,
        memory_context: dict,
    ) -> list[dict]:
        payload = {
            "trend_analysis": trend_analysis,
            "pattern_analysis": pattern_analysis,
            "evidence_pack": evidence_pack,
            "memory_context": memory_context,
        }
        try:
            result = structured_llm_call("imitation_planner", payload)
        except LLMError:
            return []

        plans = result.get("plans") if isinstance(result, dict) else None
        if not isinstance(plans, list) or not 3 <= len(plans) <= 5:
            return []
        if not all(self._valid_plan(plan) for plan in plans):
            return []
        return plans

    def _rule_based_plans(self, trend_analysis: dict, pattern_analysis: dict) -> list[dict]:
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

    def _valid_plan(self, plan: dict) -> bool:
        if not isinstance(plan, dict):
            return False
        required = ("idea_title", "shooting_scene", "differentiation_point")
        if not all(plan.get(key) for key in required):
            return False
        difficulty = plan.get("estimated_difficulty")
        if difficulty and difficulty not in {"low", "medium", "high"}:
            return False
        structure = plan.get("content_structure")
        return not structure or isinstance(structure, list)
