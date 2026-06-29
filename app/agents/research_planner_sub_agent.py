from __future__ import annotations


class ResearchPlannerSubAgent:
    def run(self, decision: dict, evidence: dict | None = None) -> dict:
        keyword = (evidence or {}).get("keyword") or decision.get("keyword") or "宠物"
        if decision.get("decision") != "accept":
            return {"status": "skipped", "questions": [], "keyword": keyword}
        return {
            "status": "planned",
            "keyword": keyword,
            "questions": [
                f"{keyword} 最近增长最快的内容角度是什么？",
                f"{keyword} 哪些标题和开头结构重复出现？",
                f"{keyword} 是否有足够样本支持生成仿拍方案？",
            ],
            "max_iterations": 1,
        }
