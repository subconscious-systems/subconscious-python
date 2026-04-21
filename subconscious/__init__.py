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
from .content import Image
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
    # Multimodal content
    ContentBlock,
    TextContent,
    ImageContent,
    ImageSource,
    ImageSourceBase64,
    ImageSourceBlobRef,
    ImageSourceUrl,
    ImageMime,
    # Tool response
    ToolResponse,
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
    "ImageSource",
    "ImageSourceBase64",
    "ImageSourceBlobRef",
    "ImageSourceUrl",
    "ImageMime",
    # Tool response
    "ToolResponse",
    # Capability helpers
    "engine_supports_images",
    "SUGGESTED_IMAGE_ENGINES",
    "EngineDoesNotSupportImagesError",
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
