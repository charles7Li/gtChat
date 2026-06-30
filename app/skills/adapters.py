from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Callable

from app.skills.base import SkillContext, SkillInput, SkillOutput


class LocalFunctionAdapter:
    def __init__(self, func: Callable[..., object]) -> None:
        self.func = func

    def invoke(self, skill_input: SkillInput, context: SkillContext) -> SkillOutput:
        started = perf_counter()
        try:
            data = self.func(**skill_input.payload)
            return SkillOutput("success", data=data, metadata=_metadata(started, context))
        except Exception as exc:
            return SkillOutput("failed", error=str(exc), metadata=_metadata(started, context))


class FileImportAdapter:
    def __init__(self, importer: Callable[..., object]) -> None:
        self.importer = importer

    def invoke(self, skill_input: SkillInput, context: SkillContext) -> SkillOutput:
        payload = dict(skill_input.payload)
        path = payload.get("path")
        if not path:
            return SkillOutput("failed", error="path is required")
        payload["path"] = Path(path)
        return LocalFunctionAdapter(self.importer).invoke(SkillInput(payload), context)


def export_report_file(path: str | Path) -> dict:
    report_path = Path(path)
    return {"path": str(report_path), "exists": report_path.exists(), "text": report_path.read_text(encoding="utf-8") if report_path.exists() else ""}


def _metadata(started: float, context: SkillContext) -> dict:
    return {"duration_ms": round((perf_counter() - started) * 1000), "agent": context.agent, "run_id": context.run_id}
