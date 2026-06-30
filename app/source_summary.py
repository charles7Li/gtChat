from __future__ import annotations


def build_source_summary(state: dict) -> dict:
    sources = []
    collector = state.get("collector_result") or {}
    if collector:
        sources.append(
            {
                "source": collector.get("source", ""),
                "source_type": "collector",
                "record_count": collector.get("count", 0),
                "provenance": collector,
            }
        )
    commercial = state.get("commercial_import_summary") or {}
    if commercial:
        sources.append(
            {
                "source": commercial.get("source", ""),
                "source_type": "commercial_import",
                "record_count": commercial.get("record_count", 0),
                "provenance": commercial.get("provenance", []),
            }
        )
    raw_items = state.get("raw_items") or []
    provenance_items = [item.get("provenance") for item in raw_items if isinstance(item, dict) and item.get("provenance")]
    if provenance_items:
        sources.append(
            {
                "source": _first_value(raw_items, "platform") or "unknown",
                "source_type": "raw_items",
                "record_count": len(raw_items),
                "provenance": provenance_items[:5],
            }
        )
    return {"sources": sources, "source_count": len(sources)}


def _first_value(items: list[dict], key: str) -> str:
    for item in items:
        value = item.get(key) if isinstance(item, dict) else None
        if value:
            return str(value)
    return ""
