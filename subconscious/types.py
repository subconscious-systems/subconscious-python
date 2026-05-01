"""Type definitions for the Subconscious SDK (1.0)."""

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar, Union

# ---------------------------------------------------------------------------
# Engine identity
# ---------------------------------------------------------------------------
#
# Sourced from `packages/common/engines.ts`. The Literal lists the live
# canonical names plus legacy aliases the server still accepts and resolves
# at ingest. New code should prefer one of the live names below.
Engine = Literal[
    "tim",
    "tim-edge",
    "tim-claude",
    "tim-claude-heavy",
    "tim-omni",
    "tim-omni-mini",
    # Legacy aliases — accepted by the server, resolved to a live engine.
    "tim-large",
    "tim-small",
    "tim-small-preview",
    "tim-gpt",
    "tim-gpt-heavy",
    "timini",
]


# ---------------------------------------------------------------------------
# JSON Schema for structured output
# ---------------------------------------------------------------------------
class OutputSchema(Dict[str, Any]):
    """
    JSON Schema for structured output format.

    Expected structure:
    - $defs: Optional definitions for complex types
    - properties: Dict of property names to their JSON Schema definitions
    - required: List of required property names
    - title: Title for the schema
    - type: "object"

    Most users do not need to construct this directly; the SDK accepts a
    Pydantic model in `answer_format` / `reasoning_format` and converts it
    automatically. (R13.)
    """

    pass


def pydantic_to_schema(model: type, title: Optional[str] = None) -> OutputSchema:
    """
    Convert a Pydantic model to the JSON Schema format expected by Subconscious.

    Note: You typically don't need to call this directly. The SDK
    automatically converts Pydantic models passed to `answer_format` /
    `reasoning_format`. (R13.)
    """
    schema = model.model_json_schema()  # type: ignore[attr-defined]
    result = OutputSchema(
        {
            "type": "object",
            "title": title or schema.get("title", model.__name__),
            "properties": schema.get("properties", {}),
            "required": schema.get(
                "required", list(schema.get("properties", {}).keys())
            ),
        }
    )
    if "$defs" in schema:
        result["$defs"] = schema["$defs"]
    return result


# Run lifecycle
RunStatus = Literal[
    "queued", "running", "succeeded", "failed", "canceled", "timed_out"
]


# ---------------------------------------------------------------------------
# Reasoning shapes (R2, R3)
# ---------------------------------------------------------------------------


@dataclass
class ToolUse:
    """One completed tool invocation captured inside a reasoning node.

    Pre-1.0 the SDK typed this as ``List[Any]`` forcing every consumer to
    cast and ``json.loads``. The structured shape eliminates that. (R3.)
    """

    tool_name: str
    parameters: Optional[Any] = None
    tool_result: Optional[Any] = None


@dataclass
class ReasoningNode:
    """A node in the reasoning tree.

    Note ``subtasks`` (plural). Earlier versions shipped ``subtask``
    (singular) which differed from the engine wire format. (R2.)
    """

    title: str
    thought: str
    tooluse: Optional[ToolUse] = None
    subtasks: List["ReasoningNode"] = field(default_factory=list)
    conclusion: str = ""


# ---------------------------------------------------------------------------
# Run + result
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass
class RunResult(Generic[T]):
    """The structured result of a completed run.

    Generic over ``T`` — the answer type. Defaults to ``Any`` for free-form
    completions. When using ``answer_format`` consumers may type-hint the
    answer's shape. (R10.)
    """

    answer: T
    reasoning: Optional[List[ReasoningNode]] = None


@dataclass
class ModelUsage:
    """Token usage for a specific model."""

    engine: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class PlatformToolUsage:
    """Usage statistics for a platform tool."""

    tool_id: str
    calls: int


