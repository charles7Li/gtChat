from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class SkillInput:
    payload: dict[str, Any]


@dataclass(frozen=True)
class SkillContext:
    agent: str = "default"
    run_id: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillOutput:
    status: str
    data: Any = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    adapter: "SkillAdapter"


class SkillAdapter(Protocol):
    def invoke(self, skill_input: SkillInput, context: SkillContext) -> SkillOutput:
        ...
