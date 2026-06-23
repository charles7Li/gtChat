import json
import shutil
from pathlib import Path

from app.agents import PlanAgent, ReportWriterAgent
from app.workflow.graph import clean_items, trace_writer_node
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
    assert cleaned[0]["created_at"].startswith("2024-")


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
            "user_query": "分析宠物赛道趋势",
            "route": "trend_report_path",
            "plan": {"keyword": "宠物"},
            "clean_items": [],
            "trend_analysis": {"summary": "趋势总结", "top_topics": [], "content_type_distribution": {}},
            "pattern_analysis": {"title_patterns": [], "replicable_templates": []},
        }
        result = ReportWriterAgent(output_dir).run(state)
        report_path = output_dir / "trend_report.md"
        assert report_path.exists()
        assert "# 小红书内容趋势分析报告" in report_path.read_text(encoding="utf-8")
        assert result["report_path"] == str(report_path)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_trace_writer_generates_agent_trace():
    output_dir = ARTIFACT_DIR / "trace_writer"
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = {
            "user_query": "生成仿拍选题",
            "route": "imitation_plan_path",
            "review_result": {"overall_score": 86},
        }
        trace_writer_node(state, output_dir)
        trace_path = output_dir / "agent_trace.json"
        assert trace_path.exists()
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["route"] == "imitation_plan_path"
        assert trace["final_score"] == 86
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
