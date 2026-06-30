from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass(frozen=True)
class HotspotRule:
    min_heat_score: float | None = None
    min_growth_rate: float | None = None
    min_rank: int | None = None
    min_engagement: int | None = None
    required_sources: tuple[str, ...] = ()


def evaluate_hotspot_signal(signal: dict, rule: HotspotRule) -> dict:
    reasons = []
    if rule.required_sources and signal.get("source") not in rule.required_sources:
        return _result(False, signal, rule, [f"source {signal.get('source')} not allowed"])
    if rule.min_heat_score is not None and _float(signal.get("heat_score")) >= rule.min_heat_score:
        reasons.append(f"heat_score >= {rule.min_heat_score}")
    if rule.min_growth_rate is not None and _float(signal.get("growth_rate")) >= rule.min_growth_rate:
        reasons.append(f"growth_rate >= {rule.min_growth_rate}")
    if rule.min_rank is not None and 0 < _int(signal.get("rank")) <= rule.min_rank:
        reasons.append(f"rank <= {rule.min_rank}")
    if rule.min_engagement is not None and _int(signal.get("total_engagement")) >= rule.min_engagement:
        reasons.append(f"engagement >= {rule.min_engagement}")
    return _result(bool(reasons), signal, rule, reasons or ["no threshold matched"])


def build_hotspot_analysis_payload(signal: dict, evaluation: dict) -> dict:
    return {
        "route": "hotspot_auto_analysis_path",
        "keyword": signal.get("keyword", ""),
        "topic": signal.get("topic") or signal.get("keyword", ""),
        "source": signal.get("source", ""),
        "hotspot_signal": signal,
        "trigger_reason": evaluation.get("reasons", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _result(triggered: bool, signal: dict, rule: HotspotRule, reasons: list[str]) -> dict:
    return {
        "triggered": triggered,
        "signal_id": signal.get("signal_id", ""),
        "keyword": signal.get("keyword", ""),
        "rule": asdict(rule),
        "reasons": reasons,
    }


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
