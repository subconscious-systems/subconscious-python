"""Tests for the tool normalization layer (R9, R12)."""

from subconscious import tools
from subconscious._normalize_tools import normalize_tools


def test_promote_defaults_to_properties_R12():
    input_tools = [
        tools.function(
            name="sendEmail",
            url="https://api.example.com",
            parameters={
                "type": "object",
                "properties": {"to": {"type": "string"}},
                "required": ["to"],
            },
            defaults={"sender_id": "svc_abc"},
        )
    ]
    out = normalize_tools(input_tools)
    assert out is not None
    params = out[0]["parameters"]
    assert params["properties"]["sender_id"] == {"type": "string"}
    assert params["properties"]["to"] == {"type": "string"}


def test_does_not_overwrite_explicit_property():
    input_tools = [
        tools.function(
            name="sendEmail",
            url="https://api.example.com",
            parameters={
                "type": "object",
                "properties": {
                    "sender_id": {"type": "string", "description": "explicit"}
                },
                "required": [],
            },
            defaults={"sender_id": "svc_abc"},
        )
    ]
    out = normalize_tools(input_tools)
    assert out is not None
    assert out[0]["parameters"]["properties"]["sender_id"] == {
        "type": "string",
        "description": "explicit",
    }


def test_infers_shapes_for_non_string_defaults():
    input_tools = [
        tools.function(
            name="createTicket",
            url="https://api.example.com",
            parameters={"type": "object", "properties": {}, "required": []},
            defaults={
                "priority": 3,
                "urgent": True,
                "tags": ["ops"],
                "extra": {"foo": 1},
            },
        )
    ]
    out = normalize_tools(input_tools)
    assert out is not None
    props = out[0]["parameters"]["properties"]
    assert props["priority"] == {"type": "number"}
    assert props["urgent"] == {"type": "boolean"}
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert props["extra"] == {"type": "object"}


def test_default_function_tool_headers_overlay_R9():
    input_tools = [
        tools.function(
            name="send",
            url="https://api.example.com",
            parameters={"type": "object", "properties": {}, "required": []},
        )
    ]
    out = normalize_tools(
        input_tools,
        default_function_tool_headers={"X-Tenant": "acme"},
    )
    assert out is not None
    assert out[0]["headers"] == {"X-Tenant": "acme"}


def test_per_tool_headers_win_on_conflict():
    input_tools = [
        tools.function(
            name="send",
            url="https://api.example.com",
            parameters={"type": "object", "properties": {}, "required": []},
            headers={"X-Tenant": "beta"},
        )
    ]
    out = normalize_tools(
        input_tools,
        default_function_tool_headers={"X-Tenant": "acme", "X-Trace": "t1"},
    )
    assert out is not None
    assert out[0]["headers"] == {"X-Tenant": "beta", "X-Trace": "t1"}


def test_default_defaults_promoted_to_properties_R9_R12():
    input_tools = [
        tools.function(
            name="send",
            url="https://api.example.com",
            parameters={"type": "object", "properties": {}, "required": []},
        )
    ]
    out = normalize_tools(
        input_tools,
        default_function_tool_defaults={"tenant_id": "t_xyz"},
    )
    assert out is not None
    assert out[0]["defaults"] == {"tenant_id": "t_xyz"}
    assert out[0]["parameters"]["properties"]["tenant_id"] == {"type": "string"}


def test_non_function_tools_passthrough():
    input_tools = [tools.platform("parallel_search"), tools.resource("sandbox")]
    out = normalize_tools(
        input_tools,
        default_function_tool_headers={"X-Tenant": "acme"},
    )
    assert out is not None
    assert out[0] == {"id": "parallel_search", "type": "platform"}
    assert out[1] == {"id": "sandbox", "type": "resource"}
