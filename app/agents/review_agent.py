from __future__ import annotations


class ReviewAgent:
    def run(self, imitation_plans: list[dict]) -> dict:
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
            "issues": [] if overall >= 75 else ["方案数量或差异化不足"],
            "revision_suggestions": [] if overall >= 75 else ["补充更明确的差异化场景和执行细节"],
        }
