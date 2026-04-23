"""Type definitions for the Subconscious SDK."""

import json
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field

from .errors import RequestTooLargeError

# Engine types — matches public, non-deprecated engines from the monorepo.
Engine = Literal[
    'tim',
    'tim-edge',
    'tim-claude',
    'tim-claude-heavy',
    'tim-oss-local',
    'tim-1.5',
    'tim-gpt-heavy-tc',
]


# JSON Schema types for structured output
class OutputSchema(dict[str, Any]):
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


def pydantic_to_schema(model: type, title: str | None = None) -> OutputSchema:
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

    result = OutputSchema(
        {
            'type': 'object',
            'title': title or schema.get('title', model.__name__),
            'properties': schema.get('properties', {}),
            'required': schema.get('required', list(schema.get('properties', {}).keys())),
        }
    )

    if '$defs' in schema:
        result['$defs'] = schema['$defs']

    return result


# Run status types
RunStatus = Literal['queued', 'running', 'succeeded', 'failed', 'canceled', 'timed_out']


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
    tool_call_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    tool_result: Any | None = None


class ReasoningTask(BaseModel):
    """A node in the reasoning tree. Recursive via ``subtasks``.

    Maps to ``ReasoningTask`` in the monorepo (schemas/index.ts).
    All fields are optional because the tree is built incrementally
    during streaming.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    thought: str | None = None
    tooluse: AgentToolUse | None = None
    subtasks: list['ReasoningTask'] | None = None
    conclusion: str | None = None


class RunResult(BaseModel):
    """The result of a completed run.

    Maps to ``ReasoningOutput`` in the monorepo (schemas/index.ts).
    """

    answer: str = ''
    reasoning: list[ReasoningTask] | None = None


class Usage(BaseModel):
    """Token usage for a run.

    Maps to ``RunUsage`` in the monorepo (schemas/index.ts).
    Flat structure matching the API wire format exactly.
    """

    model_config = ConfigDict(populate_by_name=True)

    input_tokens: int = Field(default=0, alias='inputTokens')
    output_tokens: int = Field(default=0, alias='outputTokens')
    duration_ms: int | None = Field(default=None, alias='durationMs')


class RunError(BaseModel):
    """Error details for a failed run.

    Maps to ``RunError`` in the monorepo (schemas/index.ts).
    """

    code: str = ''
    message: str = ''


class Run(BaseModel):
    """Represents an agent run — mirrors GET /v1/runs/:runId response."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(default='', alias='runId')
    status: RunStatus | None = None
    result: RunResult | None = None
    usage: Usage | None = None
    error: RunError | None = None


# Tool types
@dataclass
class PlatformTool:
    """A platform-hosted tool."""

    id: str
    type: Literal['platform'] = 'platform'
    options: dict[str, Any] = field(default_factory=dict)


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
    type: Literal['function'] = 'function'
    description: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    url: str | None = None
    method: str | None = None
    timeout: int | None = None
    headers: dict[str, str] | None = None
    """HTTP headers sent when calling this tool's endpoint."""
    defaults: dict[str, Any] | None = None
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

    type: Literal['bearer', 'api_key']
    token: str
    header: str | None = None


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
    type: Literal['mcp'] = 'mcp'
    allowed_tools: list[str] | None = None
    auth: McpAuth | None = None


# Tool union type
Tool = PlatformTool | FunctionTool | MCPTool | dict[str, Any]


# Multimodal content — mirrors timlarge/src/timlarge/types.py canonical types.
# A single Source union is shared across all content blocks (text, image, audio, file).


class TextContent(BaseModel):
    type: Literal['text']
    text: str


class SourceBase64(BaseModel):
    kind: Literal['base64']
    data: str
    mime: str


class SourceBlobRef(BaseModel):
    kind: Literal['blob_ref']
    blob_key: str
    mime: str
    size_bytes: int | None = None
    attachment_id: str | None = None
    presigned_url: str | None = None
    presigned_expires_at: str | None = None


class SourceUrl(BaseModel):
    kind: Literal['url']
    url: str
    mime: str | None = None


Source = Annotated[SourceBase64 | SourceBlobRef | SourceUrl, Discriminator('kind')]


class ImageContent(BaseModel):
    type: Literal['image']
    source: Source


class AudioContent(BaseModel):
    type: Literal['audio']
    source: Source


class FileContent(BaseModel):
    type: Literal['file']
    source: Source
    filename: str | None = None
    mime: str | None = None


