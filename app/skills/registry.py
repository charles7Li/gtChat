from __future__ import annotations

from pathlib import Path

from app.data_sources import import_chanmama_file
from app.skills.adapters import FileImportAdapter, LocalFunctionAdapter, export_report_file
from app.skills.base import Skill, SkillContext, SkillInput, SkillOutput
from app.video import analyze_local_video


class SkillRegistry:
    def __init__(self, allowed_skills: dict[str, set[str]] | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self.allowed_skills = allowed_skills or {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def list_skills(self) -> list[str]:
        return sorted(self._skills)

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"unknown skill: {name}")
        return self._skills[name]

    def call(self, name: str, payload: dict, *, context: SkillContext | None = None) -> SkillOutput:
        ctx = context or SkillContext()
        if not self.is_allowed(ctx.agent, name):
            output = SkillOutput("failed", error=f"agent '{ctx.agent}' is not allowed to call skill '{name}'")
        else:
            output = self.get(name).adapter.invoke(SkillInput(payload), ctx)
        if isinstance(ctx.trace, dict):
            ctx.trace.setdefault("skill_timings", []).append({"skill": name, "status": output.status, **output.metadata})
        return output

    def is_allowed(self, agent: str, skill_name: str) -> bool:
        allowed = self.allowed_skills.get(agent) or self.allowed_skills.get("*")
        return allowed is None or skill_name in allowed


def create_default_registry(allowed_skills: dict[str, set[str]] | None = None) -> SkillRegistry:
    registry = SkillRegistry(allowed_skills)
    registry.register(Skill("chanmama_import", "Import one ChanMama CSV/JSON export.", FileImportAdapter(import_chanmama_file)))
    registry.register(Skill("local_video_analyze", "Analyze a local video file.", LocalFunctionAdapter(analyze_local_video)))
    registry.register(Skill("report_export", "Read a generated report file.", FileImportAdapter(export_report_file)))
    return registry


def load_allowed_skills(path: str | Path = "config/agent_skills.yaml") -> dict[str, set[str]]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    allowed: dict[str, set[str]] = {}
    current_agent = ""
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current_agent = stripped[:-1]
            allowed[current_agent] = set()
            continue
        if current_agent and stripped.startswith("- "):
            allowed[current_agent].add(stripped[2:].strip())
    return allowed
