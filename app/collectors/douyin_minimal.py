from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

DEFAULT_COOKIE_PATH = Path(".profiles") / "douyin" / "default.cookies.json"
DEFAULT_DOUYIN_PROFILE_DIR = Path(".profiles") / "douyin" / "browser"
SEARCH_ENDPOINT_ENV = "DOUYIN_SEARCH_ENDPOINT"
DETAIL_ENDPOINT_ENV = "DOUYIN_DETAIL_ENDPOINT"
HOT_BOARD_ENDPOINT_ENV = "DOUYIN_HOT_BOARD_ENDPOINT"


def load_douyin_cookies(cookie_path: str | Path = DEFAULT_COOKIE_PATH) -> str:
    path = Path(cookie_path)
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8").strip()


def check_douyin_login(cookie_path: str | Path = DEFAULT_COOKIE_PATH) -> dict:
    path = Path(cookie_path)
    if not path.exists():
        return {"status": "auth_required", "reason": "cookies_missing", "cookie_path": str(path)}
    if not path.read_text(encoding="utf-8").strip():
        return {"status": "auth_required", "reason": "cookies_empty", "cookie_path": str(path)}
    return {"status": "ok", "cookie_path": str(path)}


def login_douyin(
    *,
    cookie_path: str | Path = DEFAULT_COOKIE_PATH,
    profile_dir: str | Path = DEFAULT_DOUYIN_PROFILE_DIR,
    login_url: str = "https://www.douyin.com/",
    playwright_factory=None,
    input_func=input,
) -> dict:
    factory = playwright_factory or _sync_playwright
    cookie_file = Path(cookie_path)
    profile = Path(profile_dir)
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    with factory() as playwright:
        context = playwright.chromium.launch_persistent_context(str(profile), headless=False)
        page = context.pages[0] if getattr(context, "pages", []) else context.new_page()
        page.goto(login_url)
        input_func("Scan Douyin QR code in the opened browser, then press Enter...")
        cookies = context.cookies()
        cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        context.close()
    return {"status": "ok", "cookie_path": str(cookie_file), "cookie_count": len(cookies)}


def validate_douyin_live_config(cookie_path: str | Path = DEFAULT_COOKIE_PATH) -> dict:
    login = check_douyin_login(cookie_path)
    endpoints = {
        SEARCH_ENDPOINT_ENV: bool(os.getenv(SEARCH_ENDPOINT_ENV)),
        DETAIL_ENDPOINT_ENV: bool(os.getenv(DETAIL_ENDPOINT_ENV)),
        HOT_BOARD_ENDPOINT_ENV: bool(os.getenv(HOT_BOARD_ENDPOINT_ENV)),
    }
    missing = [name for name, present in endpoints.items() if not present]
    ready = login["status"] == "ok" and not missing
    return {"status": "ready" if ready else "not_ready", "login": login, "endpoints": endpoints, "missing": missing}


def collect_douyin_search(
    keyword: str,
    *,
    limit: int = 20,
    cookie_path: str | Path | None = None,
    raw_items: list[dict] | None = None,
) -> list[dict]:
    if raw_items is None:
        _require_ready_cookie(cookie_path)
        payload = _fetch_json(
            _required_endpoint(SEARCH_ENDPOINT_ENV),
            {"keyword": keyword, "limit": max(1, int(limit or 20))},
            cookie_path or DEFAULT_COOKIE_PATH,
        )
        raw_items = _extract_items(payload, "items", "data", "aweme_list", "results")
    return dedupe_douyin_items(normalize_douyin_item(item) for item in raw_items)[: max(1, int(limit or 20))]


def get_douyin_detail(
    aweme_id: str,
    *,
    cookie_path: str | Path | None = None,
    raw_item: dict | None = None,
) -> dict:
    if raw_item is None:
        _require_ready_cookie(cookie_path)
        payload = _fetch_json(_required_endpoint(DETAIL_ENDPOINT_ENV), {"aweme_id": aweme_id}, cookie_path or DEFAULT_COOKIE_PATH)
        raw_item = _extract_one(payload, "item", "data", "aweme_detail", "detail")
    return normalize_douyin_item({"aweme_id": aweme_id, **raw_item})


def collect_douyin_hot_board(
    *,
    limit: int = 50,
    cookie_path: str | Path | None = None,
    raw_items: list[dict] | None = None,
) -> list[dict]:
    if raw_items is None:
        _require_ready_cookie(cookie_path)
        payload = _fetch_json(_required_endpoint(HOT_BOARD_ENDPOINT_ENV), {"limit": max(1, int(limit or 50))}, cookie_path or DEFAULT_COOKIE_PATH)
        raw_items = _extract_items(payload, "items", "data", "word_list", "hot_list", "results")
    return [normalize_douyin_hot_item(item, index + 1) for index, item in enumerate(raw_items[: max(1, int(limit or 50))])]


