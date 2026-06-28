import json
import os
import shutil
from uuid import uuid4
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.cli import _load_env_file
from app.agents import ImitationPlannerAgent, PatternExtractorAgent, PlanAgent, ReportWriterAgent, ReviewAgent, TrendAnalyzerAgent
from app.cleaner import clean_items_with_metadata
from app.llm import LLMError, structured_llm_call
from app.llm.structured_call import _load_prompt, _load_skill
from app.memory import SimpleMemory
from app.workflow.evidence import build_evidence_pack
from app.workflow.graph import clean_items, run_workflow, trace_writer_node
from app.workflow.langgraph_runner import (
    build_langgraph_workflow,
    langgraph_available,
)
from app.workflow.router import route_from_state
from app.workflow.trace import require_state_keys, run_node, warn_dict_missing_keys, warn_missing_outputs


ARTIFACT_DIR = Path(__file__).parent / "_artifacts"


class FakeLLMPlan(BaseModel):
    title: str
    score: int


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
    assert pack["detail_coverage"]["detailed_count"] == 2
    assert pack["top_items"][0]["detail_status"] == "unknown"
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


def test_structured_llm_call_validates_schema_for_openai_compatible_provider(monkeypatch):
    def fake_post_chat_completion(**kwargs):
        return {"choices": [{"message": {"content": '{"title": "方案", "score": 88, "extra": "drop"}'}}]}

    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("app.llm.structured_call._post_chat_completion", fake_post_chat_completion)

    result = structured_llm_call("imitation_planner", {"topic": "宠物"}, FakeLLMPlan)

    assert result == {"title": "方案", "score": 88}


def test_load_prompt_appends_node_skill():
    prompt = _load_prompt("report_writer")

    assert "# Node Skill" in prompt
    assert "imitation playbook writer" in prompt


def test_load_skill_returns_empty_for_missing_skill():
    assert _load_skill("missing_node") == ""


