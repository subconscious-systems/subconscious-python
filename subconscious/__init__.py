"""
Subconscious Python SDK

The official Python SDK for the Subconscious API.
"""

from .client import Subconscious
from .types import (
    # Run types
    Run,
    RunStatus,
    RunResult,
    RunInput,
    RunOptions,
    RunParams,
    ReasoningNode,
    Engine,
    Usage,
    ModelUsage,
    PlatformToolUsage,
    PollOptions,
    # Tool types
    Tool,
    PlatformTool,
    FunctionTool,
    MCPTool,
    # Stream events
    StreamEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    # Structured output
    OutputSchema,
    pydantic_to_schema,
)
from .errors import (
    SubconsciousError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ValidationError,
)

__version__ = "0.2.0"
__author__ = "Subconscious Systems"
__email__ = "contact@subconscious.dev"

__all__ = [
    # Client
    "Subconscious",
    # Run types
    "Run",
    "RunStatus",
    "RunResult",
    "RunInput",
    "RunOptions",
    "RunParams",
    "ReasoningNode",
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
    # Stream events
    "StreamEvent",
    "DeltaEvent",
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
]
