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
from app.hotspots import HotspotRule, MonitorJobConfig, build_hotspot_analysis_payload, evaluate_hotspot_signal, run_hotspot_monitor_once
from app.memory import SimpleMemory
from app.schemas.analysis import PatternExtractionResult, ReviewResult
from app.workflow.evidence import build_evidence_pack
from app.workflow.graph import clean_items, run_workflow, trace_writer_node
from app.workflow.graph import commercial_data_import_node
from app.workflow.langgraph_runner import (
    build_langgraph_workflow,
    langgraph_available,
    run_workflow_langgraph,
)
from app.workflow.performance import build_performance_summary
from app.workflow.route_manifest import load_route_manifests
from app.workflow.router import route_from_state
from app.workflow.trace import NODE_CONTRACTS, require_state_keys, run_node, warn_dict_missing_keys, warn_missing_outputs


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


def test_plan_agent_routes_reference_video_imitation():
    plan = PlanAgent().run(r"基于参考视频 path=C:\tmp\video_analysis_brief.json 生成仿拍")
    assert plan["route"] == "reference_video_imitation_path"
    assert plan["reference_video_path"] == r"C:\tmp\video_analysis_brief.json"


def test_plan_agent_routes_commercial_data_analysis():
    plan = PlanAgent().run("分析蝉妈妈导出文件")
    assert plan["route"] == "commercial_data_analysis_path"


def test_plan_agent_routes_hotspot_auto_analysis():
    plan = PlanAgent().run("热点自动分析宠物趋势")
    assert plan["route"] == "hotspot_auto_analysis_path"


def test_plan_agent_accepts_reference_video_file_path():
    plan = PlanAgent().run(r"基于参考视频 path=C:\tmp\reference.mp4 生成仿拍")
    assert plan["route"] == "reference_video_imitation_path"
    assert plan["reference_video_path"] == r"C:\tmp\reference.mp4"


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
        assert schema is PatternExtractionResult
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
        assert schema is ReviewResult
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
    assert route_from_state({"route": "reference_video_imitation_path"}) == "reference_video_imitation_path"
    assert route_from_state({"route": "commercial_data_analysis_path"}) == "commercial_data_analysis_path"
    assert route_from_state({"route": "hotspot_auto_analysis_path"}) == "hotspot_auto_analysis_path"
    assert route_from_state({"route": "unknown"}) == "trend_report_path"


def test_route_manifests_match_current_langgraph_paths():
    manifests = load_route_manifests()
    runner_nodes = set(NODE_CONTRACTS) | {"store", "memory_write", "trace"}

    assert set(manifests) == {
        "trend_report_path",
        "imitation_plan_path",
        "full_pipeline_path",
        "reference_video_imitation_path",
        "commercial_data_analysis_path",
        "hotspot_auto_analysis_path",
    }
    assert manifests["trend_report_path"].stage_names == [
        "plan",
        "route",
        "memory_load",
        "load_latest_search_results",
        "clean",
        "trend_analyze",
        "pattern_extract",
        "evidence_pack",
        "report",
        "trace",
    ]
    assert manifests["imitation_plan_path"].stage_names == [
        "plan",
        "route",
        "memory_load",
        "load_latest_search_results",
        "clean",
        "trend_analyze",
        "pattern_extract",
        "evidence_pack",
        "imitation_plan",
        "review",
        "report",
        "trace",
    ]
    assert manifests["full_pipeline_path"].stage_names == [
        "plan",
        "route",
        "memory_load",
        "collect",
        "clean",
        "store",
        "trend_analyze",
        "pattern_extract",
        "evidence_pack",
        "imitation_plan",
        "review",
        "report",
        "memory_write",
        "trace",
    ]
    assert manifests["reference_video_imitation_path"].stage_names == [
        "plan",
        "route",
        "local_video_analyze",
        "video_pattern_extract",
        "imitation_plan",
        "review",
        "report",
        "trace",
    ]
    assert manifests["commercial_data_analysis_path"].stage_names == [
        "plan",
        "route",
        "memory_load",
        "commercial_data_import",
        "trace",
    ]
    assert manifests["hotspot_auto_analysis_path"].stage_names == [
        "plan",
        "route",
        "memory_load",
        "load_latest_search_results",
        "clean",
        "trend_analyze",
        "pattern_extract",
        "evidence_pack",
        "imitation_plan",
        "review",
        "report",
        "trace",
    ]
    for manifest in manifests.values():
        assert set(manifest.stage_names) <= runner_nodes
        if not manifest.allow_live_collect:
            assert "collect" not in manifest.stage_names


