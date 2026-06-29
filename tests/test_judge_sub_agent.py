from app.agents import JudgeSubAgent


def test_judge_sub_agent_accepts_strong_signal():
    result = JudgeSubAgent().run({"signal_score": 82, "new_item_count": 3, "engagement_growth": 0.2})

    assert result["decision"] == "accept"


def test_judge_sub_agent_watches_medium_signal():
    result = JudgeSubAgent().run({"signal_score": 45, "new_item_count": 2, "engagement_growth": 0.1})

    assert result["decision"] == "watch"


def test_judge_sub_agent_rejects_weak_signal():
    result = JudgeSubAgent().run({"signal_score": 10, "new_item_count": 0, "engagement_growth": 0.0})

    assert result["decision"] == "reject"
