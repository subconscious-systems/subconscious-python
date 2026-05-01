"""Subconscious API client."""

import json
import time
import warnings
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Generator, List, Optional, Union

import requests

from ._normalize_tools import normalize_tools
from .errors import raise_for_status
from .types import (
    DeltaEvent,
    DoneEvent,
    Engine,
    ErrorEvent,
    PollOptions,
    ReasoningNode,
    ReasoningNodeEvent,
    ResultEvent,
    Run,
    RunInput,
    RunOptions,
    RunResult,
    RunStatus,
    StartedEvent,
    StreamEvent,
    ToolCallEvent,
    ToolUse,
    Usage,
)


_AWAIT_COMPLETION_WARNING_SHOWN = False


def _warn_await_completion_deprecated() -> None:
    global _AWAIT_COMPLETION_WARNING_SHOWN
    if _AWAIT_COMPLETION_WARNING_SHOWN:
        return
    _AWAIT_COMPLETION_WARNING_SHOWN = True
    warnings.warn(
        "options.await_completion is deprecated. "
        "Call client.run_and_wait(...) instead of "
        "client.run(..., options={'await_completion': True}). "
        "The legacy field will be removed in a future minor release.",
        DeprecationWarning,
        stacklevel=3,
    )


def _await_completion_requested(options: Any) -> bool:
    """Read ``options.await_completion`` from a dict or RunOptions."""
    if options is None:
        return False
    if isinstance(options, RunOptions):
        return bool(options.await_completion)
    if isinstance(options, dict):
        return bool(options.get("await_completion"))
    return False


def _resolve_schema(schema: Any) -> Optional[Dict[str, Any]]:
    """
    Resolve a schema to a JSON Schema dict.

    Accepts:
    - A Pydantic BaseModel class (calls model_json_schema() automatically) (R13)
    - A dict (passed through as-is)
    - None (returns None)
    """
    if schema is None:
        return None

    if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()

    if isinstance(schema, dict):
        return schema

    return schema


TERMINAL_STATUSES: List[RunStatus] = [
    "succeeded",
    "failed",
    "canceled",
    "timed_out",
]