ContentBlock = Annotated[
    TextContent | ImageContent | AudioContent | FileContent,
    Discriminator('type'),
]


# Flexible input accepted by ToolResponse.build().
_ToolResponseItem = str | TextContent | ImageContent | AudioContent | FileContent
ToolResponseContent = _ToolResponseItem | list[_ToolResponseItem]


class ToolResponse(BaseModel):
    """Canonical envelope returned by a FunctionTool HTTP endpoint.

    Reuses the ContentBlock union (text, image, audio, file) from run input.
    Use ``ToolResponse.build(tool_call_id, content)`` to wrap plain strings,
    a single content block, or a mixed list; the strict constructor
    ``ToolResponse(tool_call_id=..., content=[...])`` remains available for
    callers holding already-normalized blocks.
    """

    tool_call_id: str | None = None
    content: list[ContentBlock]
    is_error: bool = False

    @classmethod
    def build(
        cls,
        tool_call_id: str | None,
        content: ToolResponseContent,
        *,
        is_error: bool = False,
    ) -> 'ToolResponse':
        """Build a tool response from text, an image, audio, a file, or a mixed list."""

        def _wrap(item: _ToolResponseItem) -> ContentBlock:
            if isinstance(item, str):
                return TextContent(type='text', text=item)
            return item

        blocks = [_wrap(i) for i in content] if isinstance(content, list) else [_wrap(content)]
        return cls(tool_call_id=tool_call_id, content=blocks, is_error=is_error)


@dataclass
class RunInput:
    """Input configuration for a run."""

    instructions: str
    tools: list[Tool] = field(default_factory=list)
    resources: list[str] | None = None
    skills: list[str] | None = None
    """Names of skills to inject into the system prompt for this run. Skills are
    reusable prompt fragments resolved by name at request time (platform/public
    skills are global; org skills are org-scoped). Unknown names fail the request."""
    answer_format: OutputSchema | None = None
    """JSON Schema for the answer output format. Use pydantic_to_schema() to generate from Pydantic."""
    reasoning_format: OutputSchema | None = None
    """JSON Schema for the reasoning output format. Use pydantic_to_schema() to generate from Pydantic."""
    content: list[ContentBlock] | None = None
    """Canonical multimodal content blocks (TextContent or ImageContent). Use the
    ``Image`` helper to build ImageContent blocks from a path/bytes/URL/blob_key."""


# ---------------------------------------------------------------------------
# Request wire-format models — Pydantic models for the POST /v1/runs body.
# Mirrors the exact camelCase shape the API expects so the SDK validates
# payload structure at construction time.
# ---------------------------------------------------------------------------


