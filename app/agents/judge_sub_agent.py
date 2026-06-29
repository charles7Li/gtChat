from __future__ import annotations


class JudgeSubAgent:
    def run(self, signal: dict, snapshots: list[dict] | None = None) -> dict:
        score = int(signal.get("signal_score") or 0)
        new_items = int(signal.get("new_item_count") or 0)
        growth = float(signal.get("engagement_growth") or 0)
        if score >= 75 or new_items >= 5 or growth >= 1.0:
            decision = "accept"
            reason = "signal is strong enough for research"
        elif score >= 40 or new_items >= 2 or growth >= 0.3:
            decision = "watch"
            reason = "signal is plausible but needs another tick"
        else:
            decision = "reject"
            reason = "signal is too weak"
        return {
            "decision": decision,
            "reason": reason,
            "signal_score": score,
            "new_item_count": new_items,
            "engagement_growth": growth,
            "snapshot_count": len(snapshots or []),
        }
