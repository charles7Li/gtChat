from __future__ import annotations

from app.utils import parse_count, parse_timestamp_ms


def clean_items(raw_items: list[dict]) -> list[dict]:
    return clean_items_with_metadata(raw_items)["clean_items"]


def clean_items_with_metadata(raw_items: list[dict]) -> dict:
    cleaned: list[dict] = []
    dropped: list[dict] = []
    seen_keys: set[str] = set()
    missing_metrics_count = 0

    for index, raw in enumerate(raw_items):
        title = raw.get("title") or raw.get("note_title") or ""
        body = raw.get("body_text") or raw.get("desc") or raw.get("content") or ""
        raw_id = str(raw.get("id") or raw.get("note_id") or "")

        if not title and not body:
            dropped.append(_drop_record(index, raw, "empty_content"))
            continue

        duplicate_key = _duplicate_key(raw, title)
        if duplicate_key in seen_keys:
            dropped.append(_drop_record(index, raw, "duplicate"))
            continue
        seen_keys.add(duplicate_key)

        liked = parse_count(raw.get("liked_count") or raw.get("likes"))
        collected = parse_count(raw.get("collected_count") or raw.get("collects"))
        comments = parse_count(raw.get("comment_count") or raw.get("comments"))
        if liked == 0 and collected == 0 and comments == 0:
            missing_metrics_count += 1

        cleaned.append(
            {
                "id": raw_id or str(raw.get("url") or raw.get("link") or f"item-{index}"),
                "title": title,
                "body_text": body,
                "tags": _normalize_tags(raw.get("tags") or raw.get("tag_list") or []),
                "metrics": {
                    "liked_count": liked,
                    "collected_count": collected,
                    "comment_count": comments,
                    "total_engagement": liked + collected + comments,
                },
                "content_type": _normalize_content_type(raw.get("content_type") or raw.get("type")),
                "image_count": parse_count(raw.get("image_count") or len(raw.get("images") or [])),
                "author": raw.get("author") or raw.get("nickname") or "",
                "url": raw.get("url") or raw.get("link") or "",
                "detail_url": raw.get("detail_url") or raw.get("url") or raw.get("link") or "",
                "detail_status": raw.get("detail_status") or ("success" if body else "list_only"),
                "created_at": parse_timestamp_ms(raw.get("created_at") or raw.get("time") or raw.get("timestamp")),
                "created_at_raw": raw.get("created_at") or raw.get("time") or raw.get("timestamp"),
            }
        )

    data_quality = _quality_summary(raw_items, cleaned, dropped, missing_metrics_count)
    return {
        "clean_items": cleaned,
        "dropped_items": dropped,
        "data_quality": data_quality,
    }


def _duplicate_key(raw: dict, title: str) -> str:
    if raw.get("id") or raw.get("note_id"):
        return "id:" + str(raw.get("id") or raw.get("note_id"))
    if raw.get("url") or raw.get("link"):
        return "url:" + str(raw.get("url") or raw.get("link"))
    author = raw.get("author") or raw.get("nickname") or ""
    return f"title_author:{title}|{author}"


def _drop_record(index: int, raw: dict, reason: str) -> dict:
    return {
        "index": index,
        "reason": reason,
        "id": str(raw.get("id") or raw.get("note_id") or ""),
        "title": raw.get("title") or raw.get("note_title") or "",
    }


def _normalize_tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = [item for item in tags.replace("，", ",").split(",")]
    normalized = []
    for tag in tags or []:
        text = str(tag).strip().lstrip("#")
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_content_type(content_type) -> str:
    text = str(content_type or "").lower()
    if "video" in text or "视频" in text:
        return "video_note"
    if "image" in text or "图" in text:
        return "image_note"
    return "image_note"


def _quality_summary(
    raw_items: list[dict],
    cleaned: list[dict],
    dropped: list[dict],
    missing_metrics_count: int,
) -> dict:
    dropped_empty = sum(1 for item in dropped if item["reason"] == "empty_content")
    dropped_duplicate = sum(1 for item in dropped if item["reason"] == "duplicate")
    total_raw = len(raw_items)
    total_clean = len(cleaned)
    if total_raw == 0:
        score = 0
    else:
        clean_ratio = total_clean / total_raw
        metric_ratio = 1 - (missing_metrics_count / max(total_clean, 1))
        score = round(max(0, min(100, clean_ratio * 70 + metric_ratio * 30)))

    return {
        "total_raw": total_raw,
        "total_clean": total_clean,
        "dropped_empty": dropped_empty,
        "dropped_duplicate": dropped_duplicate,
        "missing_metrics_count": missing_metrics_count,
        "quality_score": score,
    }
