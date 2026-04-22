"""Type definitions for the Subconscious SDK."""

from typing import Any, Dict, List, Literal, Optional, Union
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

# Engine types — matches public, non-deprecated engines from the monorepo.
Engine = Literal[
    "tim",
    "tim-edge",
    "tim-claude",
    "tim-claude-heavy",
    "tim-oss-local",
    "tim-1.5",
    "tim-gpt-heavy-tc",
]


# JSON Schema types for structured output
class OutputSchema(Dict[str, Any]):
    """
    JSON Schema for structured output format.
    
    Expected structure:
    - $defs: Optional definitions for complex types
    - properties: Dict of property names to their JSON Schema definitions
    - required: List of required property names
    - title: Title for the schema
    - type: "object"
    
    Use pydantic_to_schema() to convert a Pydantic model to this format.
    """
    pass


def pydantic_to_schema(model: type, title: Optional[str] = None) -> OutputSchema:
    """
    Convert a Pydantic model to the JSON Schema format expected by Subconscious.
    
    Note: You typically don't need to call this directly. The SDK automatically
    converts Pydantic models passed to answerFormat/reasoningFormat.
    
    Args:
        model: A Pydantic BaseModel class
        title: Optional title override (defaults to model class name)
    
    Returns:
        An OutputSchema compatible with answerFormat/reasoningFormat
    """
    schema = model.model_json_schema()
    
    result = OutputSchema({
        "type": "object",
        "title": title or schema.get("title", model.__name__),
        "properties": schema.get("properties", {}),
        "required": schema.get("required", list(schema.get("properties", {}).keys())),
    })
    
    if "$defs" in schema:
        result["$defs"] = schema["$defs"]
    
    return result

# Run status types
RunStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "timed_out"]


# ---------------------------------------------------------------------------
# Response types — Pydantic models mirroring the API wire format 1:1.
# Field aliases match the camelCase keys returned by GET /v1/runs/:runId.
# populate_by_name=True allows both snake_case and camelCase construction.
# ---------------------------------------------------------------------------

class AgentToolUse(BaseModel):
    """A tool call within a reasoning step.

    Maps to ``AgentToolUse`` in the monorepo (schemas/index.ts).
    """
    model_config = ConfigDict(populate_by_name=True)

    tool_name: str
    tool_call_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    tool_result: Optional[Any] = None


class ReasoningTask(BaseModel):
    """A node in the reasoning tree. Recursive via ``subtasks``.

    Maps to ``ReasoningTask`` in the monorepo (schemas/index.ts).
    All fields are optional because the tree is built incrementally
    during streaming.
    """
    model_config = ConfigDict(populate_by_name=True)

    title: Optional[str] = None
    thought: Optional[str] = None
    tooluse: Optional[AgentToolUse] = None
    subtasks: Optional[List["ReasoningTask"]] = None
    conclusion: Optional[str] = None


class RunResult(BaseModel):
    """The result of a completed run.

    Maps to ``ReasoningOutput`` in the monorepo (schemas/index.ts).
    """
    answer: str = ""
    reasoning: Optional[List[ReasoningTask]] = None


class Usage(BaseModel):
    """Token usage for a run.

    Maps to ``RunUsage`` in the monorepo (schemas/index.ts).
    Flat structure matching the API wire format exactly.
    """
    model_config = ConfigDict(populate_by_name=True)

    input_tokens: int = Field(default=0, alias="inputTokens")
    output_tokens: int = Field(default=0, alias="outputTokens")
    duration_ms: Optional[int] = Field(default=None, alias="durationMs")


class RunError(BaseModel):
    """Error details for a failed run.

    Maps to ``RunError`` in the monorepo (schemas/index.ts).
    """
    code: str = ""
    message: str = ""


class Run(BaseModel):
    """Represents an agent run — mirrors GET /v1/runs/:runId response."""
    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(default="", alias="runId")
    status: Optional[RunStatus] = None
    result: Optional[RunResult] = None
    usage: Optional[Usage] = None
    error: Optional[RunError] = None


# Tool types
@dataclass
class PlatformTool:
    """A platform-hosted tool."""

    id: str
    type: Literal["platform"] = "platform"
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionTool:
    """A custom function tool.
    
    Attributes:
        name: The tool name the model will use to call it
        description: Description of what the tool does
        url: HTTP endpoint URL for the tool
        method: HTTP method (GET or POST)
        timeout: Request timeout in seconds
        parameters: JSON Schema defining the tool's parameters
        headers: HTTP headers sent when calling this tool's endpoint
        defaults: Parameter values hidden from model and injected at call time
    """

    name: str
    type: Literal["function"] = "function"
    description: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    method: Optional[str] = None
    timeout: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    """HTTP headers sent when calling this tool's endpoint."""
    defaults: Optional[Dict[str, Any]] = None
    """Parameter values hidden from model and injected at call time."""