def test_structured_llm_call_uses_packyapi_preset(monkeypatch):
    seen = {}

    def fake_post_chat_completion(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"message": {"content": '{"title": "ok", "score": 88}'}}]}

    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("LLM_PRESET", "packyapi")
    monkeypatch.setenv("PACKY_API_KEY", "packy-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("app.llm.structured_call._post_chat_completion", fake_post_chat_completion)

    result = structured_llm_call("imitation_planner", {"topic": "pet"}, FakeLLMPlan)

    assert result == {"title": "ok", "score": 88}
    assert seen["base_url"] == "https://www.packyapi.com/v1"
    assert seen["api_key"] == "packy-key"


def test_cli_env_loader_reads_local_env_without_overwriting(monkeypatch):
    env_dir = ARTIFACT_DIR / f"cli_env_{uuid4().hex}"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_file = env_dir / ".env"
    try:
        env_file.write_text("LLM_ENABLE=true\nLLM_MODEL=file-model\n", encoding="utf-8")
        monkeypatch.setenv("LLM_MODEL", "existing-model")
        monkeypatch.delenv("LLM_ENABLE", raising=False)

        _load_env_file(env_file)

        assert os.environ["LLM_ENABLE"] == "true"
        assert os.environ["LLM_MODEL"] == "existing-model"
    finally:
        shutil.rmtree(env_dir, ignore_errors=True)


def test_structured_llm_call_validates_schema_for_langchain_provider(monkeypatch):
    def fake_langchain_call(**kwargs):
        return {"title": "方案", "score": "not-int"}

    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_PROVIDER", "langchain")
    monkeypatch.setattr("app.llm.structured_call._call_langchain_chat_openai", fake_langchain_call)

    with pytest.raises(LLMError, match="schema validation"):
        structured_llm_call("imitation_planner", {"topic": "宠物"}, FakeLLMPlan)


def test_trend_analyzer_uses_valid_llm_output(monkeypatch):
    def fake_llm_call(prompt_name, payload, schema=None, *, model=None, timeout_seconds=None):
        assert prompt_name == "trend_analyzer"
        assert payload["clean_items"][0]["body_text"] == "body"
        return {
            "top_topics": ["pet travel"],
            "hot_emotions": ["relief"],
            "audience_pain_points": ["hard to plan"],
            "high_engagement_reasons": [{"title": "title", "liked_count": 10, "reason": "clear outcome"}],
            "content_type_distribution": {"note": 1},
            "summary": "LLM trend summary",
        }

    monkeypatch.setattr("app.agents.trend_analyzer_agent.structured_llm_call", fake_llm_call)
    result = TrendAnalyzerAgent().run(
        [
            {
                "title": "title",
                "body_text": "body",
                "tags": ["pet"],
                "content_type": "note",
                "metrics": {"liked_count": 10},
            }
        ]
    )

    assert result["summary"] == "LLM trend summary"
    assert result["top_topics"] == ["pet travel"]


def test_trend_analyzer_falls_back_when_llm_output_invalid(monkeypatch):
    monkeypatch.setattr("app.agents.trend_analyzer_agent.structured_llm_call", lambda *args, **kwargs: {"summary": ""})
    result = TrendAnalyzerAgent().run(
        [
            {
                "title": "pet checklist",
                "body_text": "hard but practical",
                "tags": ["pet"],
                "content_type": "note",
                "metrics": {"liked_count": 10},
            }
        ]
    )

    assert result["summary"].startswith("Analyzed 1 items")
    assert result["top_topics"][0] == "pet"

def test_pattern_extractor_uses_valid_llm_output(monkeypatch):
    def fake_llm_call(prompt_name, payload, schema=None, *, model=None, timeout_seconds=None):
        assert prompt_name == "pattern_extractor"
        assert payload["trend_analysis"]["top_topics"] == ["pet"]
        return {
            "title_patterns": ["result-first title"],
            "opening_patterns": ["pain point hook"],
            "body_patterns": ["problem -> method -> result"],
            "visual_patterns": ["before/after first image"],
            "interaction_patterns": ["ask for user examples"],
            "replicable_templates": ["show result, explain steps, invite comments"],
        }

    monkeypatch.setattr("app.agents.pattern_extractor_agent.structured_llm_call", fake_llm_call)
    result = PatternExtractorAgent().run(
        [{"title": "pet checklist", "body_text": "body", "tags": ["pet"], "metrics": {"liked_count": 10}}],
        {"top_topics": ["pet"]},
    )

    assert result["replicable_templates"] == ["show result, explain steps, invite comments"]
    assert result["title_patterns"] == ["result-first title"]


def test_pattern_extractor_falls_back_when_llm_output_invalid(monkeypatch):
    monkeypatch.setattr("app.agents.pattern_extractor_agent.structured_llm_call", lambda *args, **kwargs: {"title_patterns": []})
    result = PatternExtractorAgent().run(
        [{"title": "3 pet mistakes", "body_text": "hard mistake", "image_count": 7}],
        {"top_topics": ["pet"]},
    )

    assert result["title_patterns"]
    assert result["replicable_templates"][0].startswith("Around pet")

def test_review_agent_uses_valid_llm_output(monkeypatch):
    def fake_llm_call(prompt_name, payload, schema=None, *, model=None, timeout_seconds=None):
        assert prompt_name == "review_agent"
        assert payload["imitation_plans"][1]["idea_title"] == "second"
        return {
            "overall_score": 91,
            "scores": {
                "trend_relevance": 92,
                "platform_fit": 90,
                "shooting_feasibility": 88,
                "originality": 93,
                "conversion_potential": 91,
            },
            "best_plan_index": 1,
            "issues": ["needs sharper hook"],
            "revision_suggestions": ["make the first 3 seconds more specific"],
        }

    monkeypatch.setattr("app.agents.review_agent.structured_llm_call", fake_llm_call)
    result = ReviewAgent().run([{"idea_title": "first"}, {"idea_title": "second"}])

    assert result["overall_score"] == 91
    assert result["best_plan_index"] == 1


def test_review_agent_falls_back_when_llm_output_invalid(monkeypatch):
    monkeypatch.setattr(
        "app.agents.review_agent.structured_llm_call",
        lambda *args, **kwargs: {"overall_score": 91, "scores": {}, "best_plan_index": 9, "issues": [], "revision_suggestions": []},
    )
    result = ReviewAgent().run([{"idea_title": "only"}])

    assert result["best_plan_index"] == 0
    assert result["overall_score"] >= 75

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
        latest_report_path = output_dir / "trend_report.md"
        report_path = Path(result["report_path"])
        evidence_path = output_dir / "evidence_pack.json"
        report_text = latest_report_path.read_text(encoding="utf-8")
        timestamped_text = report_path.read_text(encoding="utf-8")
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

        assert latest_report_path.exists()
        assert report_path.exists()
        assert evidence_path.exists()
        assert "分析宠物赛道趋势" in report_path.name
        assert "小红书内容趋势分析报告" in report_text
        assert report_text.startswith("# 20")
        assert report_text == timestamped_text
        assert "## 2. 数据质量概览" in report_text
        assert manifest["report"] == str(report_path)
        assert manifest["latest_report"] == str(latest_report_path)
        assert result["evidence_path"] == str(evidence_path)
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_report_writer_uses_valid_llm_report(monkeypatch):
    output_dir = ARTIFACT_DIR / f"report_writer_llm_{uuid4().hex}"
    report = "# LLM Report\n\n" + "Useful creator-facing analysis.\n\n" * 12

    def fake_llm_call(prompt_name, payload, schema=None, *, model=None, timeout_seconds=None):
        assert prompt_name == "report_writer"
        assert payload["trend_analysis"]["summary"] == "trend"
        return {"final_report": report}

    monkeypatch.setattr("app.agents.report_writer_agent.structured_llm_call", fake_llm_call)
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = {
            "run_id": "run-llm-report",
            "user_query": "query",
            "route": "trend_report_path",
            "trend_analysis": {"summary": "trend"},
            "pattern_analysis": {},
            "evidence_pack": {},
            "data_quality": {},
        }
        result = ReportWriterAgent(output_dir).run(state)
        latest_report = (output_dir / "trend_report.md").read_text(encoding="utf-8")

        assert result["final_report"].startswith("# 20")
        assert "query" in result["final_report"].splitlines()[0]
        assert "LLM Report" in result["final_report"].splitlines()[0]
        assert "Useful creator-facing analysis." in result["final_report"]
        assert latest_report == result["final_report"]
        assert Path(result["report_path"]).name.endswith("_query_trend_report.md")
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_report_writer_falls_back_when_llm_report_invalid(monkeypatch):
    output_dir = ARTIFACT_DIR / f"report_writer_fallback_{uuid4().hex}"
    monkeypatch.setattr("app.agents.report_writer_agent.structured_llm_call", lambda *args, **kwargs: {"final_report": "too short"})
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        state = {
            "run_id": "run-template-report",
            "user_query": "query",
            "route": "trend_report_path",
            "plan": {"keyword": "pet"},
            "clean_items": [],
            "data_quality": {"total_raw": 0, "total_clean": 0},
            "evidence_pack": {"top_items": []},
            "trend_analysis": {"summary": "trend", "top_topics": [], "content_type_distribution": {}},
            "pattern_analysis": {"title_patterns": [], "replicable_templates": []},
        }
        result = ReportWriterAgent(output_dir).run(state)

        assert result["final_report"] != "too short"
        assert result["final_report"].startswith("#")
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_report_writer_prompt_focuses_on_trend_following_and_imitation():
    prompt = Path("app/prompts/report_writer.md").read_text(encoding="utf-8")

    assert "怎么追这个趋势" in prompt
    assert "怎么仿拍" in prompt
    assert "detail_coverage" in prompt
    assert "only has search/list-level signals" in prompt
    assert "what can be copied and what must be changed" in prompt

def test_report_writer_prompt_prioritizes_imitation_playbook():
    prompt = Path("app/prompts/report_writer.md").read_text(encoding="utf-8")
    skill = Path("app/skills/report_writer.md").read_text(encoding="utf-8")

    assert "imitation playbook" in prompt
    assert "仿拍作业单" in prompt
    assert "先仿什么" in prompt
    assert "怎么拆原笔记" in prompt
    assert "3-5 个仿拍方案" in prompt
    assert "imitation directions" in skill
    assert "source pattern" in skill
    assert "image-text note" in prompt
    assert "video note" in prompt
    assert "first 3 seconds" in prompt
    assert "cover image" in skill


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


def test_run_node_hooks_validate_inputs_and_warn_outputs():
    def noop_node(state):
        return state

    state = {"warnings": [], "errors": [], "trace_nodes": []}
    result = run_node(
        state,
        "noop",
        noop_node,
        after=[warn_missing_outputs("expected_output")],
    )
    assert result["trace_nodes"][0]["status"] == "warning"
    assert result["warnings"][0]["code"] == "node_missing_output"

    incomplete_state = {"warnings": [], "errors": [], "trace_nodes": [], "analysis": {"summary": ""}}
    result = run_node(
        incomplete_state,
        "quality_gate",
        noop_node,
        after=[warn_dict_missing_keys("analysis", "summary", "top_topics")],
    )
    assert result["trace_nodes"][0]["status"] == "warning"
    assert result["warnings"][0]["code"] == "node_incomplete_output"

    failing_state = {"warnings": [], "errors": [], "trace_nodes": []}
    try:
        run_node(
            failing_state,
            "needs_input",
            noop_node,
            before=[require_state_keys("required_input")],
        )
    except ValueError as exc:
        assert "required_input" in str(exc)
    else:
        raise AssertionError("run_node should fail when required input is missing")
    assert failing_state["errors"][0]["code"] == "node_failed"
    assert failing_state["trace_nodes"][0]["status"] == "failed"


def test_run_node_records_disabled_llm_event(monkeypatch):
    def llm_node(state):
        try:
            structured_llm_call("imitation_planner", {"topic": "pet"})
        except LLMError:
            pass
        return state

    monkeypatch.delenv("LLM_ENABLE", raising=False)
    state = {"warnings": [], "errors": [], "trace_nodes": []}
    result = run_node(state, "llm_disabled", llm_node)

    event = result["trace_nodes"][0]["llm_events"][0]
    assert event["prompt"] == "imitation_planner"
    assert event["status"] == "disabled"


def test_run_node_records_successful_llm_event(monkeypatch):
    def fake_post_chat_completion(**kwargs):
        return {"choices": [{"message": {"content": '{"title": "ok", "score": 88}'}}]}

    def llm_node(state):
        state["llm_result"] = structured_llm_call("imitation_planner", {"topic": "pet"}, FakeLLMPlan)
        return state

    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LANGSMITH_PROJECT", "gtchat-dev")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "secret")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("app.llm.structured_call._post_chat_completion", fake_post_chat_completion)

    state = {"warnings": [], "errors": [], "trace_nodes": []}
    result = run_node(state, "llm_success", llm_node)

    event = result["trace_nodes"][0]["llm_events"][0]
    assert event["prompt"] == "imitation_planner"
    assert event["status"] == "success"
    assert event["model"] == "fake-model"
    assert event["langsmith"] == {"tracing": "true", "project": "gtchat-dev"}
    assert "secret" not in str(event)


def test_simple_memory_writes_v2_runs_and_keyword_index():
    memory_dir = ARTIFACT_DIR / f"memory_{uuid4().hex}"
    shutil.rmtree(memory_dir, ignore_errors=True)
    try:
        memory = SimpleMemory(memory_dir)
        memory.write(
            {
                "run_id": "run-pet",
                "route": "imitation_plan_path",
                "keyword": "pet",
                "trend_analysis": {"summary": "pet trend"},
                "pattern_analysis": {"replicable_templates": ["before after"]},
                "imitation_plans": [{"idea_title": "plan"}],
                "review_result": {"best_plan_index": 0, "overall_score": 86},
            }
        )
        memory.write(
            {
                "run_id": "run-food",
                "keyword": "food",
                "trend_analysis": {"summary": "food trend"},
                "review_result": {"overall_score": 70},
            }
        )

        context = memory.load(keyword="pet")

        assert (memory_dir / "runs.jsonl").exists()
        assert (memory_dir / "index.json").exists()
        assert context["keyword_runs"][0]["run_id"] == "run-pet"
        assert context["recent_runs"][0]["run_id"] == "run-food"
        assert context["index"]["keywords"]["pet"]["run_count"] == 1
        assert context["index"]["keywords"]["pet"]["average_review_score"] == 86
        assert "pet trend" in context["summary"]
    finally:
        shutil.rmtree(memory_dir, ignore_errors=True)


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
        assert all("input_summary" in node for node in state["trace_nodes"])
        assert all("output_summary" in node for node in state["trace_nodes"])
        assert (output_dir / "trend_report.md").exists()
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
