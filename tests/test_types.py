"""Tests for type definitions, tool serialization, and run parsing."""

import pytest

from subconscious.types import (
    AgentToolUse,
    FunctionTool,
    McpAuth,
    MCPTool,
    PlatformTool,
    ReasoningTask,
    Run,
    RunError,
    RunResult,
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
# _parse_run — camelCase API response deserialization
# ---------------------------------------------------------------------------

class TestParseRun:
    """Validates that _parse_run (via Run.model_validate) correctly
    deserializes the camelCase JSON returned by GET /v1/runs/:runId."""

    def _parse(self, data):
        return Subconscious._parse_run(None, data)

    def test_full_succeeded_response(self):
        data = {
            "runId": "run_abc",
            "status": "succeeded",
            "result": {
                "answer": "hello world",
                "reasoning": [
                    {
                        "title": "Search",
                        "thought": "I need to search",
                        "tooluse": {
                            "tool_name": "web_search",
                            "tool_call_id": "call_1",
                            "parameters": {"query": "AI news"},
                            "tool_result": {"content": [{"type": "text", "text": "results"}], "is_error": False},
                        },
                        "subtasks": [
                            {"title": "Sub-step", "thought": "Analyzing..."}
                        ],
                        "conclusion": "Found results",
                    }
                ],
            },
            "usage": {
                "inputTokens": 150,
                "outputTokens": 42,
                "durationMs": 1234,
            },
        }
        run = self._parse(data)

        assert run.run_id == "run_abc"
        assert run.status == "succeeded"
        assert run.error is None

        # Result
        assert isinstance(run.result, RunResult)
        assert run.result.answer == "hello world"
        assert isinstance(run.result.reasoning, list)
        assert len(run.result.reasoning) == 1

        task = run.result.reasoning[0]
        assert isinstance(task, ReasoningTask)
        assert task.title == "Search"
        assert task.thought == "I need to search"
        assert task.conclusion == "Found results"

        # Tool use
        assert isinstance(task.tooluse, AgentToolUse)
        assert task.tooluse.tool_name == "web_search"
        assert task.tooluse.tool_call_id == "call_1"
        assert task.tooluse.parameters == {"query": "AI news"}
        assert task.tooluse.tool_result is not None

        # Subtasks
        assert isinstance(task.subtasks, list)
        assert len(task.subtasks) == 1
        assert task.subtasks[0].title == "Sub-step"

        # Usage — flat structure
        assert isinstance(run.usage, Usage)
        assert run.usage.input_tokens == 150
        assert run.usage.output_tokens == 42
        assert run.usage.duration_ms == 1234

    def test_failed_response_with_error(self):
        data = {
            "runId": "run_fail",
            "status": "failed",
            "error": {"code": "500", "message": "Engine crashed"},
            "usage": {"inputTokens": 10, "outputTokens": 0},
        }
        run = self._parse(data)

        assert run.run_id == "run_fail"
        assert run.status == "failed"
        assert isinstance(run.error, RunError)
        assert run.error.code == "500"
        assert run.error.message == "Engine crashed"
        assert run.result is None
        assert run.usage.input_tokens == 10

    def test_queued_response_minimal(self):
        data = {"runId": "run_q", "status": "queued"}
        run = self._parse(data)

        assert run.run_id == "run_q"
        assert run.status == "queued"
        assert run.result is None
        assert run.usage is None
        assert run.error is None

    def test_usage_without_duration(self):
        data = {
            "runId": "run_nodur",
            "status": "succeeded",
            "result": {"answer": "ok"},
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }
        run = self._parse(data)
        assert run.usage.duration_ms is None
        assert run.usage.input_tokens == 1
        assert run.usage.output_tokens == 1

    def test_multiple_reasoning_tasks(self):
        data = {
            "runId": "run_multi",
            "status": "succeeded",
            "result": {
                "answer": "final",
                "reasoning": [
                    {"title": "Step 1", "thought": "first"},
                    {"title": "Step 2", "thought": "second", "conclusion": "done"},
                    {"title": "Step 3"},
                ],
            },
        }
        run = self._parse(data)
        assert len(run.result.reasoning) == 3
        assert run.result.reasoning[0].title == "Step 1"
        assert run.result.reasoning[1].conclusion == "done"
        assert run.result.reasoning[2].thought is None

    def test_deeply_nested_subtasks(self):
        data = {
            "runId": "run_deep",
            "status": "succeeded",
            "result": {
                "answer": "nested",
                "reasoning": [{
                    "title": "L0",
                    "subtasks": [{
                        "title": "L1",
                        "subtasks": [{
                            "title": "L2",
                            "thought": "leaf node",
                        }],
                    }],
                }],
            },
        }
        run = self._parse(data)
        l0 = run.result.reasoning[0]
        l1 = l0.subtasks[0]
        l2 = l1.subtasks[0]
        assert l0.title == "L0"
        assert l1.title == "L1"
        assert l2.title == "L2"
        assert l2.thought == "leaf node"
        assert l2.subtasks is None

    def test_empty_reasoning_list(self):
        data = {
            "runId": "run_empty_r",
            "status": "succeeded",
            "result": {"answer": "answer only", "reasoning": []},
        }
        run = self._parse(data)
        assert run.result.reasoning == []
        assert run.result.answer == "answer only"

    def test_result_without_reasoning(self):
        data = {
            "runId": "run_no_r",
            "status": "succeeded",
            "result": {"answer": "simple answer"},
        }
        run = self._parse(data)
        assert run.result.answer == "simple answer"
        assert run.result.reasoning is None

    def test_canceled_status(self):
        data = {"runId": "run_cancel", "status": "canceled"}
        run = self._parse(data)
        assert run.status == "canceled"

    def test_timed_out_status(self):
        data = {"runId": "run_to", "status": "timed_out"}
        run = self._parse(data)
        assert run.status == "timed_out"

    def test_running_status(self):
        data = {"runId": "run_ing", "status": "running"}
        run = self._parse(data)
        assert run.status == "running"
        assert run.result is None
        assert run.usage is None

    def test_tooluse_without_result(self):
        data = {
            "runId": "run_tu",
            "status": "succeeded",
            "result": {
                "answer": "ok",
                "reasoning": [{
                    "title": "Search",
                    "tooluse": {
                        "tool_name": "web_search",
                        "parameters": {"q": "test"},
                    },
                }],
            },
        }
        run = self._parse(data)
        tu = run.result.reasoning[0].tooluse
        assert tu.tool_name == "web_search"
        assert tu.tool_call_id is None
        assert tu.tool_result is None
        assert tu.parameters == {"q": "test"}

    def test_tooluse_with_string_result(self):
        data = {
            "runId": "run_str_tr",
            "status": "succeeded",
            "result": {
                "answer": "ok",
                "reasoning": [{
                    "tooluse": {
                        "tool_name": "calc",
                        "parameters": {},
                        "tool_result": "42",
                    },
                }],
            },
        }
        run = self._parse(data)
        assert run.result.reasoning[0].tooluse.tool_result == "42"

    def test_tooluse_with_complex_result(self):
        nested_result = {
            "content": [{"type": "text", "text": "hi"}],
            "is_error": False,
            "_attachments": [{"type": "image", "source": {"kind": "blob_ref", "blob_key": "k1"}}],
        }
        data = {
            "runId": "run_cplx",
            "status": "succeeded",
            "result": {
                "answer": "ok",
                "reasoning": [{
                    "tooluse": {
                        "tool_name": "browse",
                        "parameters": {},
                        "tool_result": nested_result,
                    },
                }],
            },
        }
        run = self._parse(data)
        tr = run.result.reasoning[0].tooluse.tool_result
        assert isinstance(tr, dict)
        assert tr["content"][0]["text"] == "hi"
        assert tr["_attachments"][0]["source"]["blob_key"] == "k1"

    def test_extra_unknown_fields_tolerated(self):
        """The API may add new fields in the future; they should not
        cause validation errors."""
        data = {
            "runId": "run_extra",
            "status": "succeeded",
            "result": {"answer": "ok", "some_new_field": True},
            "usage": {"inputTokens": 1, "outputTokens": 1, "newMetric": 99},
            "newTopLevel": "surprise",
        }
        run = self._parse(data)
        assert run.run_id == "run_extra"
        assert run.usage.input_tokens == 1

    def test_error_without_usage(self):
        data = {
            "runId": "run_err_no_u",
            "status": "failed",
            "error": {"code": "timeout", "message": "timed out"},
        }
        run = self._parse(data)
        assert run.error.code == "timeout"
        assert run.usage is None


# ---------------------------------------------------------------------------
# Pydantic model construction — snake_case and alias paths
# ---------------------------------------------------------------------------

class TestModelConstruction:
    """Test that response Pydantic models can be constructed both via
    snake_case kwargs (Pythonic) and camelCase aliases (wire format)."""

    def test_run_snake_case_construction(self):
        run = Run(run_id="run_1", status="queued")
        assert run.run_id == "run_1"
        assert run.status == "queued"

    def test_run_alias_construction(self):
        run = Run.model_validate({"runId": "run_2", "status": "running"})
        assert run.run_id == "run_2"

    def test_usage_snake_case_construction(self):
        u = Usage(input_tokens=10, output_tokens=20, duration_ms=500)
        assert u.input_tokens == 10
        assert u.output_tokens == 20
        assert u.duration_ms == 500

    def test_usage_alias_construction(self):
        u = Usage.model_validate({"inputTokens": 5, "outputTokens": 3})
        assert u.input_tokens == 5
        assert u.output_tokens == 3
        assert u.duration_ms is None

    def test_usage_defaults(self):
        u = Usage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.duration_ms is None

    def test_run_error_construction(self):
        e = RunError(code="429", message="rate limited")
        assert e.code == "429"
        assert e.message == "rate limited"

    def test_run_error_defaults(self):
        e = RunError()
        assert e.code == ""
        assert e.message == ""

    def test_agent_tool_use_construction(self):
        tu = AgentToolUse(tool_name="search", parameters={"q": "test"})
        assert tu.tool_name == "search"
        assert tu.tool_call_id is None
        assert tu.tool_result is None

    def test_reasoning_task_all_optional(self):
        task = ReasoningTask()
        assert task.title is None
        assert task.thought is None
        assert task.tooluse is None
        assert task.subtasks is None
        assert task.conclusion is None

    def test_run_result_defaults(self):
        r = RunResult()
        assert r.answer == ""
        assert r.reasoning is None


# ---------------------------------------------------------------------------
# Serialization round-trip — model_dump produces alias keys
# ---------------------------------------------------------------------------

class TestSerialization:
    """Verify model_dump(by_alias=True) produces the camelCase wire format
    so the SDK could also serialize these objects for logging/debugging."""

    def test_usage_round_trip(self):
        u = Usage.model_validate({"inputTokens": 100, "outputTokens": 50, "durationMs": 3000})
        dumped = u.model_dump(by_alias=True)
        assert dumped == {"inputTokens": 100, "outputTokens": 50, "durationMs": 3000}

    def test_run_round_trip(self):
        data = {
            "runId": "run_rt",
            "status": "succeeded",
            "result": {"answer": "ok", "reasoning": None},
            "usage": {"inputTokens": 1, "outputTokens": 2, "durationMs": None},
            "error": None,
        }
        run = Run.model_validate(data)
        dumped = run.model_dump(by_alias=True)
        assert dumped["runId"] == "run_rt"
        assert dumped["usage"]["inputTokens"] == 1

    def test_reasoning_task_round_trip(self):
        task = ReasoningTask(
            title="T",
            tooluse=AgentToolUse(tool_name="calc", parameters={"x": 1}),
            subtasks=[ReasoningTask(thought="leaf")],
        )
        dumped = task.model_dump(by_alias=True, exclude_none=True)
        assert dumped["title"] == "T"
        assert dumped["tooluse"]["tool_name"] == "calc"
        assert dumped["subtasks"][0]["thought"] == "leaf"
