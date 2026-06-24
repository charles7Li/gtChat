import json
import shutil
from pathlib import Path

from app.agents import ImitationPlannerAgent, PlanAgent, ReportWriterAgent
from app.cleaner import clean_items_with_metadata
from app.workflow.evidence import build_evidence_pack
from app.workflow.graph import clean_items, run_workflow, trace_writer_node
from app.workflow.langgraph_runner import (
    build_langgraph_workflow,
    langgraph_available,
)
from app.workflow.router import route_from_state


ARTIFACT_DIR = Path(__file__).parent / "_artifacts"


def test_plan_agent_routes_trend_report():
    plan = PlanAgent().run("分析宠物赛道趋势")
    assert plan["route"] == "trend_report_path"


def test_plan_agent_routes_imitation_plan():
    plan = PlanAgent().run("生成仿拍选题")
    assert plan["route"] == "imitation_plan_path"


def test_plan_agent_routes_full_pipeline():
    plan = PlanAgent().run("从采集到报告全做一遍")
    assert plan["route"] == "full_pipeline_path"


def test_cleaner_parses_wan_count():
    cleaned = clean_items(
        [
            {
                "id": "1",
                "title": "宠物用品避坑",
                "liked_count": "4.8万",
                "collected_count": "1942",
                "comment_count": "4976",
                "created_at": 1718000000000,
            }
        ]
    )
    assert cleaned[0]["metrics"]["liked_count"] == 48000
    assert cleaned[0]["metrics"]["collected_count"] == 1942
    assert cleaned[0]["metrics"]["comment_count"] == 4976
    assert cleaned[0]["metrics"]["total_engagement"] == 54918
    assert cleaned[0]["created_at"].startswith("2024-")


def test_cleaner_tracks_duplicates_and_quality():
    result = clean_items_with_metadata(
        [
            {"id": "1", "title": "宠物用品避坑", "liked_count": "10"},
            {"id": "1", "title": "宠物用品避坑", "liked_count": "10"},
            {"id": "2", "title": "", "body_text": ""},
        ]
    )
    assert len(result["clean_items"]) == 1
    assert result["data_quality"]["total_raw"] == 3
    assert result["data_quality"]["dropped_duplicate"] == 1
    assert result["data_quality"]["dropped_empty"] == 1
    assert result["dropped_items"][0]["reason"] == "duplicate"


def test_evidence_pack_sorts_top_items_by_engagement():
    state = {
        "run_id": "run-1",
        "keyword": "宠物",
        "clean_items": [
            {"id": "low", "title": "低互动", "body_text": "a", "tags": [], "metrics": {"total_engagement": 1}},
            {"id": "high", "title": "高互动", "body_text": "b" * 600, "tags": ["避坑"], "metrics": {"total_engagement": 99}},
        ],
        "trend_analysis": {"top_topics": ["避坑"]},
        "data_quality": {"quality_score": 80},
    }
    pack = build_evidence_pack(state, limit=1)
    assert pack["top_items"][0]["id"] == "high"
    assert len(pack["top_items"][0]["body_excerpt"]) == 500
    assert pack["topic_candidates"] == ["避坑"]


def test_imitation_planner_falls_back_when_llm_disabled(monkeypatch):
    monkeypatch.delenv("LLM_ENABLE", raising=False)
    plans = ImitationPlannerAgent().run(
        {"top_topics": ["宠物用品"]},
        {"replicable_templates": ["痛点开头 + 步骤拆解"]},
    )
    assert len(plans) == 3
    assert plans[0]["reference_pattern"] == "痛点开头 + 步骤拆解"


def test_imitation_planner_uses_valid_llm_output(monkeypatch):
    def fake_llm_call(prompt_name, payload, schema=None, *, model=None, timeout_seconds=None):
        assert prompt_name == "imitation_planner"
        assert payload["evidence_pack"]["keyword"] == "宠物"
        return {
            "plans": [
                {
                    "idea_title": f"LLM 方案 {index}",
                    "reference_pattern": "结果前置型标题",
                    "shooting_scene": "家中真实场景",
                    "content_structure": ["展示结果", "拆解过程", "引导评论"],
                    "differentiation_point": "换成自己的宠物和生活场景",
                    "required_props": ["手机"],
                    "estimated_difficulty": "low",
                }
                for index in range(1, 4)
            ]
        }

    monkeypatch.setattr("app.agents.imitation_planner_agent.structured_llm_call", fake_llm_call)
    plans = ImitationPlannerAgent().run(
        {"top_topics": ["宠物用品"]},
        {"replicable_templates": ["痛点开头 + 步骤拆解"]},
        {"keyword": "宠物"},
    )
    assert len(plans) == 3
    assert plans[0]["idea_title"] == "LLM 方案 1"


def test_router_returns_route_from_state():
    assert route_from_state({"route": "trend_report_path"}) == "trend_report_path"
    assert route_from_state({"route": "imitation_plan_path"}) == "imitation_plan_path"
    assert route_from_state({"route": "full_pipeline_path"}) == "full_pipeline_path"
    assert route_from_state({"route": "unknown"}) == "trend_report_path"


def test_report_writer_generates_trend_report():
    output_dir = ARTIFACT_DIR / "report_writer"
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = {
            "run_id": "run-1",
            "user_query": "分析宠物赛道趋势",
            "route": "trend_report_path",
            "plan": {"keyword": "宠物"},
            "clean_items": [],
            "data_quality": {"total_raw": 0, "total_clean": 0, "quality_score": 0},
            "evidence_pack": {"top_items": []},
            "trend_analysis": {"summary": "趋势总结", "top_topics": [], "content_type_distribution": {}},
            "pattern_analysis": {"title_patterns": [], "replicable_templates": []},
        }
        result = ReportWriterAgent(output_dir).run(state)
        report_path = output_dir / "trend_report.md"
        evidence_path = output_dir / "evidence_pack.json"
        assert report_path.exists()
        assert evidence_path.exists()
        assert "# 小红书内容趋势分析报告" in report_path.read_text(encoding="utf-8")
        assert "## 2. 数据质量概览" in report_path.read_text(encoding="utf-8")
        assert result["report_path"] == str(report_path)
        assert result["evidence_path"] == str(evidence_path)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_trace_writer_generates_agent_trace():
    output_dir = ARTIFACT_DIR / "trace_writer"
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = {
            "run_id": "run-1",
            "user_query": "生成仿拍选题",
            "route": "imitation_plan_path",
            "review_result": {"overall_score": 86},
            "data_quality": {"quality_score": 90},
            "trace_nodes": [{"name": "plan", "status": "success"}],
        }
        trace_writer_node(state, output_dir)
        trace_path = output_dir / "agent_trace.json"
        assert trace_path.exists()
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["route"] == "imitation_plan_path"
        assert trace["final_score"] == 86
        assert trace["run_id"] == "run-1"
        assert trace["nodes"][0]["name"] == "plan"
        assert trace["data_quality"]["quality_score"] == 90
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_langgraph_runner_is_required():
    assert langgraph_available()
    assert build_langgraph_workflow() is not None


def test_run_workflow_uses_langgraph_entrypoint():
    output_dir = ARTIFACT_DIR / "langgraph_workflow"
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = run_workflow("分析宠物赛道趋势", output_dir)
        assert state["route"] == "trend_report_path"
        assert state["trace_nodes"][0]["name"] == "plan"
        assert any(node["name"] == "route" for node in state["trace_nodes"])
        assert (output_dir / "trend_report.md").exists()
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
