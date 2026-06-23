from __future__ import annotations

import json
from pathlib import Path


DEFAULT_SEARCH_DIR = Path.home() / ".xiaohongshu-cli" / "search_results"


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_latest_search_results(search_dir: str | Path = DEFAULT_SEARCH_DIR) -> list[dict]:
    directory = Path(search_dir)
    if not directory.exists():
        return []
    files = sorted(directory.glob("search_*_deep_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return []
    data = load_json(files[0])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "notes", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []
