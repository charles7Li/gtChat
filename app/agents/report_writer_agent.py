from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class ReportWriterAgent:
    def __init__(self, output_dir: str | Path = "outputs/final_package") -> None:
        self.output_dir = Path(output_dir)

    def run(self, state: dict) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report = self._render_markdown(state)
        report_path = self.output_dir / "trend_report.md"
        manifest_path = self.output_dir / "manifest.json"
        report_path.write_text(report, encoding="utf-8")
        manifest = {
            "report": str(report_path),
            "agent_trace": str(self.output_dir / "agent_trace.json"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        state["final_report"] = report
        state["report_path"] = str(report_path)
        state["manifest_path"] = str(manifest_path)
        return state

    def _render_markdown(self, state: dict) -> str:
        plan = state.get("plan") or {}
        clean_items = state.get("clean_items") or []
        trend = state.get("trend_analysis") or {}
        pattern = state.get("pattern_analysis") or {}
        plans = state.get("imitation_plans") or []
        review = state.get("review_result") or {}
        score = review.get("overall_score")
        review_note = "\n\n> 建议修改：当前方案评分偏低，需补充差异化和执行细节。" if score and score < 75 else ""

        return "\n".join(
            [
                "# 小红书内容趋势分析报告",
                "",
                "## 1. 本次任务",
                f"- 用户需求：{state.get('user_query', '')}",
                f"- 路由：{state.get('route', '')}",
                f"- 关键词：{plan.get('keyword', state.get('keyword', '宠物'))}",
                "",
                "## 2. 数据概览",
                f"- 清洗后内容数：{len(clean_items)}",
                f"- 内容类型分布：{trend.get('content_type_distribution', {})}",
                "",
                "## 3. 热门趋势总结",
                trend.get("summary", "暂无趋势总结。"),
                f"- 热点主题：{', '.join(trend.get('top_topics', []))}",
                "",
                "## 4. 爆款内容套路",
                f"- 标题套路：{', '.join(pattern.get('title_patterns', []))}",
                f"- 可复用模板：{', '.join(pattern.get('replicable_templates', []))}",
                "",
                "## 5. 可仿拍选题方案",
                self._render_plans(plans),
                "",
                "## 6. ReviewAgent 评分",
                f"- 总分：{score if score is not None else '暂无'}",
                f"- 分项：{review.get('scores', {})}{review_note}",
                "",
                "## 7. 后续建议",
                "- 优先复用高互动标题结构，但用自己的场景和经验做差异化。",
                "- 若数据不足，先补充最新搜索结果后再运行完整流程。",
                "",
            ]
        )

    def _render_plans(self, plans: list[dict]) -> str:
        if not plans:
            return "- 本路径未生成仿拍方案。"
        lines = []
        for index, plan in enumerate(plans, start=1):
            lines.extend(
                [
                    f"### 方案 {index}: {plan.get('idea_title', '')}",
                    f"- 参考模式：{plan.get('reference_pattern', '')}",
                    f"- 拍摄场景：{plan.get('shooting_scene', '')}",
                    f"- 差异化：{plan.get('differentiation_point', '')}",
                ]
            )
        return "\n".join(lines)