def normalize_douyin_content_item(raw: dict, *, content_format: str | None = None, provenance: dict | None = None) -> dict:
    item = normalize_douyin_item(raw)
    images = raw.get("images") or raw.get("image_list") or raw.get("pictures") or []
    if isinstance(images, str):
        images = [images]
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    video_url = raw.get("video_url") or raw.get("play_url") or _first(video, "play_addr", "url")
    format_name = content_format or ("image_text" if images and not video_url else item["type"])
    return {
        "item_id": item["id"],
        "source": "douyin",
        "content_format": format_name,
        "title": item["title"],
        "content": item["body_text"],
        "images": [str(_image_url(image)) for image in images if _image_url(image)],
        "video_url": str(video_url or ""),
        "author": item["author"],
        "publish_time": str(item["created_at"] or ""),
        "metrics": {
            "liked_count": item["liked_count"],
            "collected_count": item["collected_count"],
            "comment_count": item["comment_count"],
        },
        "tags": item["tags"],
        "url": item["url"],
        "provenance": provenance or {"source_type": "endpoint"},
        "raw_record": raw,
    }


def normalize_douyin_image_text_item(raw: dict, *, provenance: dict | None = None) -> dict:
    return normalize_douyin_content_item(raw, content_format="image_text", provenance=provenance)


def douyin_hot_item_to_signal(raw: dict, *, rank: int | None = None, provenance: dict | None = None) -> dict:
    keyword = str(_first(raw, "keyword", "word", "title", "sentence", "hot_word") or "")
    signal_rank = rank or _int_or_none(_first(raw, "rank", "position"))
    signal_id = _first(raw, "id", "sentence_id", "word_id") or keyword or signal_rank or "unknown"
    return {
        "signal_id": f"douyin-hot-{signal_id}",
        "source": "douyin_hot_board",
        "keyword": keyword,
        "topic": _first(raw, "topic", "category") or "",
        "rank": signal_rank,
        "heat_score": _float_or_none(_first(raw, "heat_score", "hot_value", "score")),
        "growth_rate": _float_or_none(_first(raw, "growth_rate", "rise_rate")),
        "related_terms": _terms(raw.get("related_terms") or raw.get("related_words") or raw.get("tags")),
        "snapshot_time": str(_first(raw, "snapshot_time", "created_at") or _now()),
        "raw_record": raw,
        "provenance": provenance or {"source_type": "hot_board"},
    }


def official_keyword_to_signal(raw: dict, *, provenance: dict | None = None) -> dict:
    keyword = str(_first(raw, "keyword", "word", "search_word", "query") or "")
    signal_id = _first(raw, "id", "keyword_id") or keyword or "unknown"
    return {
        "signal_id": f"douyin-keyword-{signal_id}",
        "source": "douyin_official_keyword",
        "keyword": keyword,
        "topic": _first(raw, "topic", "category") or "",
        "rank": _int_or_none(_first(raw, "rank", "position")),
        "heat_score": _float_or_none(_first(raw, "heat_score", "search_index", "index", "score")),
        "growth_rate": _float_or_none(_first(raw, "growth_rate", "mom", "wow")),
        "related_terms": _terms(raw.get("related_terms") or raw.get("related_words")),
        "snapshot_time": str(_first(raw, "snapshot_time", "date") or _now()),
        "raw_record": raw,
        "provenance": provenance or {"source_type": "official_keyword_export"},
    }


def import_douyin_official_keywords(path: str | Path, *, provenance: dict | None = None) -> list[dict]:
    records = _read_records(Path(path))
    base = {"source_type": "official_keyword_export", "path": str(path)}
    if provenance:
        base.update(provenance)
    return [official_keyword_to_signal(record, provenance=base) for record in records]


def normalize_douyin_item(raw: dict) -> dict:
    aweme_id = _first(raw, "aweme_id", "id", "item_id", "video_id")
    desc = _first(raw, "desc", "title", "text", "caption")
    stats = raw.get("statistics") or raw.get("stats") or {}
    author = raw.get("author") or raw.get("user") or {}
    tags = raw.get("tags") or raw.get("hashtags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        "id": str(aweme_id or ""),
        "title": str(desc or ""),
        "body_text": str(_first(raw, "body_text", "description", "desc") or desc or ""),
        "author": str(_first(author, "nickname", "name", "unique_id") or raw.get("author") or ""),
        "liked_count": str(_first(stats, "digg_count", "liked_count", "like_count") or _first(raw, "liked_count", "digg_count", "like_count") or 0),
        "collected_count": str(_first(stats, "collect_count", "collected_count") or _first(raw, "collected_count", "collect_count") or 0),
        "comment_count": str(_first(stats, "comment_count", "comments") or _first(raw, "comment_count", "comments") or 0),
        "created_at": _first(raw, "create_time", "created_at", "publish_time") or "",
        "url": str(raw.get("url") or raw.get("share_url") or _douyin_video_url(aweme_id)),
        "type": str(raw.get("type") or "video"),
        "tags": [str(tag.get("name") if isinstance(tag, dict) else tag) for tag in tags if tag],
        "platform": "douyin",
        "raw": raw,
    }


