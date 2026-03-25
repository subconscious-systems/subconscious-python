"""Tests for type definitions and tool serialization."""

import pytest

from subconscious.types import (
    FunctionTool,
    McpAuth,
    MCPTool,
    PlatformTool,
    Tool,
)
from subconscious.client import _normalize_tool


# ---------------------------------------------------------------------------
# MCPTool construction
# ---------------------------------------------------------------------------

class TestMCPTool:
    def test_basic_construction(self):
        tool = MCPTool(server="https://example.com/mcp")
        assert tool.server == "https://example.com/mcp"
        assert tool.type == "mcp"
        assert tool.allowed_tools is None
        assert tool.auth is None

    def test_with_allowed_tools(self):
        tool = MCPTool(server="https://x.com/mcp", allowed_tools=["search", "fetch"])
        assert tool.allowed_tools == ["search", "fetch"]

    def test_with_wildcard(self):
        tool = MCPTool(server="https://x.com/mcp", allowed_tools=["*"])
        assert tool.allowed_tools == ["*"]

    def test_with_empty_list_blocks_all(self):
        tool = MCPTool(server="https://x.com/mcp", allowed_tools=[])
        assert tool.allowed_tools == []

    def test_with_bearer_auth(self):
        auth = McpAuth(type="bearer", token="tok123")
        tool = MCPTool(server="https://x.com/mcp", auth=auth)
        assert tool.auth is not None
        assert tool.auth.type == "bearer"
        assert tool.auth.token == "tok123"
        assert tool.auth.header is None

    def test_with_api_key_auth(self):
        auth = McpAuth(type="api_key", token="key456", header="X-Api-Key")
        tool = MCPTool(server="https://x.com/mcp", auth=auth)
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
        tool: Tool = MCPTool(server="https://x.com/mcp")
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
            server="https://x.com/mcp",
            allowed_tools=["search", "fetch"],
        )
        result = _normalize_tool(tool)
        assert "allowedTools" in result
        assert result["allowedTools"] == ["search", "fetch"]
        assert "allowed_tools" not in result
        assert result["server"] == "https://x.com/mcp"
        assert result["type"] == "mcp"

    def test_mcp_with_auth_nested_serialization(self):
        auth = McpAuth(type="bearer", token="tok123")
        tool = MCPTool(server="https://x.com/mcp", auth=auth)
        result = _normalize_tool(tool)
        assert isinstance(result["auth"], dict)
        assert result["auth"]["type"] == "bearer"
        assert result["auth"]["token"] == "tok123"
        # header is None so should be stripped
        assert "header" not in result["auth"]

    def test_strips_none_values(self):
        tool = MCPTool(server="https://x.com/mcp")
        result = _normalize_tool(tool)
        assert "allowedTools" not in result
        assert "auth" not in result
        assert set(result.keys()) == {"server", "type"}

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
