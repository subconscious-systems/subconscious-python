"""Tests for type definitions and tool serialization."""

import pytest

from subconscious.types import (
    FunctionTool,
    McpAuth,
    McpToolAnnotations,
    MCPTool,
    NativeTool,
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
# NativeTool construction
# ---------------------------------------------------------------------------

class TestNativeTool:
    def test_basic_construction(self):
        tool = NativeTool(
            name="computer_use",
            provider="anthropic",
            tool_config={"display_width": 1024},
            url="https://api.example.com/tools/computer",
        )
        assert tool.name == "computer_use"
        assert tool.provider == "anthropic"
        assert tool.tool_config == {"display_width": 1024}
        assert tool.url == "https://api.example.com/tools/computer"
        assert tool.type == "native"
        assert tool.method == "POST"
        assert tool.timeout is None
        assert tool.headers is None
        assert tool.defaults is None

    def test_with_optional_fields(self):
        tool = NativeTool(
            name="computer_use",
            provider="anthropic",
            tool_config={},
            url="https://api.example.com/tools/computer",
            method="GET",
            timeout=30,
            headers={"X-Custom": "val"},
            defaults={"display_width": 1024},
        )
        assert tool.method == "GET"
        assert tool.timeout == 30
        assert tool.headers == {"X-Custom": "val"}
        assert tool.defaults == {"display_width": 1024}


# ---------------------------------------------------------------------------
# McpToolAnnotations
# ---------------------------------------------------------------------------

class TestMcpToolAnnotations:
    def test_all_none_defaults(self):
        ann = McpToolAnnotations()
        assert ann.title is None
        assert ann.read_only_hint is None
        assert ann.destructive_hint is None
        assert ann.idempotent_hint is None
        assert ann.open_world_hint is None

    def test_partial_construction(self):
        ann = McpToolAnnotations(title="Search", read_only_hint=True)
        assert ann.title == "Search"
        assert ann.read_only_hint is True
        assert ann.destructive_hint is None

    def test_full_construction(self):
        ann = McpToolAnnotations(
            title="Delete",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        )
        assert ann.destructive_hint is True
        assert ann.open_world_hint is True


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

    def test_native_tool_is_tool(self):
        tool: Tool = NativeTool(
            name="t", provider="p", tool_config={}, url="https://x.com"
        )
        assert tool.type == "native"

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

    def test_native_tool_serialization(self):
        tool = NativeTool(
            name="computer_use",
            provider="anthropic",
            tool_config={"w": 1024},
            url="https://x.com",
            timeout=30,
        )
        result = _normalize_tool(tool)
        assert result["name"] == "computer_use"
        assert result["toolConfig"] == {"w": 1024}
        assert result["timeout"] == 30
        assert "headers" not in result  # None stripped
        assert "defaults" not in result  # None stripped

    def test_dict_passthrough(self):
        raw = {"type": "custom", "name": "raw"}
        result = _normalize_tool(raw)
        assert result == raw

    def test_annotations_key_mapping(self):
        ann = McpToolAnnotations(
            title="Search",
            read_only_hint=True,
            destructive_hint=False,
        )
        result = _normalize_tool(ann)
        assert result["readOnlyHint"] is True
        assert result["destructiveHint"] is False
        assert "read_only_hint" not in result
        assert "idempotentHint" not in result  # None stripped


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