def normalize_douyin_hot_item(raw: dict, rank: int) -> dict:
    title = _first(raw, "title", "word", "sentence", "hot_word")
    hot_id = _first(raw, "id", "sentence_id", "word_id") or rank
    return {
        "id": f"douyin-hot-{hot_id}",
        "title": str(title or ""),
        "body_text": f"抖音热榜：{title or ''}",
        "liked_count": "0",
        "collected_count": "0",
        "comment_count": "0",
        "created_at": _first(raw, "created_at", "create_time") or "",
        "url": str(raw.get("url") or ""),
        "type": "hot_trend",
        "tags": [],
        "platform": "douyin",
        "raw": raw,
    }


def dedupe_douyin_items(items) -> list[dict]:
    seen = set()
    output = []
    for item in items:
        item_id = item.get("id")
        key = item_id or item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal Douyin collector boundary")
    parser.add_argument("--keyword", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--cookie-path", default=str(DEFAULT_COOKIE_PATH))
    parser.add_argument("--check-login", action="store_true")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hot-board", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(json.dumps(validate_douyin_live_config(args.cookie_path), ensure_ascii=False))
        return 0
    if args.login:
        print(json.dumps(login_douyin(cookie_path=args.cookie_path), ensure_ascii=False))
        return 0
    if args.check_login:
        print(json.dumps(check_douyin_login(args.cookie_path), ensure_ascii=False))
        return 0
    if args.hot_board:
        print(json.dumps(collect_douyin_hot_board(limit=args.limit, cookie_path=args.cookie_path), ensure_ascii=False))
        return 0
    if args.keyword:
        print(json.dumps(collect_douyin_search(args.keyword, limit=args.limit, cookie_path=args.cookie_path), ensure_ascii=False))
        return 0
    raise SystemExit("pass --keyword, --hot-board, or --check-login")


def _require_ready_cookie(cookie_path: str | Path | None) -> None:
    status = check_douyin_login(cookie_path or DEFAULT_COOKIE_PATH)
    if status["status"] != "ok":
        raise RuntimeError(f"Douyin auth required: {status['reason']}")


def _required_endpoint(env_name: str) -> str:
    endpoint = os.getenv(env_name, "")
    if not endpoint:
        raise RuntimeError(f"{env_name} is required for live Douyin collection")
    return endpoint


def _sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required for Douyin login") from exc
    return sync_playwright()


def _fetch_json(endpoint: str, params: dict, cookie_path: str | Path) -> dict:
    query = parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    separator = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{separator}{query}" if query else endpoint
    req = request.Request(url, headers={"Cookie": _cookie_header(load_douyin_cookies(cookie_path)), "User-Agent": "gtChat/1.0"})
    with request.urlopen(req, timeout=20) as response:  # noqa: S310 - user-configured collector endpoint
        return json.loads(response.read().decode("utf-8"))


def _cookie_header(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, list):
        return "; ".join(f"{item.get('name')}={item.get('value')}" for item in data if item.get("name"))
    if isinstance(data, dict):
        return "; ".join(f"{key}={value}" for key, value in data.items())
    return text


def _extract_items(payload: dict, *keys: str) -> list[dict]:
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value, *keys)
            if nested:
                return nested
    return []


def _extract_one(payload: dict, *keys: str) -> dict:
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            return value
    return payload if isinstance(payload, dict) else {}


def _douyin_video_url(aweme_id) -> str:
    return f"https://www.douyin.com/video/{aweme_id}" if aweme_id else ""


def _first(data: dict, *keys: str):
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        if value not in (None, ""):
            return value
    return ""


def _image_url(image) -> str:
    if isinstance(image, str):
        return image
    if isinstance(image, dict):
        return str(_first(image, "url", "uri", "src") or "")
    return ""


def _terms(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [term.strip() for term in value.split(",") if term.strip()]
    if isinstance(value, list):
        return [str(item.get("word") if isinstance(item, dict) else item) for item in value if item]
    return []


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_records(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for key in ("items", "records", "data"):
                if isinstance(data.get(key), list):
                    return [row for row in data[key] if isinstance(row, dict)]
            return [data]
    if suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"unsupported official keyword export: {path.suffix}")


if __name__ == "__main__":
    raise SystemExit(main())
