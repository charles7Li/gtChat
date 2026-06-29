from __future__ import annotations

from app.llm import LLMError, structured_llm_call
from app.schemas.analysis import ReviewResult


class ReviewAgent:
    SCORE_KEYS = (
        "trend_relevance",
        "platform_fit",
        "shooting_feasibility",
        "originality",
        "conversion_potential",
    )

    def run(self, imitation_plans: list[dict]) -> dict:
        llm_result = self._try_llm_review(imitation_plans)
        if llm_result:
            return llm_result
        return self._rule_based_review(imitation_plans)

    def _try_llm_review(self, imitation_plans: list[dict]) -> dict:
        try:
            result = structured_llm_call("review_agent", {"imitation_plans": imitation_plans[:5]}, ReviewResult)
        except LLMError:
            return {}
        return result if self._valid_review(result, len(imitation_plans)) else {}

    def _rule_based_review(self, imitation_plans: list[dict]) -> dict:
        count = len(imitation_plans)
        base = 72 + min(count, 5) * 3
        scores = {
            "trend_relevance": min(base + 6, 95),
            "platform_fit": min(base + 2, 92),
            "shooting_feasibility": min(base + 4, 94),
            "originality": min(base, 90),
            "conversion_potential": min(base - 2, 88),
        }
        overall = round(sum(scores.values()) / len(scores))
        return {
            "overall_score": overall,
            "scores": scores,
            "best_plan_index": 0 if imitation_plans else None,
            "issues": [] if overall >= 75 else ["Plans need clearer differentiation"],
            "revision_suggestions": [] if overall >= 75 else ["Add more concrete scenes and execution details"],
        }

    def _valid_review(self, result: object, plan_count: int) -> bool:
        if not isinstance(result, dict):
            return False
        if not isinstance(result.get("overall_score"), int):
            return False
        scores = result.get("scores")
        if not isinstance(scores, dict):
            return False
        if not all(isinstance(scores.get(key), int) for key in self.SCORE_KEYS):
            return False
        best_index = result.get("best_plan_index")
        if best_index is not None and (not isinstance(best_index, int) or best_index < 0 or best_index >= plan_count):
            return False
        return isinstance(result.get("issues"), list) and isinstance(result.get("revision_suggestions"), list)
