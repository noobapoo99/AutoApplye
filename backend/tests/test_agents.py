import pytest
import pytest_asyncio

@pytest.mark.asyncio
async def test_cosine_similarity():
    from agents.resume_agent import cosine_similarity
    assert cosine_similarity([1,0,0], [1,0,0]) == pytest.approx(1.0)
    assert cosine_similarity([1,0,0], [0,1,0]) == pytest.approx(0.0)
    assert cosine_similarity([1,0,0], [0.5,0.866,0]) == pytest.approx(0.5, abs=0.01)
    assert cosine_similarity([0,0,0], [1,0,0]) == 0.0

@pytest.mark.asyncio
async def test_make_cache_key_deterministic():
    from core.redis_client import make_cache_key
    key1 = make_cache_key("autoapply", "test", "123")
    key2 = make_cache_key("autoapply", "test", "123")
    key3 = make_cache_key("autoapply", "test", "456")
    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 32

@pytest.mark.asyncio
async def test_queue_names_all_exist():
    from core.queue import QUEUES
    required = ["JD_RAW","JD_ENRICHED","JD_READY","JD_FLAGGED",
                "DLQ_EMAIL","DLQ_APPLICATION","DLQ_RESEARCH"]
    for name in required:
        assert name in QUEUES, f"Missing queue: {name}"

@pytest.mark.asyncio
async def test_hallucination_criteria_exactly_six():
    from core.llm import HallucinationScorer
    assert len(HallucinationScorer.CRITERIA) == 6
    keys = [c[0] for c in HallucinationScorer.CRITERIA]
    assert "company_name_match" in keys
    assert "score_range_valid" in keys

@pytest.mark.asyncio
async def test_agent_factory_all_registered():
    import agents.scout_agent, agents.research_agent, agents.resume_agent
    import agents.application_agent, agents.gmail_agent
    from agents.base import AgentFactory
    for name in ["scout","research","resume","application","gmail"]:
        assert name in AgentFactory.available(), f"Agent not registered: {name}"

@pytest.mark.asyncio
async def test_agent_factory_creates_correct_type():
    import agents.scout_agent, agents.research_agent
    from agents.base import AgentFactory
    from agents.scout_agent import JDScoutAgent
    from agents.research_agent import CompanyResearchAgent
    scout = AgentFactory.create("scout", search_query="test")
    assert isinstance(scout, JDScoutAgent)
    research = AgentFactory.create("research")
    assert isinstance(research, CompanyResearchAgent)

@pytest.mark.asyncio
async def test_resume_strategies_all_present():
    from agents.base import RESUME_STRATEGIES
    expected = ["keyword_injection","summary_rewrite","skills_reorder"]
    for name in expected:
        assert name in RESUME_STRATEGIES, f"Missing strategy: {name}"
        assert hasattr(RESUME_STRATEGIES[name], "strategy_name")
        assert RESUME_STRATEGIES[name].strategy_name == name

@pytest.mark.asyncio
async def test_application_status_values():
    from db.models import ApplicationStatus
    expected = {
        "discovered","researching","resume_editing","flagged_human",
        "applying","applied","email_received","interview","rejected","withdrawn"
    }
    actual = {s.value for s in ApplicationStatus}
    assert actual == expected

@pytest.mark.asyncio
async def test_base_agent_has_required_methods():
    from agents.base import BaseAgent
    import inspect
    assert hasattr(BaseAgent, "run")
    assert inspect.iscoroutinefunction(BaseAgent.run)
    assert hasattr(BaseAgent, "process")
    assert hasattr(BaseAgent, "emit_result")
    assert hasattr(BaseAgent, "validate_input")
