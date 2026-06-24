from __future__ import annotations

from app.workflow.state import WorkflowState


def build_evidence_pack(state: WorkflowState, limit: int = 20) -> dict:
    clean_items = state.get("clean_items", [])
    top_items = sorted(
        clean_items,
        key=lambda item: item.get("metrics", {}).get("total_engagement", 0),
        reverse=True,
    )[:limit]
    trend = state.get("trend_analysis") or {}

    return {
        "run_id": state.get("run_id"),
        "keyword": state.get("keyword") or (state.get("plan") or {}).get("keyword", "宠物"),
        "item_count": len(clean_items),
        "top_items": [_summarize_item(item) for item in top_items],
        "topic_candidates": trend.get("top_topics", []),
        "data_quality": state.get("data_quality", {}),
    }


def _summarize_item(item: dict) -> dict:
    body = item.get("body_text", "")
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "body_excerpt": body[:500],
        "tags": item.get("tags", []),
        "metrics": item.get("metrics", {}),
        "content_type": item.get("content_type", "unknown"),
    }
