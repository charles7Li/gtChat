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
        evidence_path = self.output_dir / "evidence_pack.json"
        report_path.write_text(report, encoding="utf-8")
        evidence_path.write_text(
            json.dumps(state.get("evidence_pack", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest = {
            "run_id": state.get("run_id"),
            "report": str(report_path),
            "agent_trace": str(self.output_dir / "agent_trace.json"),
            "evidence_pack": str(evidence_path),
            "route": state.get("route"),
            "keyword": (state.get("plan") or {}).get("keyword", state.get("keyword")),
            "data_quality": state.get("data_quality", {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        state["final_report"] = report
        state["report_path"] = str(report_path)
        state["manifest_path"] = str(manifest_path)
        state["evidence_path"] = str(evidence_path)
        return state

    def _render_markdown(self, state: dict) -> str:
        plan = state.get("plan") or {}
        clean_items = state.get("clean_items") or []
        trend = state.get("trend_analysis") or {}
        pattern = state.get("pattern_analysis") or {}
        plans = state.get("imitation_plans") or []
        review = state.get("review_result") or {}
        data_quality = state.get("data_quality") or {}
        dropped = state.get("dropped_items") or []
        evidence = state.get("evidence_pack") or {}
        warnings = state.get("warnings") or []
        score = review.get("overall_score")
        review_note = "\n\n> 建议修改：当前方案评分偏低，需补充差异化和执行细节。" if score and score < 75 else ""

        return "\n".join(
            [
                "# 小红书内容趋势分析报告",
                "",
                "## 1. 本次任务与数据来源",
                f"- 用户需求：{state.get('user_query', '')}",
                f"- 路由：{state.get('route', '')}",
                f"- 关键词：{plan.get('keyword', state.get('keyword', '宠物'))}",
                f"- Run ID：{state.get('run_id', '')}",
                "",
                "## 2. 数据质量概览",
                f"- 原始内容数：{data_quality.get('total_raw', len(state.get('raw_items', [])))}",
                f"- 清洗后内容数：{data_quality.get('total_clean', len(clean_items))}",
                f"- 丢弃内容数：{len(dropped)}",
                f"- 重复内容数：{data_quality.get('dropped_duplicate', 0)}",
                f"- 质量评分：{data_quality.get('quality_score', '暂无')}",
                f"- 内容类型分布：{trend.get('content_type_distribution', {})}",
                "",
                "## 3. 热门趋势总结",
                trend.get("summary", "暂无趋势总结。"),
                f"- 热点主题：{', '.join(trend.get('top_topics', []))}",
                "",
                "## 4. 高互动样本证据",
                self._render_evidence(evidence),
                "",
                "## 5. 爆款内容套路",
                f"- 标题套路：{', '.join(pattern.get('title_patterns', []))}",
                f"- 可复用模板：{', '.join(pattern.get('replicable_templates', []))}",
                "",
                "## 6. 可仿拍选题方案",
                self._render_plans(plans),
                "",
                "## 7. ReviewAgent 评分",
                f"- 总分：{score if score is not None else '暂无'}",
                f"- 分项：{review.get('scores', {})}{review_note}",
                "",
                "## 8. 风险与后续动作",
                self._render_warnings(warnings),
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

    def _render_evidence(self, evidence: dict) -> str:
        items = evidence.get("top_items") or []
        if not items:
            return "- 暂无高互动样本证据。"
        lines = []
        for item in items[:5]:
            metrics = item.get("metrics", {})
            title = item.get("title") or item.get("body_excerpt") or "无标题"
            lines.append(
                "- "
                + f"{title} "
                + f"(id={item.get('id', '')}, engagement={metrics.get('total_engagement', 0)})"
            )
        return "\n".join(lines)

    def _render_warnings(self, warnings: list[dict]) -> str:
        if not warnings:
            return ""
        lines = ["- 本次运行存在以下降级或风险："]
        for warning in warnings:
            lines.append(f"- [{warning.get('code', 'warning')}] {warning.get('message', '')}")
        return "\n".join(lines)