def test_commercial_data_import_node_dry_run(tmp_path):
    root = tmp_path / "chanmama"
    pending = root / "pending"
    pending.mkdir(parents=True)
    (pending / "creators.csv").write_text("creator_id,name\nc1,A\n", encoding="utf-8")

    state = commercial_data_import_node({"route": "commercial_data_analysis_path"}, path=root)

    assert state["commercial_import_summary"]["source"] == "chanmama"
    assert state["commercial_import_summary"]["record_count"] == 1
    assert (root / "processed" / "creators.csv").exists()


def test_hotspot_rule_builds_auto_analysis_payload():
    signal = {"signal_id": "s1", "source": "douyin_hot_board", "keyword": "pet", "rank": 3, "heat_score": 88}

    evaluation = evaluate_hotspot_signal(signal, HotspotRule(min_heat_score=80, min_rank=5, required_sources=("douyin_hot_board",)))
    payload = build_hotspot_analysis_payload(signal, evaluation)

    assert evaluation["triggered"] is True
    assert "heat_score >= 80" in evaluation["reasons"]
    assert "rank <= 5" in evaluation["reasons"]
    assert payload["route"] == "hotspot_auto_analysis_path"
    assert payload["keyword"] == "pet"
    assert payload["source"] == "douyin_hot_board"


def test_hotspot_rule_rejects_disallowed_source():
    evaluation = evaluate_hotspot_signal({"source": "xhs", "keyword": "pet", "heat_score": 99}, HotspotRule(min_heat_score=80, required_sources=("douyin_hot_board",)))

    assert evaluation["triggered"] is False
    assert evaluation["reasons"] == ["source xhs not allowed"]


def test_run_hotspot_monitor_once_builds_payloads_without_live():
    config = MonitorJobConfig(
        job_id="job-1",
        name="pet monitor",
        platforms=("douyin_hot_board",),
        keywords=("pet",),
        allow_live=True,
        rule=HotspotRule(min_heat_score=80),
    )
    signals = [
        {"signal_id": "s1", "source": "douyin_hot_board", "keyword": "pet", "heat_score": 90},
        {"signal_id": "s2", "source": "douyin_hot_board", "keyword": "other", "heat_score": 99},
    ]

    result = run_hotspot_monitor_once(config, signals)

    assert result["status"] == "triggered"
    assert result["signals_found"] == 1
    assert result["triggered_analysis"] is True
    assert result["analysis_payloads"][0]["route"] == "hotspot_auto_analysis_path"
    assert result["warnings"] == ["allow_live ignored by dry-run monitor"]


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
            "commercial_import_summary": {"source": "chanmama", "record_count": 1, "provenance": [{"source_type": "chanmama_export"}]},
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
        assert "数据来源：chanmama / commercial_import / records=1" in report_text
        assert manifest["report"] == str(report_path)
        assert manifest["latest_report"] == str(latest_report_path)
        assert manifest["source_summary"]["sources"][0]["source"] == "chanmama"
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
            "raw_items": [{"id": "1", "platform": "douyin", "provenance": {"source_type": "endpoint"}}],
            "trace_nodes": [{"name": "plan", "status": "success", "duration_ms": 5}],
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
        assert trace["source_summary"]["sources"][0]["source"] == "douyin"
        assert trace["performance"]["workflow_total_ms"] == 5
        assert trace["performance"]["budget_passed"] is True
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_build_performance_summary_counts_nodes_and_llm_events():
    summary = build_performance_summary(
        [
            {"name": "plan", "status": "success", "duration_ms": 3, "llm_events": [{"latency_ms": 2}]},
            {"name": "report", "status": "success", "duration_ms": 8},
        ],
        route="trend_report_path",
        budget_ms=10,
    )

    assert summary["workflow_total_ms"] == 11
    assert summary["llm_total_ms"] == 2
    assert summary["slowest_node"]["name"] == "report"
    assert summary["budget_ms"] == 10
    assert summary["budget_passed"] is False


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
    assert event["prompt_version"]
    assert isinstance(event["latency_ms"], int)