class Subconscious:
    """The main Subconscious API client.

    Example::

        from subconscious import Subconscious, tools

        client = Subconscious(api_key="...")

        # Fire-and-forget (R18):
        run = client.run(
            engine="tim-claude",
            input={"instructions": "Search AI news"},
        )

        # Block until done (R18, R10):
        run = client.run_and_wait(
            engine="tim-claude",
            input={
                "instructions": "Summarize this article…",
                "answerFormat": SummarySchema,  # Pydantic class — auto-converted (R13)
            },
        )
        print(run.result.answer)

        # Stream:
        for event in client.stream(engine="tim-claude", input=...):
            if event.type == "started":  print("runId:", event.run_id)
            if event.type == "delta":    print(event.content, end="")
            if event.type == "result":   print("answer:", event.result.answer)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.subconscious.dev/v1",
        *,
        default_function_tool_headers: Optional[Dict[str, str]] = None,
        default_function_tool_defaults: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Subconscious client.

        Args:
            api_key: Your Subconscious API key.
            base_url: API base URL.
            default_function_tool_headers: Headers merged into every
                FunctionTool dispatch. Use this for cross-cutting auth
                instead of duplicating ``headers`` on every function tool.
                Per-tool values win on conflict. (R9.)
            default_function_tool_defaults: Hidden parameter values merged
                into every FunctionTool's ``defaults``. Per-tool values
                win on conflict. (R9.)
        """
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_function_tool_headers = default_function_tool_headers
        self._default_function_tool_defaults = default_function_tool_defaults

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
        url = f"{self._base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers(),
            json=json_data,
        )
        raise_for_status(response)
        return response.json()

    # ------------------------------------------------------------------
    # Internal: build POST /v1/runs body
    # ------------------------------------------------------------------

    def _build_create_body(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if isinstance(input, RunInput):
            input_dict: Dict[str, Any] = {
                "instructions": input.instructions,
            }
            if input.tools is not None:
                input_dict["tools"] = input.tools
            if input.images is not None:
                input_dict["images"] = input.images
            if input.resources is not None:
                input_dict["resources"] = input.resources
            if input.skills is not None:
                input_dict["skills"] = input.skills
            if input.agent_id is not None:
                input_dict["agentId"] = input.agent_id
            if input.answer_format is not None:
                input_dict["answerFormat"] = _resolve_schema(input.answer_format)
            if input.reasoning_format is not None:
                input_dict["reasoningFormat"] = _resolve_schema(input.reasoning_format)
        else:
            input_dict = dict(input)
            if "answerFormat" in input_dict:
                input_dict["answerFormat"] = _resolve_schema(input_dict["answerFormat"])
            if "reasoningFormat" in input_dict:
                input_dict["reasoningFormat"] = _resolve_schema(
                    input_dict["reasoningFormat"]
                )
            # Camel-case agent id alias for ergonomic snake-case dict callers.
            if "agent_id" in input_dict and "agentId" not in input_dict:
                input_dict["agentId"] = input_dict.pop("agent_id")

        # Normalize tools (apply R9 overlays + R12 defaults promotion).
        if "tools" in input_dict:
            input_dict["tools"] = normalize_tools(
                input_dict.get("tools"),
                default_function_tool_headers=self._default_function_tool_headers,
                default_function_tool_defaults=self._default_function_tool_defaults,
            )

        return {"engine": engine, "input": input_dict}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
        *,
        options: Optional[Union[RunOptions, Dict[str, Any]]] = None,
        poll_options: Optional[Union[PollOptions, Dict[str, Any]]] = None,
    ) -> Run:
        """Create a run and return its ``run_id`` immediately. Fire-and-forget.

        Use :py:meth:`run_and_wait` if you want to block until the run reaches
        a terminal state. (R18.)

        Back-compat: passing ``options={"await_completion": True}`` (or the
        ``RunOptions(await_completion=True)`` dataclass) transparently routes
        through :py:meth:`run_and_wait` and emits a one-shot
        :py:class:`DeprecationWarning`. New code should call
        :py:meth:`run_and_wait` directly.
        """
        if _await_completion_requested(options):
            _warn_await_completion_deprecated()
            return self.run_and_wait(engine, input, poll_options=poll_options)
        return self._create_run_only(engine, input)

    def run_and_wait(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
        *,
        poll_options: Optional[Union[PollOptions, Dict[str, Any]]] = None,
    ) -> Run:
        """Create a run and poll until it reaches a terminal state. (R18.)"""
        # Use ``_create_run_only`` (the bare POST) instead of ``run()`` to
        # avoid ping-ponging on the deprecated ``options.await_completion``
        # back-compat path.
        run = self._create_run_only(engine, input)
        return self.wait(run.run_id, poll_options)

    def _create_run_only(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
    ) -> Run:
        """Internal: bare POST /runs and return the run_id only."""
        body = self._build_create_body(engine, input)
        data = self._request("POST", "/runs", body)
        return Run(run_id=data["runId"])

    def get(self, run_id: str) -> Run:
        """Get the current state of a run."""
        data = self._request("GET", f"/runs/{run_id}")
        return self._parse_run(data)

    def wait(
        self,
        run_id: str,
        options: Optional[Union[PollOptions, Dict[str, Any]]] = None,
    ) -> Run:
        """Wait for a run to complete by polling."""
        interval_ms = 1000
        max_attempts: Optional[int] = None
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
                raise TimeoutError(
                    f"Polling exceeded max attempts ({max_attempts})"
                )

            time.sleep(interval_ms / 1000)

    def cancel(self, run_id: str) -> Run:
        """Cancel a run.

        **Idempotent** (R9). Callers may invoke this against a run in any
        state (running, queued, already terminal) and receive the run's
        current shape with a 200 response. Already-cancelled or already-
        succeeded runs are returned unchanged with their existing status,
        so you do not need to wrap this in ``try/except`` for the common
        case. Errors are only raised for network/auth failures.
        """
        data = self._request("POST", f"/runs/{run_id}/cancel")
        return self._parse_run(data)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def stream(
        self,
        engine: Engine,
        input: Union[RunInput, Dict[str, Any]],
    ) -> Generator[StreamEvent, None, Optional[Run]]:
        """Create a streaming run and yield typed events.

        Stream Events v2 (R8, R15) — yields ``StartedEvent`` first,
        then any number of ``DeltaEvent`` / ``ReasoningNodeEvent`` /
        ``ToolCallEvent`` events, exactly one of ``ResultEvent`` (success)
        or ``ErrorEvent`` (failure), then ``DoneEvent`` last.
        """
        body = self._build_create_body(engine, input)

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

        header_run_id = response.headers.get("x-run-id", "")
        # R8: emit `started` synchronously the moment we have a runId, even
        # before the first server frame.
        emitted_started_runid: Optional[str] = None
        if header_run_id:
            yield StartedEvent(run_id=header_run_id)
            emitted_started_runid = header_run_id

        run_id = header_run_id

        for event in self._iter_sse_events(response, run_id):
            # Skip a duplicate `started` event for the same id we already synthesized.
            if (
                isinstance(event, StartedEvent)
                and event.run_id == emitted_started_runid
            ):
                continue
            if isinstance(event, StartedEvent):
                emitted_started_runid = event.run_id
                run_id = event.run_id
            yield event

        return Run(run_id=run_id, status="succeeded") if run_id else None

    def observe(
        self,
        run_id: str,
    ) -> Generator[StreamEvent, None, Optional[Run]]:
        """Re-attach to an in-flight (or finished) run and stream its events. (R16.)

        Same wire format and event taxonomy as :py:meth:`stream`. Useful
        when a parent process restarts and needs to resume an existing
        run.

        Example::

            run = client.run(engine="tim-claude", input=...)
            persist_to_db(run.run_id)
            # … later, possibly in a different process …
            for event in client.observe(run.run_id):
                handle(event)
        """
        url = f"{self._base_url}/runs/{run_id}/stream"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }

        response = requests.get(url, headers=headers, stream=True)
        raise_for_status(response)

        for event in self._iter_sse_events(response, run_id):
            yield event

        return Run(run_id=run_id, status="succeeded") if run_id else None

    # ------------------------------------------------------------------
    # SSE parsing
    # ------------------------------------------------------------------

    def _iter_sse_events(
        self,
        response: requests.Response,
        run_id: str,
    ) -> Generator[StreamEvent, None, None]:
        """Parse a chunked SSE response into typed StreamEvent values."""
        pending_event: Optional[str] = None

        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line  # already decoded
            if not line:
                pending_event = None
                continue

            if line.startswith(":"):
                # Heartbeat / comment.
                continue

            if line.startswith("event:"):
                pending_event = line[6:].strip()
                continue

            if not line.startswith("data:"):
                continue
            data_content = line[5:].strip()

            if data_content == "[DONE]":
                yield DoneEvent(run_id=run_id)
                pending_event = None
                continue

            try:
                payload = json.loads(data_content)
            except json.JSONDecodeError:
                continue

            event = self._parse_sse_payload(pending_event, payload, run_id)
            if event is None:
                continue

            # Update tracked run_id from `started` events.
            if isinstance(event, StartedEvent):
                run_id = event.run_id
            yield event

    def _parse_sse_payload(
        self,
        event_tag: Optional[str],
        payload: Dict[str, Any],
        run_id: str,
    ) -> Optional[StreamEvent]:
        if event_tag in ("started", "meta"):
            # Canonical wire key is ``runId`` (camelCase). The legacy
            # ``run_id`` snake_case form is accepted for one minor
            # release of back-compat with older API builds.
            new_id = payload.get("runId") or payload.get("run_id") or run_id
            if not new_id:
                return None
            return StartedEvent(run_id=new_id)

        if event_tag == "reasoning_node":
            node_data = payload.get("node", payload)
            return ReasoningNodeEvent(run_id=run_id, node=_parse_reasoning_node(node_data))

        if event_tag == "tool_call":
            call_data = payload.get("call", payload)
            return ToolCallEvent(run_id=run_id, call=_parse_tool_use(call_data))

        if event_tag == "result":
            result_data = payload.get("result", payload)
            usage_data = payload.get("usage")
            result = RunResult(
                answer=result_data.get("answer"),
                reasoning=_parse_reasoning_list(result_data.get("reasoning")),
            )
            usage = (
                Usage(
                    input_tokens=usage_data.get("inputTokens", 0),
                    output_tokens=usage_data.get("outputTokens", 0),
                )
                if usage_data
                else None
            )
            return ResultEvent(run_id=run_id, result=result, usage=usage)

        if event_tag == "error":
            return ErrorEvent(
                run_id=run_id,
                code=payload.get("code") or "internal_error",
                message=(
                    payload.get("message")
                    or payload.get("details")
                    or payload.get("error")
                    or "Unknown error"
                ),
                details=payload.get("details") if isinstance(
                    payload.get("details"), dict
                )
                else None,
            )

        # No event tag — OpenAI-compat delta chunk.
        choices = payload.get("choices", [])
        if choices:
            content = choices[0].get("delta", {}).get("content")
            if content:
                return DeltaEvent(run_id=run_id, content=content)

        # Bare `{"runId": "…"}` (or legacy `{"run_id": …}`) frames — synthesize started.
        if "runId" in payload:
            return StartedEvent(run_id=payload["runId"])
        if "run_id" in payload:
            return StartedEvent(run_id=payload["run_id"])

        return None

    # ------------------------------------------------------------------
    # JSON → dataclass parsing
    # ------------------------------------------------------------------

    def _parse_run(self, data: Dict[str, Any]) -> Run:
        result = None
        if "result" in data and data["result"]:
            r = data["result"]
            result = RunResult(
                answer=r.get("answer", ""),
                reasoning=_parse_reasoning_list(r.get("reasoning")),
            )

        usage = None
        if "usage" in data and data["usage"]:
            u = data["usage"]
            if isinstance(u, dict) and ("inputTokens" in u or "input_tokens" in u):
                usage = Usage(
                    input_tokens=u.get("inputTokens", u.get("input_tokens", 0)),
                    output_tokens=u.get("outputTokens", u.get("output_tokens", 0)),
                )

        return Run(
            run_id=data.get("runId", data.get("run_id", "")),
            status=data.get("status"),
            result=result,
            usage=usage,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_tool_use(data: Any) -> Optional[ToolUse]:
    if not isinstance(data, dict):
        return None
    return ToolUse(
        tool_name=data.get("tool_name") or data.get("name") or "",
        parameters=data.get("parameters"),
        tool_result=data.get("tool_result"),
    )


def _parse_reasoning_node(data: Any) -> Optional[ReasoningNode]:
    if not isinstance(data, dict):
        return None
    return ReasoningNode(
        title=data.get("title", ""),
        thought=data.get("thought", ""),
        tooluse=_parse_tool_use(data.get("tooluse")),
        subtasks=_parse_reasoning_list(data.get("subtasks")) or [],
        conclusion=data.get("conclusion", ""),
    )


def _parse_reasoning_list(data: Any) -> Optional[List[ReasoningNode]]:
    if not isinstance(data, list):
        return None
    out: List[ReasoningNode] = []
    for item in data:
        node = _parse_reasoning_node(item)
        if node is not None:
            out.append(node)
    return out
