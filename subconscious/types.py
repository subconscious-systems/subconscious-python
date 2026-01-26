"""Type definitions for the Subconscious SDK."""

from typing import Any, Dict, List, Literal, Optional, Union
from dataclasses import dataclass, field

# Engine types
Engine = Literal["tim-edge", "tim-gpt", "tim-gpt-heavy"]


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
    # Get the JSON Schema from Pydantic
    schema = model.model_json_schema()
    
    # Create the output schema
    result = OutputSchema({
        "type": "object",
        "title": title or schema.get("title", model.__name__),
        "properties": schema.get("properties", {}),
        "required": schema.get("required", list(schema.get("properties", {}).keys())),
    })
    
    # Include $defs if present (for complex nested types)
    if "$defs" in schema:
        result["$defs"] = schema["$defs"]
    
    return result

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
    answer_format: Optional[OutputSchema] = None
    """JSON Schema for the answer output format. Use pydantic_to_schema() to generate from Pydantic."""
    reasoning_format: Optional[OutputSchema] = None
    """JSON Schema for the reasoning output format. Use pydantic_to_schema() to generate from Pydantic."""


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