def test_run_node_records_successful_llm_event(monkeypatch):
    def fake_post_chat_completion(**kwargs):
        return {
            "choices": [{"message": {"content": '{"title": "ok", "score": 88}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }

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
    assert event["prompt_version"]
    assert isinstance(event["latency_ms"], int)
    assert event["token_usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
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


def test_langgraph_runner_passes_langsmith_config_when_enabled(monkeypatch):
    seen = {}

    class FakeGraphApp:
        def invoke(self, state, config=None):
            seen["state"] = state
            seen["config"] = config
            return state

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "gtchat-test")
    monkeypatch.setenv("LANGSMITH_RUN_NAME", "custom-run")
    monkeypatch.setattr("app.workflow.langgraph_runner.build_langgraph_workflow", lambda *args, **kwargs: FakeGraphApp())

    state = run_workflow_langgraph("生成仿拍选题")

    assert state["user_query"] == "生成仿拍选题"
    assert seen["config"]["run_name"] == "custom-run"
    assert seen["config"]["tags"] == ["gtchat", "langgraph"]
    assert seen["config"]["metadata"]["project"] == "gtchat-test"
    assert seen["config"]["metadata"]["entrypoint"] == "langgraph"


def test_langgraph_runner_skips_langsmith_config_by_default(monkeypatch):
    seen = {}

    class FakeGraphApp:
        def invoke(self, state, config=None):
            seen["config"] = config
            return state

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setattr("app.workflow.langgraph_runner.build_langgraph_workflow", lambda *args, **kwargs: FakeGraphApp())

    run_workflow_langgraph("分析宠物赛道趋势")

    assert seen["config"] is None


def test_run_workflow_reference_video_imitation_path(monkeypatch):
    output_dir = ARTIFACT_DIR / "reference_video_workflow"
    brief_dir = ARTIFACT_DIR / "reference_video_input"
    brief_path = brief_dir / "video_analysis_brief.json"
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(brief_dir, ignore_errors=True)
    brief_dir.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(
            {
                "source": {"local_path": "reference.mp4", "title": "宠物洗护前后对比", "duration_seconds": 18},
                "transcript": {"full_text": "先展示洗护前后对比，再拆步骤。", "segments": [], "word_count": 16, "language": "zh"},
                "structure_analysis": {"total_scenes": 3, "scenes": []},
                "keyframes": ["keyframes/frame_0000.jpg"],
                "style_profile": {"visual_patterns": ["first frame shows before after contrast"]},
                "replication_guidance": {
                    "topic": "宠物洗护",
                    "replicable_templates": ["before after hook -> three cleaning steps -> result close-up"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_ENABLE", raising=False)
    try:
        state = run_workflow(f"基于参考视频 path={brief_path} 生成仿拍", output_dir)
        trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))

        assert state["route"] == "reference_video_imitation_path"
        assert state["reference_video_path"] == str(brief_path)
        assert state["trend_analysis"]["top_topics"] == ["宠物洗护"]
        assert state["pattern_analysis"]["replicable_templates"][0].startswith("before after hook")
        assert len(state["imitation_plans"]) == 3
        assert [node["name"] for node in state["trace_nodes"]] == [
            "plan",
            "route",
            "local_video_analyze",
            "video_pattern_extract",
            "imitation_plan",
            "review",
            "report",
        ]
        assert trace["route"] == "reference_video_imitation_path"
        assert (output_dir / "trend_report.md").exists()
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(brief_dir, ignore_errors=True)


def test_run_workflow_reference_video_file_path_generates_brief(monkeypatch):
    output_dir = ARTIFACT_DIR / "reference_video_file_workflow"
    video_dir = ARTIFACT_DIR / "reference_video_file_input"
    video_path = video_dir / "reference.mp4"
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(video_dir, ignore_errors=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path.write_text("fake", encoding="utf-8")

    def fake_analyze_local_video(path, *, output_dir, **kwargs):
        brief = {
            "source": {"local_path": str(path), "title": "宠物洗护视频", "duration_seconds": 10},
            "transcript": {"full_text": "洗护前后对比。", "segments": [], "word_count": 7, "language": "zh"},
            "structure_analysis": {"total_scenes": 1, "scenes": []},
            "keyframes": ["keyframes/frame_0000.jpg"],
            "style_profile": {"visual_patterns": ["before after frame"]},
            "replication_guidance": {"topic": "宠物洗护"},
            "_analysis_meta": {"output_path": str(Path(output_dir) / "video_analysis_brief.json")},
        }
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "video_analysis_brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
        return brief

    monkeypatch.setattr("app.workflow.graph.analyze_local_video", fake_analyze_local_video)
    monkeypatch.delenv("LLM_ENABLE", raising=False)
    try:
        state = run_workflow(f"基于参考视频 path={video_path} 生成仿拍", output_dir)

        assert state["route"] == "reference_video_imitation_path"
        assert state["reference_video_source_path"] == str(video_path)
        assert state["reference_video_path"].endswith("video_analysis_brief.json")
        assert state["trend_analysis"]["top_topics"] == ["宠物洗护"]
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(video_dir, ignore_errors=True)


@pytest.mark.parametrize(
    ("query", "route", "expected_nodes"),
    [
        (
            "分析宠物赛道趋势",
            "trend_report_path",
            [
                "plan",
                "route",
                "memory_load",
                "load_latest_search_results",
                "clean",
                "trend_analyze",
                "pattern_extract",
                "evidence_pack",
                "report",
            ],
        ),
        (
            "生成仿拍选题",
            "imitation_plan_path",
            [
                "plan",
                "route",
                "memory_load",
                "load_latest_search_results",
                "clean",
                "trend_analyze",
                "pattern_extract",
                "evidence_pack",
                "imitation_plan",
                "review",
                "report",
            ],
        ),
        (
            "从采集到报告全做一遍",
            "full_pipeline_path",
            [
                "plan",
                "route",
                "memory_load",
                "collect",
                "clean",
                "store",
                "trend_analyze",
                "pattern_extract",
                "evidence_pack",
                "imitation_plan",
                "review",
                "report",
                "memory_write",
            ],
        ),
    ],
)
def test_run_workflow_uses_langgraph_entrypoint_for_all_routes(monkeypatch, query, route, expected_nodes):
    output_dir = ARTIFACT_DIR / f"langgraph_workflow_{route}"
    shutil.rmtree(output_dir, ignore_errors=True)

    def fake_memory_load(state):
        state["memory_context"] = {"index": {}, "recent_runs": [], "keyword_runs": [], "summary": ""}
        return state

    def fake_load_latest_search_results(state):
        state["raw_items"] = _workflow_fixture_items()
        return state

    def fake_collect(state):
        state["collector_result"] = {"status": "success", "source": "fixture", "count": 1}
        state["raw_items"] = _workflow_fixture_items()
        return state

    def fake_store(state):
        return state

    def fake_memory_write(state):
        state["memory_written"] = True
        return state

    monkeypatch.setattr("app.workflow.langgraph_runner.memory_load_node", fake_memory_load)
    monkeypatch.setattr("app.workflow.langgraph_runner.load_latest_search_results_node", fake_load_latest_search_results)
    monkeypatch.setattr("app.workflow.langgraph_runner.collector_node", fake_collect)
    monkeypatch.setattr("app.workflow.langgraph_runner.storage_node", fake_store)
    monkeypatch.setattr("app.workflow.langgraph_runner.memory_write_node", fake_memory_write)

    try:
        state = run_workflow(query, output_dir)
        trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))

        assert state["route"] == route
        assert [node["name"] for node in state["trace_nodes"]] == expected_nodes
        assert all("input_summary" in node for node in state["trace_nodes"])
        assert all("output_summary" in node for node in state["trace_nodes"])
        assert trace["route"] == route
        assert [node["name"] for node in trace["nodes"]] == expected_nodes
        assert state["trace_path"] == str(output_dir / "agent_trace.json")
        assert (output_dir / "trend_report.md").exists()
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _workflow_fixture_items():
    return [
        {
            "id": "fixture-1",
            "title": "宠物用品避坑清单",
            "body_text": "新手养宠常见痛点和解决步骤",
            "tags": ["宠物", "避坑"],
            "content_type": "note",
            "liked_count": "100",
            "collected_count": "20",
            "comment_count": "5",
            "created_at": 1718000000000,
        }
    ]
