"""Subconscious API client."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

import requests

from ._capabilities import (
    EngineDoesNotSupportImagesError,
    SUGGESTED_IMAGE_ENGINES,
    engine_supports_images,
)
from .errors import raise_for_status
from .types import (
    DeltaEvent,
    DoneEvent,
    Engine,
    ErrorEvent,
    PollOptions,
    Run,
    RunInput,
    RunOptions,
    RunParams,
    RunResult,
    RunStatus,
    StreamEvent,
    Tool,
    Usage,
)


# Cap the JSON body size we'll send. Express has a 6 MB body parser limit, so we
# keep the SDK comfortably under that to leave headroom for tools/instructions.
MAX_REQUEST_BYTES = 5 * 1024 * 1024


class RequestTooLargeError(ValueError):
    """Raised when the serialized run request exceeds MAX_REQUEST_BYTES."""


def _resolve_api_key(explicit: Optional[str]) -> str:
    """
    Resolve the API key using a standard precedence chain:
      1. Explicitly passed ``api_key`` argument
      2. ``SUBCONSCIOUS_API_KEY`` environment variable
      3. ``~/.subcon/config.json`` (written by ``subconscious login``)
    """
    if explicit:
        return explicit

    env_key = os.environ.get("SUBCONSCIOUS_API_KEY")
    if env_key:
        return env_key

    try:
        config_path = Path.home() / ".subcon" / "config.json"
        config = json.loads(config_path.read_text())
        if config.get("subconscious_api_key"):
            return config["subconscious_api_key"]
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    raise ValueError(
        "No API key found. Either:\n"
        "  • Pass api_key to the Subconscious constructor\n"
        "  • Set SUBCONSCIOUS_API_KEY environment variable\n"
        "  • Run `npx subconscious login` to authenticate"
    )


def _resolve_schema(schema: Any) -> Optional[Dict[str, Any]]:
    """
    Resolve a schema to a JSON Schema dict.
    
    Accepts:
    - A Pydantic BaseModel class (calls model_json_schema() automatically)
    - A dict (passed through as-is)
    - None (returns None)
    """
    if schema is None:
        return None
    
    # Check if it's a Pydantic model class
    if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    
    # Already a dict
    if isinstance(schema, dict):
        return schema
    
    # Unknown type - try to use it as-is
    return schema

# Python snake_case → API camelCase key mapping for tool serialization
_TOOL_KEY_MAP = {
    "allowed_tools": "allowedTools",
}


def _normalize_tool(tool: Any) -> Dict[str, Any]:
    """Convert a tool dataclass to an API-compatible dict.

    Strips None values and maps snake_case keys to camelCase.
    """
    if not hasattr(tool, "__dict__"):
        return tool

    result = {}
    for k, v in tool.__dict__.items():
        if v is None:
            continue
        # Recursively normalize nested dataclasses (e.g. McpAuth)
        if hasattr(v, "__dict__"):
            v = {
                _TOOL_KEY_MAP.get(nk, nk): nv
                for nk, nv in v.__dict__.items()
                if nv is not None
            }
        key = _TOOL_KEY_MAP.get(k, k)
        result[key] = v
    return result


def _normalize_content_block(block: Any) -> Any:
    """Convert a Pydantic ContentBlock (or dict) to a JSON-ready dict.

    Accepts either a ``TextContent``/``ImageContent`` model (from
    ``subconscious.types``) or a plain dict matching the same shape.
    """
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    return block


def _content_has_images(content: Optional[List[Any]]) -> bool:
    if not content:
        return False
    for block in content:
        block_type = (
            getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
        )
        if block_type == "image":
            return True
    return False


def _build_input_dict(input: Union[RunInput, Dict[str, Any]]) -> Dict[str, Any]:
    """Lower a RunInput/dict into the on-the-wire shape expected by the API."""
    if isinstance(input, RunInput):
        input_dict: Dict[str, Any] = {
            "instructions": input.instructions,
            "tools": input.tools,
        }
        if input.answer_format is not None:
            input_dict["answerFormat"] = _resolve_schema(input.answer_format)
        if input.reasoning_format is not None:
            input_dict["reasoningFormat"] = _resolve_schema(input.reasoning_format)
        if input.content is not None:
            input_dict["content"] = input.content
    else:
        input_dict = dict(input)  # copy so we don't mutate the caller's dict
        if "answerFormat" in input_dict:
            input_dict["answerFormat"] = _resolve_schema(input_dict["answerFormat"])
        if "reasoningFormat" in input_dict:
            input_dict["reasoningFormat"] = _resolve_schema(input_dict["reasoningFormat"])

    input_dict["tools"] = [_normalize_tool(t) for t in input_dict.get("tools", [])]

    # Normalize content blocks (Pydantic → dict).
    if input_dict.get("content"):
        input_dict["content"] = [_normalize_content_block(b) for b in input_dict["content"]]

    return input_dict


def _check_capabilities_and_size(engine: Engine, payload: Dict[str, Any]) -> None:
    """Client-side guards mirroring server-side checks. Surfaces typed errors
    before the network roundtrip when possible."""
    content = payload.get("input", {}).get("content")
    if _content_has_images(content) and not engine_supports_images(engine):
        raise EngineDoesNotSupportImagesError(
            f'Engine "{engine}" does not accept images. '
            f"Use one of: {', '.join(SUGGESTED_IMAGE_ENGINES)}."
        )
    serialized = json.dumps(payload)
    if len(serialized.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise RequestTooLargeError(
            f"request body exceeds {MAX_REQUEST_BYTES} bytes — split images "
            "across multiple turns or upload via /v1/internal/attachments first"
        )


TERMINAL_STATUSES: List[RunStatus] = ["succeeded", "failed", "canceled", "timed_out"]


class Subconscious:
    """
    The main Subconscious API client.

    The API key is resolved automatically if not provided:
    ``api_key`` argument → ``SUBCONSCIOUS_API_KEY`` env var → ``~/.subcon/config.json``.

    Example:
        ```python
        from subconscious import Subconscious

        # Key auto-resolved from env or ~/.subcon/config.json
        client = Subconscious()

        run = client.run(
            engine="tim-gpt",
            input={
                "instructions": "Search for the latest news about AI",
                "tools": [{"type": "platform", "id": "fast_search"}],
            },
            options={"await_completion": True},
        )

        print(run.result.answer)
        ```
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.subconscious.dev/v1",
    ):
        """
        Initialize the Subconscious client.

        Args:
            api_key: Your Subconscious API key. If omitted, resolved from
                     SUBCONSCIOUS_API_KEY env var or ~/.subcon/config.json.
            base_url: API base URL (default: https://api.subconscious.dev/v1)
        """
        self._api_key = _resolve_api_key(api_key)
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        """Get default request headers."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        url = f"{self._base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers(),
            json=json_data,
        )
        raise_for_status(response)
        return response.json()

    def run(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
        options: Optional[Union[RunOptions, Dict[str, Any]]] = None,
    ) -> Run:
        """
        Create a new run.

        Args:
            engine: The engine to use ("tim-edge", "tim-gpt", or "tim-gpt-heavy")
            input: Input configuration with instructions, tools, and optional answer/reasoning formats
            options: Optional run options (await_completion, etc.)

        Returns:
            The created run, with results if await_completion is True

        Example:
            ```python
            from pydantic import BaseModel
            
            class Result(BaseModel):
                answer: str
                confidence: float
            
            run = client.run(
                engine="tim-gpt",
                input={
                    "instructions": "Search for AI news",
                    "tools": [{"type": "platform", "id": "fast_search"}],
                    "answerFormat": Result,  # Pass the Pydantic class directly
                },
                options={"await_completion": True},
            )
            ```
        """
        input_dict = _build_input_dict(input)
        body = {"engine": engine, "input": input_dict}
        _check_capabilities_and_size(engine, body)

        # Make request
        data = self._request(
            "POST",
            "/runs",
            body,
        )

        run_id = data["runId"]

        # Check if we should wait for completion
        await_completion = False
        if options:
            if isinstance(options, RunOptions):
                await_completion = options.await_completion
            elif isinstance(options, dict):
                await_completion = options.get("await_completion", False)

        if not await_completion:
            return Run(run_id=run_id)

        return self.wait(run_id)

    def get(self, run_id: str) -> Run:
        """
        Get the current state of a run.

        Args:
            run_id: The ID of the run to retrieve

        Returns:
            The run with its current status and result (if completed)
        """
        data = self._request("GET", f"/runs/{run_id}")
        return self._parse_run(data)

    def wait(
        self,
        run_id: str,
        options: Optional[Union[PollOptions, Dict[str, Any]]] = None,
    ) -> Run:
        """
        Wait for a run to complete by polling.

        Args:
            run_id: The ID of the run to wait for
            options: Polling options (interval_ms, max_attempts)

        Returns:
            The completed run

        Raises:
            TimeoutError: If max_attempts is exceeded

        Example:
            ```python
            run = client.wait(
                run_id,
                options={"interval_ms": 2000, "max_attempts": 60},
            )
            ```
        """
        # Normalize options
        interval_ms = 1000
        max_attempts = None
        if options:
            if isinstance(options, PollOptions):
                interval_ms = options.interval_ms
                max_attempts = options.max_attempts
            elif isinstance(options, dict):
                interval_ms = options.get("interval_ms", 1000)
                max_attempts = options.get("max_attempts")

        attempts = 0
        while True:
            run = self.get(run_id)

            if run.status and run.status in TERMINAL_STATUSES:
                return run

            attempts += 1
            if max_attempts is not None and attempts >= max_attempts:
                raise TimeoutError(f"Polling exceeded max attempts ({max_attempts})")

            time.sleep(interval_ms / 1000)

    def cancel(self, run_id: str) -> Run:
        """
        Cancel a running run.

        Args:
            run_id: The ID of the run to cancel

        Returns:
            The canceled run
        """
        data = self._request("POST", f"/runs/{run_id}/cancel")
        return self._parse_run(data)

    def stream(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
    ) -> Generator[StreamEvent, None, Optional[Run]]:
        """
        Create a streaming run that yields text deltas as they arrive.

        Args:
            engine: The engine to use
            input: Input configuration with instructions, tools, and optional answer/reasoning formats

        Yields:
            StreamEvent: Delta, done, or error events

        Returns:
            The final run (if stream completes successfully)

        Example:
            ```python
            from pydantic import BaseModel
            
            class Result(BaseModel):
                summary: str
            
            for event in client.stream(
                engine="tim-gpt",
                input={
                    "instructions": "Write an essay",
                    "tools": [],
                    "answerFormat": Result,  # Pass the Pydantic class directly
                },
            ):
                if event.type == "delta":
                    print(event.content, end="", flush=True)
                elif event.type == "done":
                    print("\\nDone!")
            ```

        Note:
            Rich streaming events (reasoning steps, tool calls) are coming soon.
            Currently provides text deltas only.
        """
        input_dict = _build_input_dict(input)
        body = {"engine": engine, "input": input_dict}
        _check_capabilities_and_size(engine, body)

        url = f"{self._base_url}/runs/stream"
        headers = {
            **self._headers(),
            "Accept": "text/event-stream",
        }

        response = requests.post(
            url,
            headers=headers,
            json=body,
            stream=True,
        )
        raise_for_status(response)

        run_id = response.headers.get("x-run-id", "")
        is_error = False

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            line = line.strip()

            # Skip heartbeat comments
            if line.startswith(":"):
                continue

            # Handle event type markers
            if line.startswith("event:"):
                event_type = line[6:].strip()
                is_error = event_type == "error"
                continue

            # Handle data lines
            if line.startswith("data:"):
                data_content = line[5:].strip()

                # Stream end
                if data_content == "[DONE]":
                    yield DoneEvent(type="done", run_id=run_id)
                    continue

                try:
                    payload = json.loads(data_content)

                    # Meta event with run_id
                    if "run_id" in payload:
                        run_id = payload["run_id"]
                        continue

                    # Error event
                    if is_error or "error" in payload:
                        yield ErrorEvent(
                            type="error",
                            run_id=run_id,
                            message=payload.get("details") or payload.get("error", "Unknown error"),
                            code=payload.get("code"),
                        )
                        is_error = False
                        continue

                    # OpenAI-compatible chunk with text delta
                    choices = payload.get("choices", [])
                    if choices:
                        content = choices[0].get("delta", {}).get("content")
                        if content:
                            yield DeltaEvent(type="delta", run_id=run_id, content=content)

                except json.JSONDecodeError:
                    pass

        return Run(run_id=run_id, status="succeeded") if run_id else None

    def _parse_run(self, data: Dict[str, Any]) -> Run:
        """Parse a run response from the API."""
        result = None
        if "result" in data and data["result"]:
            result = RunResult(
                answer=data["result"].get("answer", ""),
                reasoning=data["result"].get("reasoning"),
            )

        usage = None
        if "usage" in data and data["usage"]:
            usage = Usage(
                models=data["usage"].get("models", []),
                platform_tools=data["usage"].get("platformTools", []),
            )

        return Run(
            run_id=data.get("runId", data.get("run_id", "")),
            status=data.get("status"),
            result=result,
            usage=usage,
        )
