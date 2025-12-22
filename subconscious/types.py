"""Type definitions for the Subconscious SDK."""

from typing import Any, Dict, List, Literal, Optional, Union
from dataclasses import dataclass, field

# Engine types
Engine = Literal["tim-small-preview", "tim-large", "timini"]

# Run status types
RunStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "timed_out"]


@dataclass
class ReasoningNode:
    """A node in the reasoning tree."""

    title: str
    thought: str
    tooluse: List[Any] = field(default_factory=list)
    subtask: List["ReasoningNode"] = field(default_factory=list)
    conclusion: str = ""


@dataclass
class RunResult:
    """The result of a completed run."""

    answer: str
    reasoning: Optional[ReasoningNode] = None


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
    """Usage statistics for a run."""

    models: List[ModelUsage] = field(default_factory=list)
    platform_tools: List[PlatformToolUsage] = field(default_factory=list)


@dataclass
class Run:
    """Represents an agent run."""

    run_id: str
    status: Optional[RunStatus] = None
    result: Optional[RunResult] = None
    usage: Optional[Usage] = None


# Tool types
@dataclass
class PlatformTool:
    """A platform-hosted tool."""

    id: str
    type: Literal["platform"] = "platform"
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionTool:
    """A custom function tool."""

    name: str
    type: Literal["function"] = "function"
    description: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    method: Optional[str] = None
    timeout: Optional[int] = None


@dataclass
class MCPTool:
    """An MCP (Model Context Protocol) tool."""

    url: str
    type: Literal["mcp"] = "mcp"
    allow: Optional[List[str]] = None


# Tool union type
Tool = Union[PlatformTool, FunctionTool, MCPTool, Dict[str, Any]]


@dataclass
class RunInput:
    """Input configuration for a run."""

    instructions: str
    tools: List[Tool] = field(default_factory=list)


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

