from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def scan_chanmama_pending(root: str | Path = "watched_imports/chanmama") -> list[dict]:
    base = Path(root)
    pending = base / "pending"
    processed = base / "processed"
    failed = base / "failed"
    pending.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    failed.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(item for item in pending.iterdir() if item.is_file()):
        try:
            record = import_chanmama_file(path)
            shutil.move(str(path), str(_target_path(processed, path)))
        except Exception as exc:
            record = _record(path, "unknown", 0, "failed", str(exc), {"source_type": "chanmama_export", "path": str(path)})
            shutil.move(str(path), str(_target_path(failed, path)))
        records.append(record)
    return records


def import_chanmama_file(path: str | Path) -> dict:
    file_path = Path(path)
    rows = _read_rows(file_path)
    entity_type = _detect_entity_type(rows)
    return _record(
        file_path,
        entity_type,
        len(rows),
        "success",
        "",
        {"source_type": "chanmama_export", "path": str(file_path), "columns": sorted(rows[0].keys()) if rows else []},
    )


def _read_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for key in ("items", "records", "data"):
                if isinstance(data.get(key), list):
                    return [row for row in data[key] if isinstance(row, dict)]
            return [data]
    raise ValueError(f"unsupported chanmama export: {path.suffix}")


def _detect_entity_type(rows: list[dict]) -> str:
    keys = {key.lower() for row in rows[:5] for key in row}
    if keys & {"video_id", "aweme_id", "视频id", "视频标题"}:
        return "video"
    if keys & {"product_id", "商品id", "商品名称"}:
        return "product"
    if keys & {"creator_id", "达人id", "达人昵称"}:
        return "creator"
    if keys & {"live_room_id", "直播间id"}:
        return "live_room"
    if keys & {"brand_id", "品牌id", "品牌名称"}:
        return "brand"
    return "unknown"


def _record(path: Path, entity_type: str, count: int, status: str, error: str, provenance: dict) -> dict:
    return {
        "import_id": str(uuid4()),
        "source": "chanmama",
        "input_file": str(path),
        "file_type": path.suffix.lower().lstrip("."),
        "detected_entity_type": entity_type,
        "record_count": count,
        "status": status,
        "error": error,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
    }


def _target_path(directory: Path, source: Path) -> Path:
    target = directory / source.name
    if not target.exists():
        return target
    return directory / f"{source.stem}-{uuid4().hex[:8]}{source.suffix}"
