"""
Subconscious Python SDK

The official Python SDK for the Subconscious API.
"""

from ._capabilities import (
    EngineDoesNotSupportImagesError,
    SUGGESTED_IMAGE_ENGINES,
    engine_supports_images,
)
from .client import RequestTooLargeError, Subconscious
from .content import (
    ContentBlock,
    Image,
    ImageContent,
    ImageSourceBase64,
    ImageSourceBlobRef,
    ImageSourceUrl,
    TextContent,
)
from .traces import densify_trace
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
    McpAuth,
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

__version__ = "0.3.0"
__author__ = "Subconscious Systems"
__email__ = "contact@subconscious.dev"

__all__ = [
    # Client
    "Subconscious",
    "RequestTooLargeError",
    # Multimodal content
    "Image",
    "ContentBlock",
    "TextContent",
    "ImageContent",
    "ImageSourceBase64",
    "ImageSourceBlobRef",
    "ImageSourceUrl",
    # Capability helpers
    "engine_supports_images",
    "SUGGESTED_IMAGE_ENGINES",
    "EngineDoesNotSupportImagesError",
    # Trace utilities
    "densify_trace",
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
    "McpAuth",
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