@dataclass
class Usage:
    """Token usage for a run."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Run(Generic[T]):
    """Represents an agent run."""

    run_id: str
    status: Optional[RunStatus] = None
    result: Optional[RunResult[T]] = None
    usage: Optional[Usage] = None


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@dataclass
class PlatformTool:
    """A platform-hosted tool."""

    id: str
    type: Literal["platform"] = "platform"
    options: Optional[Dict[str, Any]] = None


@dataclass
class FunctionTool:
    """A custom function tool the engine dispatches to via HTTP.

    Body shape: flat JSON keyed by parameter name (no ``tool_name`` envelope).

    ``defaults`` are hidden parameter values merged into the dispatched
    body server-side; the model never sees them. The SDK auto-promotes
    keys-only-in-defaults into ``parameters`` at normalization time so the
    engine has a complete schema. (R12.)
    """

    name: str
    type: Literal["function"] = "function"
    description: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    defaults: Optional[Dict[str, Any]] = None


@dataclass
class MCPAuth:
    """Bearer / API-key auth for an MCP tool."""

    type: Literal["bearer", "api_key"]
    token: str
    header: Optional[str] = None


@dataclass
class MCPTool:
    """An MCP (Model Context Protocol) tool.

    Use ``headers`` for arbitrary header-based auth (R7). Use ``auth`` for
    the structured Bearer / API-key shape.
    """

    url: str
    type: Literal["mcp"] = "mcp"
    allowed_tools: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    auth: Optional[MCPAuth] = None


@dataclass
class ResourceTool:
    """A hosted runtime resource — sandbox, memory, or browser. (R17.)"""

    id: Literal["sandbox", "memory", "browser"]
    type: Literal["resource"] = "resource"


# Tool union type
Tool = Union[PlatformTool, FunctionTool, MCPTool, ResourceTool, Dict[str, Any]]


# ---------------------------------------------------------------------------
# Run input
# ---------------------------------------------------------------------------


@dataclass
class RunInput:
    """Input configuration for a run.

    Mirrors the API shape exactly. (R1.)
    """

    instructions: str
    tools: List[Tool] = field(default_factory=list)
    images: Optional[List[str]] = None
    """Inline image inputs — public URLs or base64 data URIs. (R1.)"""
    resources: Optional[List[str]] = None
    """**Deprecated** — pass ``ResourceTool`` blocks inside ``tools`` instead. (R17.)"""
    skills: Optional[List[str]] = None
    """Skill IDs the server resolves into a manifest. (R1.)"""
    agent_id: Optional[str] = None
    """Optional agent identifier — associates the run with an agent's config + memory. (R1.)"""
    answer_format: Optional[Any] = None
    """JSON Schema or Pydantic model for the answer output format. (R13.)"""
    reasoning_format: Optional[Any] = None
    """JSON Schema or Pydantic model for the reasoning output format. (R13.)"""


@dataclass
class RunParams:
    """Parameters for creating a run."""

    engine: Engine
    input: RunInput


@dataclass
class PollOptions:
    """Options for polling a run."""

    interval_ms: int = 1000
    max_attempts: Optional[int] = None


# ---------------------------------------------------------------------------
# Stream events (Stream Events v2)
# ---------------------------------------------------------------------------


@dataclass
class StartedEvent:
    """Emitted once, immediately after stream open. Carries the runId
    synchronously so consumers can register cancellation handlers. (R8.)"""

    type: Literal["started"] = "started"
    run_id: str = ""


@dataclass
class DeltaEvent:
    """Text delta event - emitted as text is generated."""

    type: Literal["delta"] = "delta"
    run_id: str = ""
    content: str = ""


@dataclass
class ReasoningNodeEvent:
    """One completed reasoning node. (R15.)"""

    type: Literal["reasoning_node"] = "reasoning_node"
    run_id: str = ""
    node: Optional[ReasoningNode] = None


@dataclass
class ToolCallEvent:
    """One completed tool invocation. (R15.)"""

    type: Literal["tool_call"] = "tool_call"
    run_id: str = ""
    call: Optional[ToolUse] = None


@dataclass
class ResultEvent(Generic[T]):
    """The final structured run envelope, emitted exactly once on success
    immediately before ``DoneEvent``. (R15.)"""

    type: Literal["result"] = "result"
    run_id: str = ""
    result: Optional[RunResult[T]] = None
    usage: Optional[Usage] = None


@dataclass
class DoneEvent:
    """Stream completed. Always the last event."""

    type: Literal["done"] = "done"
    run_id: str = ""


@dataclass
class ErrorEvent:
    """Stream encountered an error. The ``code`` field is required (R5)."""

    type: Literal["error"] = "error"
    run_id: str = ""
    code: str = "internal_error"
    message: str = ""
    details: Optional[Dict[str, Any]] = None


StreamEvent = Union[
    StartedEvent,
    DeltaEvent,
    ReasoningNodeEvent,
    ToolCallEvent,
    ResultEvent,
    DoneEvent,
    ErrorEvent,
]
