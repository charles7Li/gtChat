from __future__ import annotations


class VerifierSubAgent:
    def run(self, analysis: dict, evidence: dict) -> dict:
        clean_count = int(evidence.get("clean_count") or evidence.get("item_count") or 0)
        quality_score = int(evidence.get("quality_score") or (evidence.get("data_quality") or {}).get("quality_score") or 0)
        topics = analysis.get("top_topics") or []
        if clean_count >= 20 and quality_score >= 60 and topics:
            decision = "proceed"
            reason = "evidence is sufficient"
        elif clean_count >= 10 and topics:
            decision = "limited_report"
            reason = "evidence is usable but thin"
        else:
            decision = "needs_more_evidence"
            reason = "not enough clean samples"
        return {
            "decision": decision,
            "reason": reason,
            "clean_count": clean_count,
            "quality_score": quality_score,
            "topic_count": len(topics),
        }