class RunInputWire(BaseModel):
    """Wire-format model for the ``input`` field of POST /v1/runs.

    Mirrors the exact camelCase shape the API expects, so the SDK can
    validate the payload structure at construction time rather than
    discovering mismatches at the network boundary.

    Construct via ``RunInputWire.from_run_input()`` which handles
    schema resolution, tool normalization, and content serialization.
    """

    model_config = ConfigDict(populate_by_name=True)

    _TOOL_KEY_MAP: ClassVar[dict[str, str]] = {
        'allowed_tools': 'allowedTools',
    }

    instructions: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    content: list[dict[str, Any]] | None = None
    resources: list[str] | None = None
    skills: list[str] | None = Field(
        default=None,
        description=(
            'Names of skills to inject into the system prompt for this run. '
            'Skills are reusable prompt fragments resolved by name at request time '
            '(platform/public skills are global; org skills are org-scoped). '
            'Unknown names fail the request.'
        ),
    )
    answer_format: dict[str, Any] | None = Field(default=None, alias='answerFormat')
    reasoning_format: dict[str, Any] | None = Field(default=None, alias='reasoningFormat')

    @classmethod
    def from_run_input(cls, input: RunInput | dict[str, Any]) -> 'RunInputWire':
        """Build from a user-facing ``RunInput`` or raw dict.

        Resolves Pydantic-class schemas, normalizes tool dataclasses to
        dicts with camelCase keys, and serializes content blocks.
        """
        if isinstance(input, RunInput):
            return cls(
                instructions=input.instructions,
                tools=[cls._normalize_tool(t) for t in input.tools],
                resources=input.resources or None,
                skills=input.skills or None,
                content=(
                    [cls._normalize_content_block(b) for b in input.content]
                    if input.content
                    else None
                ),
                answer_format=cls._resolve_schema(input.answer_format),
                reasoning_format=cls._resolve_schema(input.reasoning_format),
            )

        raw = dict(input)
        return cls(
            instructions=raw['instructions'],
            tools=[cls._normalize_tool(t) for t in raw.get('tools', [])],
            content=(
                [cls._normalize_content_block(b) for b in raw['content']]
                if raw.get('content')
                else None
            ),
            resources=raw.get('resources') or None,
            skills=raw.get('skills') or None,
            answer_format=cls._resolve_schema(raw.get('answerFormat')),
            reasoning_format=cls._resolve_schema(raw.get('reasoningFormat')),
        )

    @staticmethod
    def _resolve_schema(schema: Any) -> dict[str, Any] | None:
        """Resolve a schema to a JSON Schema dict.

        Accepts a Pydantic BaseModel class (calls ``model_json_schema()``),
        a dict (passed through), or None.
        """
        if schema is None:
            return None
        if isinstance(schema, type) and hasattr(schema, 'model_json_schema'):
            return schema.model_json_schema()
        if isinstance(schema, dict):
            return schema
        return schema

    @classmethod
    def _normalize_tool(cls, tool: Any) -> dict[str, Any]:
        """Convert a tool dataclass to an API-compatible dict.

        Strips None values and maps snake_case keys to camelCase.
        """
        if not hasattr(tool, '__dict__'):
            return tool

        result = {}
        for k, v in tool.__dict__.items():
            if v is None:
                continue
            if hasattr(v, '__dict__'):
                v = {
                    cls._TOOL_KEY_MAP.get(nk, nk): nv
                    for nk, nv in v.__dict__.items()
                    if nv is not None
                }
            key = cls._TOOL_KEY_MAP.get(k, k)
            result[key] = v
        return result

    @staticmethod
    def _normalize_content_block(block: Any) -> Any:
        """Convert a Pydantic ContentBlock (or dict) to a JSON-ready dict."""
        if hasattr(block, 'model_dump'):
            return block.model_dump(mode='json', exclude_none=True)
        return block


class RunOptionsWire(BaseModel):
    """Wire-format model for the ``options`` field of POST /v1/runs.

    Mirrors the server Zod schema: ``timeout`` and ``max_step_tokens``
    (snake_case) are the only server-recognized fields. Client-side flags
    like ``await_completion`` are excluded — they never reach the server.
    """

    model_config = ConfigDict(populate_by_name=True)

    timeout: int | None = Field(
        default=None,
        description='Maximum run duration in seconds (1–3600). Server cancels the run if exceeded.',
    )
    max_step_tokens: int | None = Field(
        default=None,
        description='Per-step token ceiling (256–20000). Caps tokens generated in any single reasoning step.',
    )


class RunOutputWire(BaseModel):
    """Wire-format model for the ``output`` field of POST /v1/runs.

    Server Zod schema uses camelCase keys (``callbackUrl``, ``responseContent``);
    we mirror that exactly via Pydantic field aliases.
    """

    model_config = ConfigDict(populate_by_name=True)

    callback_url: str | None = Field(
        default=None,
        alias='callbackUrl',
        description=(
            'Webhook URL the server POSTs to when the run reaches a terminal state. '
            'Useful for async workflows where polling or streaming is impractical.'
        ),
    )
    response_content: Literal['full', 'answer_only'] | None = Field(
        default=None,
        alias='responseContent',
        description=(
            'Shape of the run result. "full" returns the complete reasoning tree '
            'and answer; "answer_only" returns just the final answer. Defaults to full.'
        ),
    )


