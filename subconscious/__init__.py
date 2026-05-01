"""
Subconscious Python SDK.

The official Python SDK for the Subconscious API.
"""

from . import tools
from .client import Subconscious
from .errors import (
    AuthenticationError,
    ErrorCode,
    NotFoundError,
    RateLimitError,
    SubconsciousError,
    ValidationError,
)
from .types import (
    DeltaEvent,
    DoneEvent,
    Engine,
    ErrorEvent,
    FunctionTool,
    MCPAuth,
    MCPTool,
    ModelUsage,
    OutputSchema,
    PlatformTool,
    PlatformToolUsage,
    PollOptions,
    ReasoningNode,
    ReasoningNodeEvent,
    ResourceTool,
    ResultEvent,
    Run,
    RunInput,
    RunOptions,
    RunParams,
    RunResult,
    RunStatus,
    StartedEvent,
    StreamEvent,
    Tool,
    ToolCallEvent,
    ToolUse,
    Usage,
    pydantic_to_schema,
)

__version__ = "0.1.6"
__author__ = "Subconscious Systems"
__email__ = "contact@subconscious.dev"

__all__ = [
    "Subconscious",
    "tools",
    # Run types
    "Run",
    "RunStatus",
    "RunResult",
    "RunInput",
    "RunOptions",
    "RunParams",
    "ReasoningNode",
    "ToolUse",
    "Engine",
    "Usage",
    "ModelUsage",
    "PlatformToolUsage",
    "PollOptions",
    # Tool types
    "Tool",
    "PlatformTool",
    "FunctionTool",
    "MCPTool",
    "MCPAuth",
    "ResourceTool",
    # Stream events (Stream Events v2)
    "StreamEvent",
    "StartedEvent",
    "DeltaEvent",
    "ReasoningNodeEvent",
    "ToolCallEvent",
    "ResultEvent",
    "DoneEvent",
    "ErrorEvent",
    # Structured output
    "OutputSchema",
    "pydantic_to_schema",
    # Errors
    "SubconsciousError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "ErrorCode",
]
