from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_MANIFEST_DIR = Path("pipeline_defs")


@dataclass(frozen=True)
class RouteStage:
    name: str
    required_inputs: list[str]
    produces: list[str]
    quality_gates: list[str]


@dataclass(frozen=True)
class RouteManifest:
    name: str
    description: str
    allow_live_collect: bool
    writes_memory: bool
    external_services: list[str]
    stages: list[RouteStage]

    @property
    def stage_names(self) -> list[str]:
        return [stage.name for stage in self.stages]


def load_route_manifest(path: str | Path) -> RouteManifest:
    data = _parse_manifest(Path(path))
    return RouteManifest(
        name=str(data["name"]),
        description=str(data.get("description", "")),
        allow_live_collect=bool(data.get("allow_live_collect")),
        writes_memory=bool(data.get("writes_memory")),
        external_services=list(data.get("external_services", [])),
        stages=[
            RouteStage(
                name=str(stage["name"]),
                required_inputs=list(stage.get("required_inputs", [])),
                produces=list(stage.get("produces", [])),
                quality_gates=list(stage.get("quality_gates", [])),
            )
            for stage in data.get("stages", [])
        ],
    )


def load_route_manifests(directory: str | Path = DEFAULT_MANIFEST_DIR) -> dict[str, RouteManifest]:
    manifests = [load_route_manifest(path) for path in sorted(Path(directory).glob("*.yaml"))]
    return {manifest.name: manifest for manifest in manifests}


def _parse_manifest(path: Path) -> dict:
    data: dict = {}
    stages: list[dict] = []
    current_stage: dict | None = None
    current_list_key: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "stages:":
            data["stages"] = stages
            current_list_key = None
            continue

        if line.startswith("  - name:"):
            current_stage = {"name": _parse_scalar(line.split(":", 1)[1].strip())}
            stages.append(current_stage)
            current_list_key = None
            continue

        if line.startswith("      - ") and current_stage is not None and current_list_key:
            current_stage[current_list_key].append(_parse_scalar(stripped[2:].strip()))
            continue

        if line.startswith("    ") and current_stage is not None:
            key, value = stripped.split(":", 1)
            value = value.strip()
            if value:
                current_stage[key] = _parse_scalar(value)
                current_list_key = None
            else:
                current_stage[key] = []
                current_list_key = key
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            data[key] = _parse_scalar(value.strip())
            current_list_key = None

    data.setdefault("stages", stages)
    return data


def _parse_scalar(value: str):
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [item.strip().strip('"') for item in inner.split(",")]
    return value.strip('"')