class CreateRunBody(BaseModel):
    """Wire-format model for the full POST /v1/runs request body.

    Validates the top-level shape (``engine`` + ``input`` [+ optional
    ``options`` and ``output``]) and serializes to the dict the API expects
    via ``to_dict()``. Size validation is built in — ``to_dict()`` raises
    ``RequestTooLargeError`` if the payload exceeds the API limit.
    """

    MAX_REQUEST_BYTES: ClassVar[int] = 5 * 1024 * 1024

    engine: Engine
    input: RunInputWire
    options: RunOptionsWire | None = None
    output: RunOutputWire | None = None

    @classmethod
    def build(
        cls,
        engine: Engine,
        input: RunInput | dict[str, Any],
        options: 'RunOptions | dict[str, Any] | None' = None,
    ) -> 'CreateRunBody':
        """Construct from user-facing types, normalizing input + server options.

        ``await_completion`` is intentionally stripped from the wire body —
        it's a client-side polling toggle that must not reach the server.
        """
        return cls(
            engine=engine,
            input=RunInputWire.from_run_input(input),
            options=cls._wire_options(options),
            output=cls._wire_output(options),
        )

    @staticmethod
    def _wire_options(options: 'RunOptions | dict[str, Any] | None') -> RunOptionsWire | None:
        if options is None:
            return None
        if isinstance(options, RunOptions):
            timeout = options.timeout
            mst = options.max_step_tokens
        else:
            timeout = options.get('timeout')
            mst = options.get('max_step_tokens')
        if timeout is None and mst is None:
            return None
        return RunOptionsWire(timeout=timeout, max_step_tokens=mst)

    @staticmethod
    def _wire_output(options: 'RunOptions | dict[str, Any] | None') -> RunOutputWire | None:
        if options is None:
            return None
        if isinstance(options, RunOptions):
            out = options.output
            if out is None:
                return None
            if out.callback_url is None and out.response_content is None:
                return None
            return RunOutputWire(
                callback_url=out.callback_url,
                response_content=out.response_content,
            )
        raw = options.get('output')
        if not raw:
            return None
        # Accept both snake_case and camelCase from dict users.
        callback = raw.get('callback_url') if isinstance(raw, dict) else None
        if callback is None and isinstance(raw, dict):
            callback = raw.get('callbackUrl')
        response_content = raw.get('response_content') if isinstance(raw, dict) else None
        if response_content is None and isinstance(raw, dict):
            response_content = raw.get('responseContent')
        if callback is None and response_content is None:
            return None
        return RunOutputWire(callback_url=callback, response_content=response_content)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the JSON-ready dict sent over the wire.

        Raises ``RequestTooLargeError`` if the serialized body exceeds
        the API size limit.
        """
        d = self.model_dump(by_alias=True, exclude_none=True)
        serialized = json.dumps(d)
        if len(serialized.encode('utf-8')) > self.MAX_REQUEST_BYTES:
            raise RequestTooLargeError(
                f'request body exceeds {self.MAX_REQUEST_BYTES} bytes — split images '
                'across multiple turns or upload via /v1/internal/attachments first'
            )
        return d


@dataclass
class RunOutput:
    """Server-side output delivery options (webhook, response payload shape).

    Carried in the request body as a top-level ``output`` object.
    """

    callback_url: str | None = None
    """Webhook URL the server POSTs to when the run reaches a terminal state.
    Useful for async workflows where polling or streaming is impractical."""

    response_content: Literal['full', 'answer_only'] | None = None
    """Shape of the run result. 'full' returns the complete reasoning tree
    and answer; 'answer_only' returns just the final answer. Defaults to 'full'."""


@dataclass
class RunOptions:
    """Options for creating a run.

    ``await_completion`` is purely a client-side flag that toggles polling
    inside :meth:`Subconscious.run`; it is never sent to the server. The
    remaining fields (``timeout``, ``max_step_tokens``, ``output``) are
    serialized into the POST /v1/runs body as server-side runtime limits.
    """

    await_completion: bool = False
    """Client-side only — never sent to the server. When True, ``client.run()``
    polls ``GET /v1/runs/:id`` until the run reaches a terminal state before
    returning. When False (default), ``run()`` returns as soon as the run is
    accepted, with only ``run_id`` populated."""

    timeout: int | None = None
    """Maximum run duration in seconds (1–3600). Server cancels the run if exceeded."""

    max_step_tokens: int | None = None
    """Per-step token ceiling (256–20000). Caps tokens generated in any single reasoning step."""

    output: RunOutput | None = None
    """Server-side output delivery options (webhook, response payload shape)."""


@dataclass
class RunParams:
    """Parameters for creating a run."""

    engine: Engine
    input: RunInput
    options: RunOptions | None = None


@dataclass
class PollOptions:
    """Options for polling a run."""

    interval_ms: int = 1000
    max_attempts: int | None = None


# Stream event types
@dataclass
class DeltaEvent:
    """Text delta event - emitted as text is generated."""

    type: Literal['delta'] = 'delta'
    run_id: str = ''
    content: str = ''


@dataclass
class DoneEvent:
    """Stream completed successfully."""

    type: Literal['done'] = 'done'
    run_id: str = ''


@dataclass
class ErrorEvent:
    """Stream encountered an error."""

    type: Literal['error'] = 'error'
    run_id: str = ''
    message: str = ''
    code: str | None = None


StreamEvent = DeltaEvent | DoneEvent | ErrorEvent
