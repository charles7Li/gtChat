from app.agents import ResearchPlannerSubAgent, SearchStrategySubAgent, VerifierSubAgent


def test_research_planner_skips_non_accept_decision():
    result = ResearchPlannerSubAgent().run({"decision": "watch", "keyword": "pet"})

    assert result["status"] == "skipped"
    assert result["questions"] == []


def test_research_planner_and_search_strategy_create_limited_queries():
    plan = ResearchPlannerSubAgent().run({"decision": "accept"}, {"keyword": "pet"})
    strategy = SearchStrategySubAgent().run(plan, {"suffixes": ["trend", "mistakes", "setup", "extra"]})

    assert plan["status"] == "planned"
    assert len(strategy["queries"]) == 3
    assert strategy["queries"][0]["keyword"] == "pettrend"


def test_verifier_routes_evidence_states():
    verifier = VerifierSubAgent()

    assert verifier.run({"top_topics": ["pet"]}, {"clean_count": 25, "quality_score": 80})["decision"] == "proceed"
    assert verifier.run({"top_topics": ["pet"]}, {"clean_count": 12, "quality_score": 40})["decision"] == "limited_report"
    assert verifier.run({"top_topics": []}, {"clean_count": 2, "quality_score": 90})["decision"] == "needs_more_evidence"
