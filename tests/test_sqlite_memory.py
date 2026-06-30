from app.memory import SQLiteMemory


def test_sqlite_memory_writes_runs_and_keyword_index(tmp_path):
    memory = SQLiteMemory(tmp_path / "memory.db")
    state = {
        "run_id": "run-1",
        "route": "full_pipeline_path",
        "keyword": "pet",
        "trend_analysis": {"summary": "pet trend"},
        "pattern_analysis": {"replicable_templates": ["template"]},
        "imitation_plans": [{"idea_title": "idea"}],
        "review_result": {"best_plan_index": 0, "overall_score": 88},
    }

    memory.write(state)
    memory.write({**state, "run_id": "run-2", "trend_analysis": {"summary": "pet trend 2"}})
    context = memory.load(keyword="pet")

    assert len(context["keyword_runs"]) == 2
    assert context["keyword_runs"][0]["run_id"] == "run-2"
    assert context["keyword_runs"][0]["pattern_templates"] == ["template"]
    assert context["keyword_runs"][0]["best_plan"]["idea_title"] == "idea"
    assert context["index"]["version"] == 3
    assert context["index"]["keywords"]["pet"]["run_count"] == 2
    assert "pet trend 2" in context["summary"]


def test_sqlite_memory_load_empty_context(tmp_path):
    context = SQLiteMemory(tmp_path / "memory.db").load(keyword="missing")

    assert context["recent_runs"] == []
    assert context["keyword_runs"] == []
    assert context["index"]["keywords"] == {}
