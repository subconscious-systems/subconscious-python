"""Tests for type definitions and tool serialization."""

import pytest

from subconscious.types import (
    FunctionTool,
    McpAuth,
    MCPTool,
    ModelUsage,
    PlatformTool,
    PlatformToolUsage,
    Tool,
    Usage,
)
from subconscious.client import _normalize_tool, Subconscious


# ---------------------------------------------------------------------------
# MCPTool construction
# ---------------------------------------------------------------------------

class TestMCPTool:
    def test_basic_construction(self):
        tool = MCPTool(url="https://example.com/mcp")
        assert tool.url == "https://example.com/mcp"
        assert tool.type == "mcp"
        assert tool.allowed_tools is None
        assert tool.auth is None

    def test_with_allowed_tools(self):
        tool = MCPTool(url="https://x.com/mcp", allowed_tools=["search", "fetch"])
        assert tool.allowed_tools == ["search", "fetch"]

    def test_with_wildcard(self):
        tool = MCPTool(url="https://x.com/mcp", allowed_tools=["*"])
        assert tool.allowed_tools == ["*"]

    def test_with_empty_list_blocks_all(self):
        tool = MCPTool(url="https://x.com/mcp", allowed_tools=[])
        assert tool.allowed_tools == []

    def test_with_bearer_auth(self):
        auth = McpAuth(type="bearer", token="tok123")
        tool = MCPTool(url="https://x.com/mcp", auth=auth)
        assert tool.auth is not None
        assert tool.auth.type == "bearer"
        assert tool.auth.token == "tok123"
        assert tool.auth.header is None

    def test_with_api_key_auth(self):
        auth = McpAuth(type="api_key", token="key456", header="X-Api-Key")
        tool = MCPTool(url="https://x.com/mcp", auth=auth)
        assert tool.auth.type == "api_key"
        assert tool.auth.token == "key456"
        assert tool.auth.header == "X-Api-Key"


# ---------------------------------------------------------------------------
# Tool union type assignability
# ---------------------------------------------------------------------------

class TestToolUnion:
    def test_platform_tool_is_tool(self):
        tool: Tool = PlatformTool(id="fast_search")
        assert tool.type == "platform"

    def test_function_tool_is_tool(self):
        tool: Tool = FunctionTool(name="my_func")
        assert tool.type == "function"

    def test_mcp_tool_is_tool(self):
        tool: Tool = MCPTool(url="https://x.com/mcp")
        assert tool.type == "mcp"

    def test_dict_is_tool(self):
        tool: Tool = {"type": "custom", "name": "raw"}
        assert tool["type"] == "custom"


# ---------------------------------------------------------------------------
# Serialization (_normalize_tool)
# ---------------------------------------------------------------------------

class TestNormalizeTool:
    def test_mcp_key_mapping(self):
        tool = MCPTool(
            url="https://x.com/mcp",
            allowed_tools=["search", "fetch"],
        )
        result = _normalize_tool(tool)
        assert "allowedTools" in result
        assert result["allowedTools"] == ["search", "fetch"]
        assert "allowed_tools" not in result
        assert result["url"] == "https://x.com/mcp"
        assert result["type"] == "mcp"

    def test_mcp_with_auth_nested_serialization(self):
        auth = McpAuth(type="bearer", token="tok123")
        tool = MCPTool(url="https://x.com/mcp", auth=auth)
        result = _normalize_tool(tool)
        assert isinstance(result["auth"], dict)
        assert result["auth"]["type"] == "bearer"
        assert result["auth"]["token"] == "tok123"
        # header is None so should be stripped
        assert "header" not in result["auth"]

    def test_strips_none_values(self):
        tool = MCPTool(url="https://x.com/mcp")
        result = _normalize_tool(tool)
        assert "allowedTools" not in result
        assert "auth" not in result
        assert set(result.keys()) == {"url", "type"}

    def test_dict_passthrough(self):
        raw = {"type": "custom", "name": "raw"}
        result = _normalize_tool(raw)
        assert result == raw

# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_function_tool_unchanged(self):
        tool = FunctionTool(
            name="my_tool",
            description="Does stuff",
            url="https://x.com/tool",
            method="POST",
            parameters={"type": "object", "properties": {}},
            headers={"X-Key": "val"},
            defaults={"org": "acme"},
        )
        assert tool.name == "my_tool"
        assert tool.type == "function"
        result = _normalize_tool(tool)
        assert result["name"] == "my_tool"
        assert result["headers"] == {"X-Key": "val"}
        assert result["defaults"] == {"org": "acme"}

    def test_platform_tool_unchanged(self):
        tool = PlatformTool(id="fast_search", options={"limit": 10})
        assert tool.id == "fast_search"
        assert tool.type == "platform"
        result = _normalize_tool(tool)
        assert result["id"] == "fast_search"
        assert result["options"] == {"limit": 10}


# ---------------------------------------------------------------------------
# Usage parsing (_parse_run)
# ---------------------------------------------------------------------------

class TestParseRunUsage:
    """Test that _parse_run correctly deserializes usage statistics."""

    def _parse(self, data):
        """Call _parse_run without needing a live client."""
        return Subconscious._parse_run(None, data)

    def test_usage_with_camel_case_api_response(self):
        data = {
            "runId": "run_abc",
            "status": "succeeded",
            "result": {"answer": "hello"},
            "usage": {
                "models": [
                    {
                        "engine": "tim-gpt",
                        "inputTokens": 150,
                        "outputTokens": 42,
                        "totalTokens": 192,
                    }
                ],
                "platformTools": [
                    {"toolId": "fast_search", "calls": 3}
                ],
                "durationMs": 1234,
            },
        }
        run = self._parse(data)
        assert run.run_id == "run_abc"
        assert run.status == "succeeded"
        assert run.result.answer == "hello"

        # Usage should be proper dataclass instances
        assert isinstance(run.usage, Usage)
        assert len(run.usage.models) == 1
        m = run.usage.models[0]
        assert isinstance(m, ModelUsage)
        assert m.engine == "tim-gpt"
        assert m.input_tokens == 150
        assert m.output_tokens == 42
        assert m.total_tokens == 192

        assert len(run.usage.platform_tools) == 1
        pt = run.usage.platform_tools[0]
        assert isinstance(pt, PlatformToolUsage)
        assert pt.tool_id == "fast_search"
        assert pt.calls == 3

        assert run.usage.duration_ms == 1234

    def test_usage_with_snake_case_keys(self):
        """Ensure snake_case keys also work (defensive)."""
        data = {
            "runId": "run_def",
            "status": "succeeded",
            "result": {"answer": "ok"},
            "usage": {
                "models": [
                    {
                        "engine": "tim-edge",
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    }
                ],
                "platformTools": [
                    {"tool_id": "web_browse", "calls": 1}
                ],
                "duration_ms": 500,
            },
        }
        run = self._parse(data)
        m = run.usage.models[0]
        assert m.input_tokens == 10
        assert m.output_tokens == 5
        assert m.total_tokens == 15

        pt = run.usage.platform_tools[0]
        assert pt.tool_id == "web_browse"
        assert run.usage.duration_ms == 500

    def test_usage_with_multiple_models(self):
        data = {
            "runId": "run_multi",
            "status": "succeeded",
            "usage": {
                "models": [
                    {"engine": "tim-edge", "inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                    {"engine": "tim-gpt", "inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
                ],
                "platformTools": [],
            },
        }
        run = self._parse(data)
        assert len(run.usage.models) == 2
        assert run.usage.models[0].engine == "tim-edge"
        assert run.usage.models[1].engine == "tim-gpt"
        assert run.usage.models[1].input_tokens == 100

    def test_no_usage_returns_none(self):
        data = {"runId": "run_none", "status": "queued"}
        run = self._parse(data)
        assert run.usage is None

    def test_empty_usage_returns_none(self):
        data = {"runId": "run_empty", "status": "queued", "usage": {}}
        run = self._parse(data)
        assert run.usage is None

    def test_usage_without_duration(self):
        data = {
            "runId": "run_nodur",
            "status": "succeeded",
            "usage": {
                "models": [{"engine": "tim-gpt", "inputTokens": 1, "outputTokens": 1, "totalTokens": 2}],
            },
        }
        run = self._parse(data)
        assert run.usage.duration_ms is None
