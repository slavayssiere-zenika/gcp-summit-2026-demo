import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from agent import (
    list_users, get_user, create_user, update_user, delete_user, search_users, toggle_user_status, get_user_stats, health_check_users,
    list_items, get_item, create_item, update_item, delete_item, get_item_with_user, search_items, get_items_by_user, get_item_stats, health_check_items,
    list_competencies, get_competency, create_competency, delete_competency, assign_competency_to_user, remove_competency_from_user, list_user_competencies,
    analyze_cv, search_best_candidates, recalculate_competencies_tree,
    loki_query, loki_label_names, loki_label_values, loki_metric_aggregator,
    run_agent_query, format_mcp_result
)

def test_format_mcp_result():
    assert format_mcp_result([], "test") == {"result": "No result"}
    
    # Array mapping
    res = format_mcp_result([{"text": '[{"id": 1}]'}], "test")
    assert "dataType" in json.loads(res["result"])
    assert "items" in json.loads(res["result"])
    
    # Text mapping fallback
    res = format_mcp_result([{"text": "non_json"}], "test")
    assert res["result"] == "non_json"

@pytest.fixture
def mock_users_mcp(mocker):
    m = AsyncMock()
    m.call_tool.return_value = [{"text": '{"result": "success"}'}]
    mocker.patch("agent.get_users_mcp", return_value=m)
    return m

@pytest.mark.asyncio
async def test_users_tools(mock_users_mcp):
    assert "success" in (await list_users(0, 10))["result"]
    assert "success" in (await get_user(1))["result"]
    assert "success" in (await create_user("u", "e@e.com", "Name"))["result"]
    assert "success" in (await update_user(1, "u", "e", "n", True))["result"]
    assert "success" in (await delete_user(1))["result"]
    assert "success" in (await search_users("q"))["result"]
    assert "success" in (await toggle_user_status(1, False))["result"]
    assert "success" in (await get_user_stats())["result"]
    assert "success" in (await health_check_users())["result"]

@pytest.fixture
def mock_items_mcp(mocker):
    m = AsyncMock()
    m.call_tool.return_value = [{"text": '{"result": "success"}'}]
    mocker.patch("agent.get_items_mcp", return_value=m)
    return m

@pytest.mark.asyncio
async def test_items_tools(mock_items_mcp):
    assert "success" in (await list_items(0, 10))["result"]
    assert "success" in (await get_item(1))["result"]
    assert "success" in (await create_item("i", 1, "desc"))["result"]
    assert "success" in (await update_item(1, "i", "d"))["result"]
    assert "success" in (await delete_item(1))["result"]
    assert "success" in (await get_item_with_user(1))["result"]
    assert "success" in (await search_items("q"))["result"]
    assert "success" in (await get_items_by_user(1))["result"]
    assert "success" in (await get_item_stats())["result"]
    assert "success" in (await health_check_items())["result"]

@pytest.fixture
def mock_competencies_mcp(mocker):
    m = AsyncMock()
    m.call_tool.return_value = [{"text": '{"result": "success"}'}]
    mocker.patch("agent.get_competencies_mcp", return_value=m)
    return m

@pytest.mark.asyncio
async def test_competencies_tools(mock_competencies_mcp):
    assert "success" in (await list_competencies(0, 10))["result"]
    assert "success" in (await get_competency(1))["result"]
    assert "success" in (await create_competency("c", "d", 2))["result"]
    assert "success" in (await delete_competency(1))["result"]
    assert "success" in (await assign_competency_to_user(1, 1))["result"]
    assert "success" in (await remove_competency_from_user(1, 1))["result"]
    assert "success" in (await list_user_competencies(1))["result"]

@pytest.fixture
def mock_cv_mcp(mocker):
    m = AsyncMock()
    m.call_tool.return_value = [{"text": '{"result": "success"}'}]
    mocker.patch("agent.get_cv_mcp", return_value=m)
    return m

@pytest.mark.asyncio
async def test_cv_tools(mock_cv_mcp):
    assert "success" in (await analyze_cv("url"))["result"]
    assert "success" in (await search_best_candidates("q", 5))["result"]
    assert "success" in (await recalculate_competencies_tree())["result"]

@pytest.fixture
def mock_loki_mcp(mocker):
    m = AsyncMock()
    m.call_tool.return_value = [{"text": '{"result": "success"}'}]
    mocker.patch("agent.get_loki_mcp", return_value=m)
    return m

@pytest.mark.asyncio
async def test_loki_tools(mock_loki_mcp):
    assert "success" in (await loki_query("q", "1h", "now", 10))["result"]
    assert "success" in (await loki_label_names())["result"]
    assert "success" in (await loki_label_values("container"))["result"]

@pytest.mark.asyncio
async def test_loki_metric_aggregator(mocker):
    mock_httpx = mocker.patch("httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"status": "success"}
    client_instance.get.return_value = mock_resp
    
    result = await loki_metric_aggregator("sum()")
    assert "success" in result["result"]


class MockContent:
    def __init__(self, parts):
        self.parts = parts
        self.role = "model"

class MockUsage:
    def __init__(self, prompt, cand):
        self.prompt_token_count = prompt
        self.candidates_token_count = cand

class MockEvent:
    def __init__(self, author, parts, calls=None, responses=None, actions=None, usage=None):
        self.author = author
        self.content = MockContent(parts)
        self.actions = actions or []
        self._calls = calls or []
        self._responses = responses or []
        self.usage_metadata = usage or MockUsage(10, 20)

    def get_function_calls(self):
        return self._calls

    def get_function_responses(self):
        return self._responses

class MockPart:
    def __init__(self, text=None, tool_call=None):
        self.text = text
        self.tool_call = tool_call
        self.function_call = None
        self.thought = None
        self.function_response = None

class MockToolCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

@pytest.mark.asyncio
async def test_run_agent_query_logic(mocker):
    # Mocking ADK dependencies
    mock_agent = MagicMock()
    mock_agent.model = "gemini-test"
    
    # Mock session
    mock_session_service = AsyncMock()
    mock_session_service.get_session.return_value = MagicMock()
    
    class MockRunner:
        def __init__(self, *args, **kwargs):
            pass
        async def run_async(self, *args, **kwargs):
            mock_event = MockEvent("assistant", [MockPart(text="Hello result")])
            yield mock_event
            
            tool_event = MockEvent(
                "tool",
                [
                    MockPart(tool_call=MockToolCall("test_tool", {"a": 1})),
                    MockPart(text='{"result": "{\\"tool_data\\": 1}"}')
                ]
            )
            yield tool_event
            
    with patch("agent.get_session_service", return_value=mock_session_service), \
         patch("agent.create_agent", return_value=mock_agent), \
         patch("google.adk.runners.Runner", new=MockRunner):
        
        result = await run_agent_query("hello")
        assert result["response"].startswith("Hello result")
        assert result["source"] == "adk_agent"
