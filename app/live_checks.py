from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.collectors.douyin_minimal import collect_douyin_hot_board, collect_douyin_search, get_douyin_detail, validate_douyin_live_config
from app.notifications import send_notification, validate_notification_config


def run_live_checks(
    *,
    allow_live: bool = False,
    keyword: str = "pet",
    limit: int = 1,
    cookie_path: str | Path = ".profiles/douyin/default.cookies.json",
) -> dict:
    checks = {
        "douyin": validate_douyin_live_config(cookie_path),
        "notification": validate_notification_config(),
    }
    result = {"mode": "live" if allow_live else "dry_run", "checks": checks, "live_results": {}}
    if not allow_live:
        return result

    if checks["douyin"]["status"] == "ready":
        search_items = collect_douyin_search(keyword, limit=limit, cookie_path=cookie_path)
        result["live_results"]["douyin_search"] = {"status": "ok", "count": len(search_items)}
        first_id = next((item.get("id") for item in search_items if item.get("id")), "")
        if first_id:
            result["live_results"]["douyin_detail"] = {"status": "ok", "id": get_douyin_detail(first_id, cookie_path=cookie_path).get("id", "")}
        else:
            result["live_results"]["douyin_detail"] = {"status": "skipped", "reason": "search_returned_no_id"}
        result["live_results"]["douyin_hot_board"] = {"status": "ok", "count": len(collect_douyin_hot_board(limit=limit, cookie_path=cookie_path))}
    else:
        result["live_results"]["douyin"] = {"status": "skipped", "reason": "not_ready"}

    if checks["notification"]["status"] == "ready":
        result["live_results"]["notification"] = send_notification({"messages": ["Mochi Scout live check"], "status": "live_check"})
    else:
        result["live_results"]["notification"] = {"status": "skipped", "reason": "not_ready"}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Mochi Scout live integration checks. Defaults to dry-run.")
    parser.add_argument("--allow-live", action="store_true", help="Actually call configured Douyin endpoints and webhook.")
    parser.add_argument("--keyword", default="pet")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--cookie-path", default=".profiles/douyin/default.cookies.json")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_live_checks(allow_live=args.allow_live, keyword=args.keyword, limit=args.limit, cookie_path=args.cookie_path),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
