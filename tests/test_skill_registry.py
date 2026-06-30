from app.skills import SkillContext, create_default_registry, load_allowed_skills


def test_default_skill_registry_lists_local_skills():
    registry = create_default_registry()

    assert registry.list_skills() == ["chanmama_import", "local_video_analyze", "report_export"]


def test_skill_registry_checks_allowed_skills(tmp_path):
    config = tmp_path / "agent_skills.yaml"
    config.write_text("agent_a:\n  - report_export\n", encoding="utf-8")
    registry = create_default_registry(load_allowed_skills(config))
    trace = {}

    allowed = registry.call("report_export", {"path": tmp_path / "missing.md"}, context=SkillContext(agent="agent_a", trace=trace))
    denied = registry.call("chanmama_import", {"path": tmp_path / "missing.csv"}, context=SkillContext(agent="agent_a", trace=trace))

    assert allowed.status == "success"
    assert allowed.data["exists"] is False
    assert denied.status == "failed"
    assert "not allowed" in denied.error
    assert [item["skill"] for item in trace["skill_timings"]] == ["report_export", "chanmama_import"]


def test_chanmama_import_skill_uses_file_import_adapter(tmp_path):
    path = tmp_path / "videos.csv"
    path.write_text("video_id,title\nv1,hello\n", encoding="utf-8")
    registry = create_default_registry({"default": {"chanmama_import"}})

    output = registry.call("chanmama_import", {"path": path})

    assert output.status == "success"
    assert output.data["source"] == "chanmama"
    assert output.data["detected_entity_type"] == "video"
    assert output.metadata["agent"] == "default"


def test_report_export_skill_reads_report_text(tmp_path):
    path = tmp_path / "trend_report.md"
    path.write_text("# Report\n", encoding="utf-8")
    registry = create_default_registry({"default": {"report_export"}})

    output = registry.call("report_export", {"path": path})

    assert output.status == "success"
    assert output.data["text"] == "# Report\n"
