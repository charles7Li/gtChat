from __future__ import annotations

import re
from dataclasses import asdict

from app.schemas.plan import ExecutionPlan


class PlanAgent:
    """Rule-based first version of the planner."""

    TREND_WORDS = ("趋势", "分析", "最近", "什么火")
    IMITATION_WORDS = ("仿拍", "选题", "策划", "参考爆款")
    FULL_WORDS = ("从采集到", "全流程", "生成脚本", "完整", "全做一遍")
    REFERENCE_VIDEO_WORDS = ("参考视频", "视频brief", "video_analysis_brief", "reference video")

    def run(self, user_query: str) -> dict:
        query = user_query or ""
        route = self._route_for(query)
        keyword = self._extract_keyword(query)

        plan = ExecutionPlan(
            route=route,
            keyword=keyword,
            need_collection=route == "full_pipeline_path",
            need_imitation_planning=route in {"imitation_plan_path", "full_pipeline_path", "reference_video_imitation_path"},
            need_review=route in {"imitation_plan_path", "full_pipeline_path", "reference_video_imitation_path"},
            reference_video_path=self._extract_reference_video_path(query) if route == "reference_video_imitation_path" else "",
        )
        return asdict(plan)

    def _route_for(self, query: str) -> str:
        if any(word in query for word in self.REFERENCE_VIDEO_WORDS):
            return "reference_video_imitation_path"
        if any(word in query for word in self.FULL_WORDS):
            return "full_pipeline_path"
        if any(word in query for word in self.IMITATION_WORDS):
            return "imitation_plan_path"
        if any(word in query for word in self.TREND_WORDS):
            return "trend_report_path"
        return "trend_report_path"

    def _extract_keyword(self, query: str) -> str:
        for pattern in (
            r"分析(.+?)赛道趋势",
            r"分析(.+?)趋势",
            r"(.+?)赛道",
            r"关于(.+?)(?:的|趋势|选题|策划|$)",
        ):
            match = re.search(pattern, query)
            if match:
                keyword = match.group(1).strip(" ，。,.")
                if keyword:
                    return keyword
        return "宠物"

    def _extract_reference_video_path(self, query: str) -> str:
        for pattern in (
            r"(?:brief|path|文件|路径|视频)[:=：]\s*([^\s]+\.json)",
            r"([A-Za-z]:\\[^\s]+\.json)",
            r"([^\s]+video_analysis_brief\.json)",
        ):
            match = re.search(pattern, query)
            if match:
                return match.group(1).strip('"')
        return ""
