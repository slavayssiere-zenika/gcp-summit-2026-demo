"""Tests for agent_commons.mcp_proxy module.

Adapted for the McpTool-based implementation (ADK 1.31.1 migration).
McpTool is NOT a Python callable, so tests assert on .name and .mcp_tool
attributes instead of __name__, __doc__, __signature__.
"""

import asyncio
import pytest

from mcp.types import CallToolResult
from agent_commons.mcp_proxy import sanitize_input_schema


class _FakeClient:
    """Minimal MCPHttpClient stub."""

    def __init__(self):
        self.url = "http://fake-mcp:8000"
        self.last_call: tuple | None = None

    async def call_tool(self, tool_name: str, arguments: dict):
        self.last_call = (tool_name, arguments)
        return [{"type": "text", "text": "ok"}]


def _make_tool_def(
    name: str,
    description: str = "A tool",
    properties: dict | None = None,
    required: list | None = None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
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


from agent_commons.mcp_proxy import (
    create_mcp_tool_proxy,
    get_cached_tools,
    NON_BUSINESS_TOOLS,
    StatelessMcpSession,
)
from google.adk.tools.mcp_tool import McpTool


class TestCreateMcpToolProxy:
    """McpTool is NOT a Python callable — it exposes .name and .mcp_tool."""

    def test_returns_mcp_tool_instance(self):
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool"))
        assert isinstance(proxy, McpTool)

    def test_name_is_set(self):
        """McpTool.name replaces the old proxy.__name__."""
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool"))
        assert proxy.name == "my_tool"

    def test_description_is_set(self):
        """McpTool stores the description inside _mcp_tool.description."""
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("my_tool", description="Does stuff"))
        assert proxy._mcp_tool.description == "Does stuff"

    def test_inputschema_fallback_from_parameters(self):
        """Tool defs with 'parameters' key (legacy MCPHttpClient format) should be normalised."""
        client = _FakeClient()
        tool_def_legacy = {
            "name": "legacy_tool",
            "description": "Uses parameters key",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
        proxy = create_mcp_tool_proxy(client, tool_def_legacy)
        assert proxy.name == "legacy_tool"
        assert proxy._mcp_tool.inputSchema is not None

    def test_header_provider_returns_auth_when_set(self):
        """header_provider must inject auth from auth_header_var if present."""
        from agent_commons.mcp_client import auth_header_var
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        token = auth_header_var.set("Bearer test-jwt")
        try:
            headers = proxy._header_provider(None)  # type: ignore[attr-defined]
            assert headers == {"Authorization": "Bearer test-jwt"}
        finally:
            auth_header_var.reset(token)

    def test_header_provider_returns_empty_when_no_auth(self):
        """header_provider must return {} when no JWT is set (unauthenticated context)."""
        from agent_commons.mcp_client import auth_header_var
        client = _FakeClient()
        proxy = create_mcp_tool_proxy(client, _make_tool_def("t"))
        # Ensure no token in context
        token = auth_header_var.set(None)
        try:
            headers = proxy._header_provider(None)  # type: ignore[attr-defined]
            assert headers == {}
        finally:
            auth_header_var.reset(token)


class TestStatelessMcpSession:
    """Unit tests for the StatelessMcpSession result normalisation."""

    def test_list_result_normalised(self):
        client = _FakeClient()
        session = StatelessMcpSession(client)
        result = asyncio.get_event_loop().run_until_complete(
            session.call_tool("my_tool", {"q": "test"})
        )
        assert isinstance(result, CallToolResult)
        assert result.content[0].text == "ok"
        assert client.last_call == ("my_tool", {"q": "test"})

    def test_content_envelope_normalised(self):
        """Handles dict with 'content' key (standard MCP envelope)."""
        class _ContentClient:
            url = "http://fake"
            async def call_tool(self, name, args):
                return {"content": [{"type": "text", "text": "hello"}]}

        session = StatelessMcpSession(_ContentClient())
        result = asyncio.get_event_loop().run_until_complete(
            session.call_tool("t", {})
        )
        assert result.content[0].text == "hello"

    def test_result_envelope_normalised(self):
        """Handles dict with 'result' key (MCPHttpClient legacy envelope)."""
        class _ResultClient:
            url = "http://fake"
            async def call_tool(self, name, args):
                return {"result": '[{"name": "Alice"}]', "success": True}

        session = StatelessMcpSession(_ResultClient())
        result = asyncio.get_event_loop().run_until_complete(
            session.call_tool("t", {})
        )
        assert '[{"name": "Alice"}]' in result.content[0].text


class TestGetCachedTools:
    def _make_clients(self):
        client = _FakeClient()

        async def list_tools():
            return [
                _make_tool_def("search_users"),
                _make_tool_def("health_check"),   # should be filtered
                _make_tool_def("search_users"),   # duplicate — should be deduplicated
            ]
        client.list_tools = list_tools
        return client

    def test_deduplication_and_filtering(self):
        client = self._make_clients()
        cache: dict = {}
        tools = asyncio.get_event_loop().run_until_complete(
            get_cached_tools([("svc", client)], "[TEST]", ttl=300, _cache=cache)
        )
        tool_names = [t.name for t in tools]   # McpTool.name — NOT .__name__
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


class TestSanitizeInputSchema:
    """Unit tests for sanitize_input_schema — the Gemini 400 INVALID_ARGUMENT shield."""

    def test_valid_schema_unchanged(self):
        """Un schema correct ne doit pas être modifié."""
        schema = {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "query": {"type": "string"},
            },
            "required": ["user_id", "query"],
        }
        result = sanitize_input_schema(schema)
        assert result["required"] == ["user_id", "query"]
        assert "user_id" in result["properties"]
        assert "query" in result["properties"]

    def test_required_missing_property_is_dropped(self):
        """Un `required` listant une prop absente de `properties` doit être purgé."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name", "ghost_field"],  # ghost_field absent
        }
        result = sanitize_input_schema(schema)
        assert result["required"] == ["name"]

    def test_all_required_missing_removes_required_key(self):
        """Si tous les `required` sont invalides, la clé `required` est supprimée."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["ghost1", "ghost2"],
        }
        result = sanitize_input_schema(schema)
        assert "required" not in result

    def test_schema_without_required_unchanged(self):
        """Un schema sans `required` ne doit pas être altéré."""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        result = sanitize_input_schema(schema)
        assert "required" not in result

    def test_nested_items_array_sanitized(self):
        """Les sous-schémas dans `items` d'un array doivent aussi être sanitizés."""
        schema = {
            "type": "object",
            "properties": {
                "competencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                        },
                        "required": ["name", "ghost_nested"],  # ghost_nested absent
                    },
                }
            },
            "required": ["competencies"],
        }
        result = sanitize_input_schema(schema)
        # Top-level required intact
        assert result["required"] == ["competencies"]
        # Nested required purged
        nested = result["properties"]["competencies"]["items"]
        assert nested["required"] == ["name"]

    def test_production_scenario_competencies_assign(self):
        """Reproduit exactement le schema de assign_competencies_to_user qui causait le 400."""
        schema = {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "L'ID de l'utilisateur"},
                "competencies": {
                    "type": "array",
                    "description": "Liste des compétences à assigner",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "parent": {"type": "string"},
                            "aliases": {"type": "array", "items": {"type": "string"}},
                            "practiced": {"type": "boolean", "default": True},
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["user_id", "competencies"],
        }
        result = sanitize_input_schema(schema)
        # Top-level OK
        assert set(result["required"]) == {"user_id", "competencies"}
        # Nested items OK (name IS in properties)
        assert result["properties"]["competencies"]["items"]["required"] == ["name"]

    def test_anyof_recursion(self):
        """Les sous-schémas dans `anyOf` doivent être sanitizés récursivement."""
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {"x": {"type": "integer"}},
                            "required": ["x", "ghost"],  # ghost absent
                        },
                        {"type": "string"},
                    ]
                }
            },
        }
        result = sanitize_input_schema(schema)
        any_of_obj = result["properties"]["value"]["anyOf"][0]
        assert any_of_obj["required"] == ["x"]

    def test_non_dict_schema_returned_as_is(self):
        """Un schéma non-dict (string, None, int) doit être retourné tel quel."""
        assert sanitize_input_schema("string_schema") == "string_schema"
        assert sanitize_input_schema(None) is None
        assert sanitize_input_schema(42) == 42

    def test_original_schema_not_mutated(self):
        """Le schema original ne doit pas être muté (deep copy des dicts)."""
        original = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a", "ghost"],
        }
        import copy
        original_copy = copy.deepcopy(original)
        sanitize_input_schema(original)
        assert original == original_copy  # pas de mutation
