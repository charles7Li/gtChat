from __future__ import annotations

from pathlib import Path

from app.collectors.douyin_minimal import import_douyin_official_keywords
from app.data_sources.chanmama import scan_chanmama_pending


def run_data_source_import(source: str, *, path: str | Path | None = None) -> dict:
    if source == "chanmama":
        records = scan_chanmama_pending(path or "watched_imports/chanmama")
        return _summary(source, records)
    if source == "douyin_official_keyword":
        if path is None:
            raise ValueError("path is required for douyin_official_keyword")
        records = import_douyin_official_keywords(path)
        return _summary(source, records)
    raise ValueError(f"unsupported data source: {source}")


def _summary(source: str, records: list[dict]) -> dict:
    return {
        "source": source,
        "record_count": len(records),
        "records": records,
        "provenance": [record.get("provenance", {}) for record in records],
    }
