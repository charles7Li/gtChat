from __future__ import annotations


class SearchStrategySubAgent:
    def run(self, plan: dict, gaps: dict | None = None) -> dict:
        keyword = plan.get("keyword") or "宠物"
        if plan.get("status") != "planned":
            return {"status": "skipped", "queries": []}
        suffixes = (gaps or {}).get("suffixes") or ["趋势", "避坑", "仿拍"]
        return {
            "status": "ready",
            "queries": [
                {"keyword": f"{keyword}{suffix}", "sort": "popularity_descending", "time_filter": "一周内", "deep_limit": 10}
                for suffix in suffixes[:3]
            ],
        }
