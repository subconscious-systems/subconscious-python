"""
Subconscious Python SDK

The official Python SDK for the Subconscious API.
"""

from ._capabilities import (
    SUGGESTED_IMAGE_ENGINES,
    EngineDoesNotSupportImagesError,
    engine_supports_images,
)
from .client import RequestTooLargeError, Subconscious
from .content import Image
from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    SubconsciousError,
    ValidationError,
)
from .types import (
    AgentToolUse,
    # Multimodal content
    ContentBlock,
    DeltaEvent,
    DoneEvent,
    Engine,
    ErrorEvent,
    FunctionTool,
    ImageContent,
    ImageMime,
    ImageSource,
    ImageSourceBase64,
    ImageSourceBlobRef,
    ImageSourceUrl,
    McpAuth,
    MCPTool,
    # Structured output
    OutputSchema,
    PlatformTool,
    PollOptions,
    ReasoningTask,
    # Run types
    Run,
    RunError,
    RunInput,
    RunOptions,
    RunParams,
    RunResult,
    RunStatus,
    # Stream events
    StreamEvent,
    TextContent,
    # Tool types
    Tool,
    # Tool response
    ToolResponse,
    Usage,
    pydantic_to_schema,
)

__version__ = '1.0.0'
__author__ = 'Subconscious Systems'
__email__ = 'contact@subconscious.dev'

__all__ = [
    # Client
    'Subconscious',
    'RequestTooLargeError',
    # Multimodal content
    'Image',
    'ContentBlock',
    'TextContent',
    'ImageContent',
    'ImageSource',
    'ImageSourceBase64',
    'ImageSourceBlobRef',
    'ImageSourceUrl',
    'ImageMime',
    # Tool response
    'ToolResponse',
    # Capability helpers
    'engine_supports_images',
    'SUGGESTED_IMAGE_ENGINES',
    'EngineDoesNotSupportImagesError',
    # Run types
    'Run',
    'RunStatus',
    'RunResult',
    'RunInput',
    'RunOptions',
    'RunParams',
    'RunError',
    'ReasoningTask',
    'AgentToolUse',
    'Engine',
    'Usage',
    'PollOptions',
    # Tool types
    'Tool',
    'PlatformTool',
    'FunctionTool',
    'MCPTool',
    'McpAuth',
    # Stream events
    'StreamEvent',
    'DeltaEvent',
    'DoneEvent',
    'ErrorEvent',
    # Structured output
    'OutputSchema',
    'pydantic_to_schema',
    # Errors
    'SubconsciousError',
    'AuthenticationError',
    'RateLimitError',
    'NotFoundError',
    'ValidationError',
]