@dataclass
class McpAuth:
    """MCP Authentication.

    Used for MCP tools that require authentication.
    Translates to an HTTP header sent with every tool call:

    - Bearer:  ``{ "Authorization": "Bearer <token>" }``
    - API key: ``{ "<header>": "<token>" }``

    Bearer auth is the most common method (e.g. OAuth tokens).
    For API key auth, the header is typically ``X-Api-Key`` but may vary —
    check the documentation of the MCP server you are connecting to.

    Attributes:
        type: Auth method — ``"bearer"`` or ``"api_key"``.
        token: The token or key value.
        header: For ``api_key`` auth only, the header name to send the token
            in (e.g. ``"X-Api-Key"``).
    """

    type: Literal["bearer", "api_key"]
    token: str
    header: Optional[str] = None


@dataclass
class MCPTool:
    """An MCP (Model Context Protocol) tool.

    Attributes:
        url: URL of the MCP server
        allowed_tools: Tool names to enable. Case-insensitive.
            ["*"] or omit for all tools. [] blocks all.
        auth: Optional authentication for the MCP server
    """

    url: str
    type: Literal["mcp"] = "mcp"
    allowed_tools: Optional[List[str]] = None
    auth: Optional[McpAuth] = None


# Tool union type
Tool = Union[PlatformTool, FunctionTool, MCPTool, Dict[str, Any]]


# Multimodal content — mirrors packages/common/schemas/index.ts (TextContent,
# ImageContent, ImageSource*). Hand-written to replace the earlier
# datamodel-codegen pipeline; the SDK only needs the input-side surface.
ImageMime = Literal["image/png", "image/jpeg", "image/gif", "image/webp"]


class TextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"]
    text: str


class ImageSourceBase64(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["base64"]
    data: str
    mime: ImageMime


class ImageSourceBlobRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["blob_ref"]
    blob_key: str
    mime: ImageMime
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    attachment_id: Optional[str] = None


class ImageSourceUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["url"]
    url: str
    mime: Optional[ImageMime] = None


ImageSource = Union[ImageSourceBase64, ImageSourceBlobRef, ImageSourceUrl]


class ImageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["image"]
    source: ImageSource


ContentBlock = Union[TextContent, ImageContent]


# Flexible input accepted by ToolResponse.build().
ToolResponseContent = Union[
    str,
    TextContent,
    ImageContent,
    List[Union[str, TextContent, ImageContent]],
]


class ToolResponse(BaseModel):
    """Canonical envelope returned by a FunctionTool HTTP endpoint.

    Reuses the ContentBlock union (TextContent | ImageContent) from run input.
    Use ``ToolResponse.build(tool_call_id, content)`` to wrap plain strings,
    a single content block, or a mixed list; the strict constructor
    ``ToolResponse(tool_call_id=..., content=[...])`` remains available for
    callers holding already-normalized blocks.
    """

    model_config = ConfigDict(extra="forbid")
    tool_call_id: str
    content: List[ContentBlock]
    is_error: bool = False

    @classmethod
    def build(
        cls,
        tool_call_id: str,
        content: ToolResponseContent,
        *,
        is_error: bool = False,
    ) -> "ToolResponse":
        """Build a tool response from text, an image, or a mixed list."""
        def _wrap(item: Union[str, TextContent, ImageContent]) -> ContentBlock:
            if isinstance(item, str):
                return TextContent(type="text", text=item)
            return item

        blocks = [_wrap(i) for i in content] if isinstance(content, list) else [_wrap(content)]
        return cls(tool_call_id=tool_call_id, content=blocks, is_error=is_error)


@dataclass
class RunInput:
    """Input configuration for a run."""

    instructions: str
    tools: List[Tool] = field(default_factory=list)
    answer_format: Optional[OutputSchema] = None
    """JSON Schema for the answer output format. Use pydantic_to_schema() to generate from Pydantic."""
    reasoning_format: Optional[OutputSchema] = None
    """JSON Schema for the reasoning output format. Use pydantic_to_schema() to generate from Pydantic."""
    content: Optional[List[ContentBlock]] = None
    """Canonical multimodal content blocks (TextContent or ImageContent). Use the
    ``Image`` helper to build ImageContent blocks from a path/bytes/URL/blob_key."""


@dataclass
class RunOptions:
    """Options for creating a run."""

    await_completion: bool = False


@dataclass
class RunParams:
    """Parameters for creating a run."""

    engine: Engine
    input: RunInput
    options: Optional[RunOptions] = None


@dataclass
class PollOptions:
    """Options for polling a run."""

    interval_ms: int = 1000
    max_attempts: Optional[int] = None


# Stream event types
@dataclass
class DeltaEvent:
    """Text delta event - emitted as text is generated."""

    type: Literal["delta"] = "delta"
    run_id: str = ""
    content: str = ""


@dataclass
class DoneEvent:
    """Stream completed successfully."""

    type: Literal["done"] = "done"
    run_id: str = ""


@dataclass
class ErrorEvent:
    """Stream encountered an error."""

    type: Literal["error"] = "error"
    run_id: str = ""
    message: str = ""
    code: Optional[str] = None


StreamEvent = Union[DeltaEvent, DoneEvent, ErrorEvent]

