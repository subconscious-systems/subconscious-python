"""Tests for tool builders (R7, R11, R12, R13, R17)."""

from subconscious import tools
from subconscious.types import (
    FunctionTool,
    MCPAuth,
    MCPTool,
    PlatformTool,
    ResourceTool,
)

try:
    from pydantic import BaseModel  # type: ignore[import-not-found]

    HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    HAS_PYDANTIC = False


def test_platform_minimal():
    assert tools.platform("parallel_search") == PlatformTool(id="parallel_search")


def test_platform_with_options():
    out = tools.platform("parallel_search", {"region": "us"})
    assert out == PlatformTool(id="parallel_search", options={"region": "us"})


def test_function_with_raw_schema():
    out = tools.function(
        name="lookup",
        url="https://api.example.com",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    )
    assert isinstance(out, FunctionTool)
    assert out.parameters["properties"]["id"] == {"type": "string"}


def test_function_preserves_headers_and_defaults():
    out = tools.function(
        name="send",
        url="https://api.example.com/send",
        parameters={"type": "object", "properties": {}, "required": []},
        headers={"Authorization": "Bearer xyz"},
        defaults={"sender_id": "svc_abc"},
    )
    assert out.headers == {"Authorization": "Bearer xyz"}
    assert out.defaults == {"sender_id": "svc_abc"}


def test_mcp_with_headers_R7():
    out = tools.mcp(url="https://mcp.example.com", headers={"X-Tenant": "acme"})
    assert isinstance(out, MCPTool)
    assert out.headers == {"X-Tenant": "acme"}


def test_mcp_with_structured_auth():
    auth = MCPAuth(type="bearer", token="xyz")
    out = tools.mcp(url="https://mcp.example.com", auth=auth)
    assert out.auth == auth


def test_resource_R17():
    for rid in ("sandbox", "memory", "browser"):
        out = tools.resource(rid)  # type: ignore[arg-type]
        assert isinstance(out, ResourceTool)
        assert out.id == rid


if HAS_PYDANTIC:

    def test_function_accepts_pydantic_class_R13():
        class EmailArgs(BaseModel):  # type: ignore[misc]
            to: str
            body: str

        out = tools.function(
            name="sendEmail",
            url="https://api.example.com/email",
            parameters=EmailArgs,
        )
        params = out.parameters
        assert params["type"] == "object"
        assert set(params["properties"].keys()) == {"to", "body"}
