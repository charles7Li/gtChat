from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checks: dict[str, dict[str, object]] = {}

    checks["python"] = {"ok": sys.version_info >= (3, 13), "value": sys.version.split()[0]}
    checks["playwright"] = {"ok": importlib.util.find_spec("playwright") is not None}
    browser_candidates = [
        os.getenv("DOUYIN_BROWSER_EXECUTABLE", ""),
        shutil.which("chrome") or "",
        shutil.which("msedge") or "",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome = next((candidate for candidate in browser_candidates if candidate and Path(candidate).is_file()), "")
    checks["browser"] = {"ok": bool(chrome), "value": chrome or "not found"}
    checks["pipeline_defs"] = {"ok": (root / "pipeline_defs").is_dir()}
    checks["profiles"] = {"ok": (root / ".profiles").is_dir(), "value": str(root / ".profiles")}
    checks["outputs"] = {"ok": (root / "outputs").is_dir(), "value": str(root / "outputs")}
    checks["auth"] = {
        "ok": any((root / ".profiles").glob("**/*.cookies.json")) if (root / ".profiles").is_dir() else False,
        "value": "cookie profile found" if (root / ".profiles").is_dir() and any((root / ".profiles").glob("**/*.cookies.json")) else "no saved cookies",
    }

    print(json.dumps({"ok": all(item["ok"] for item in checks.values()), "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
