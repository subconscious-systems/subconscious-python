"""Tool builders (R11).

Tiny helpers that turn the discriminated-union verbosity of ``Tool`` into
a one-call API while preserving full type safety. Use these in preference
to building tool literals by hand.

Example::

    from subconscious import Subconscious, tools
    from pydantic import BaseModel

    class EmailArgs(BaseModel):
        to: str
        body: str

    client = Subconscious(api_key=...)
    run = client.run_and_wait(
        engine="tim-claude",
        input={
            "instructions": "Send a welcome email",
            "tools": [
                tools.platform("parallel_search"),
                tools.resource("sandbox"),
                tools.function(
                    name="sendEmail",
                    url="https://api.example.com/email",
                    parameters=EmailArgs,            # Pydantic OK (R13)
                    defaults={"sender_id": "svc_abc"},  # hidden from model (R12)
                    headers={"Authorization": "Bearer ..."},
                ),
                tools.mcp(
                    url="https://mcp.example.com",
                    headers={"Authorization": "Bearer ..."},  # R7
                ),
            ],
        },
    )
"""

from typing import Any, Dict, List, Literal, Optional

from .types import (
    FunctionTool,
    MCPAuth,
    MCPTool,
    PlatformTool,
    ResourceTool,
    OutputSchema,
    pydantic_to_schema,
)


def _coerce_parameters(parameters: Any, default_title: str) -> Dict[str, Any]:
    """Accept either a Pydantic model class or a raw JSON Schema dict. (R13.)"""
    if parameters is None:
        return {}
    if isinstance(parameters, dict):
        return parameters
    if isinstance(parameters, type) and hasattr(parameters, "model_json_schema"):
        return dict(pydantic_to_schema(parameters, default_title))
    # Fall through — assume already JSON-Schema shaped.
    return parameters  # type: ignore[return-value]


def platform(id: str, options: Optional[Dict[str, Any]] = None) -> PlatformTool:
    """Build a platform tool. ``options`` defaults to ``None`` (omitted)."""
    return PlatformTool(id=id, options=options)


def function(
    *,
    name: str,
    url: str,
    parameters: Any,
    description: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    defaults: Optional[Dict[str, Any]] = None,
) -> FunctionTool:
    """Build a function tool.

    ``parameters`` accepts a Pydantic ``BaseModel`` class OR a raw JSON
    Schema dict. (R13.)
    """
    return FunctionTool(
        name=name,
        description=description,
        url=url,
        parameters=_coerce_parameters(parameters, name),
        headers=headers,
        defaults=defaults,
    )


def mcp(
    *,
    url: str,
    allowed_tools: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
    auth: Optional[MCPAuth] = None,
) -> MCPTool:
    """Build an MCP tool. Use ``headers`` for header-based auth. (R7.)"""
    return MCPTool(
        url=url,
        allowed_tools=allowed_tools,
        headers=headers,
        auth=auth,
    )


def resource(id: Literal["sandbox", "memory", "browser"]) -> ResourceTool:
    """Build a hosted runtime resource tool. (R17.)"""
    return ResourceTool(id=id)
