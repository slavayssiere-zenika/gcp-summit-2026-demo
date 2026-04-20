"""Tests for agent_commons.mcp_proxy module."""

import asyncio
import inspect
import pytest


class _FakeClient:
    """Minimal MCPHttpClient stub."""

    def __init__(self):
        self.url = "http://fake-mcp:8000"
        self.last_call: tuple | None = None

    async def call_tool(self, tool_name: str, arguments: dict):
        self.last_call = (tool_name, arguments)
        return [{"type": "text", "text": "ok"}]


def _make_tool_def(name: str, description: str = "A tool", properties: dict | None = None, required: list | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "score": {"type": "number"},
                "active": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": required or ["query"],
        },
    }


from agent_commons.mcp_proxy import create_mcp_tool_proxy, get_cached_tools, NON_BUSINESS_TOOLS


class TestCreateMcpToolProxy:
    def test_name_is_set(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool"))
        assert proxy.__name__ == "my_tool"

    def test_doc_is_set(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool", description="Does stuff"))
        assert proxy.__doc__ == "Does stuff"

    def test_signature_has_required_param_without_default(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("search", required=["query"]))
        sig = inspect.signature(proxy)
        assert sig.parameters["query"].default is inspect.Parameter.empty

    def test_signature_has_optional_param_with_none_default(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("search", required=["query"]))
        sig = inspect.signature(proxy)
        assert sig.parameters["limit"].default is None

    def test_type_mapping_string(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        assert sig.parameters["query"].annotation is str

    def test_type_mapping_integer(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        assert sig.parameters["limit"].annotation is int

    def test_type_mapping_float(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        assert sig.parameters["score"].annotation is float

    def test_type_mapping_boolean(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        assert sig.parameters["active"].annotation is bool

    def test_type_mapping_array_is_object_not_list(self):
        """Arrays MUST map to object, not list — Gemini rejects missing 'items'."""
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        assert sig.parameters["tags"].annotation is object

    def test_none_is_instance_of_annotation_for_array_param(self):
        """Optional array params must use `object` annotation so isinstance(None, object) is True.
        This is critical — ADK validates optional defaults with isinstance()."""
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        sig = inspect.signature(proxy)
        # `tags` is an array type — must map to `object`, not `list`
        ann = sig.parameters["tags"].annotation
        assert ann is object
        assert isinstance(None, ann)  # must not raise TypeError

    def test_proxy_calls_client(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool"))
        result = asyncio.get_event_loop().run_until_complete(proxy(query="test"))
        assert client.last_call == ("my_tool", {"query": "test"})
        assert result == [{"type": "text", "text": "ok"}]


class TestGetCachedTools:
    def _make_clients(self):
        client = _FakeClient()
        # Inject a fake list_tools method
        async def list_tools():
            return [
                _make_tool_def("search_users"),
                _make_tool_def("health_check"),  # should be filtered
                _make_tool_def("search_users"),  # duplicate — should be deduplicated
            ]
        client.list_tools = list_tools
        return client

    def test_deduplication_and_filtering(self):
        client = self._make_clients()
        cache: dict = {}
        tools = asyncio.get_event_loop().run_until_complete(
            get_cached_tools([("svc", client)], "[TEST]", ttl=300, _cache=cache)
        )
        tool_names = [t.__name__ for t in tools]
        # health_check filtered, duplicate search_users deduplicated
        assert tool_names == ["search_users"]

    def test_cache_is_used_on_second_call(self):
        client = self._make_clients()
        call_count = [0]
        original = client.list_tools
        async def counting_list_tools():
            call_count[0] += 1
            return await original()
        client.list_tools = counting_list_tools

        cache: dict = {}
        asyncio.get_event_loop().run_until_complete(
            get_cached_tools([("svc", client)], "[TEST]", ttl=300, _cache=cache)
        )
        asyncio.get_event_loop().run_until_complete(
            get_cached_tools([("svc", client)], "[TEST]", ttl=300, _cache=cache)
        )
        assert call_count[0] == 1  # second call hits cache

    def test_non_business_tools_set_contains_health_check(self):
        assert "health_check" in NON_BUSINESS_TOOLS
        assert "ping" in NON_BUSINESS_TOOLS
