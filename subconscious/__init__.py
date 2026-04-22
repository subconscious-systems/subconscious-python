"""
Subconscious Python SDK

The official Python SDK for the Subconscious API.
"""

from .client import Subconscious
from .content import Image
from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RequestTooLargeError,
    SubconsciousError,
    ValidationError,
)
from .types import (
    AgentToolUse,
    # Multimodal content
    AudioContent,
    ContentBlock,
    # Wire-format request models
    CreateRunBody,
    DeltaEvent,
    DoneEvent,
    Engine,
    ErrorEvent,
    FileContent,
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
    RunInputWire,
    RunOptions,
    RunParams,
    RunResult,
    RunStatus,
    # General source types (audio / file)
    Source,
    SourceBase64,
    SourceBlobRef,
    SourceUrl,
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
    # Wire-format request models
    'RunInputWire',
    'CreateRunBody',
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
    'AudioContent',
    'FileContent',
    'Source',
    'SourceBase64',
    'SourceBlobRef',
    'SourceUrl',
    # Tool response
    'ToolResponse',
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
