"""Subconscious API client."""

import json
import time
from typing import Any, Dict, Generator, List, Optional, Union

import requests

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

TERMINAL_STATUSES: List[RunStatus] = ["succeeded", "failed", "canceled", "timed_out"]


class Subconscious:
    """
    The main Subconscious API client.

    Example:
        ```python
        from subconscious import Subconscious

        client = Subconscious(api_key="your-api-key")

        run = client.run(
            engine="tim-large",
            input={
                "instructions": "Search for the latest news about AI",
                "tools": [{"type": "platform", "id": "parallel_search"}],
            },
            options={"await_completion": True},
        )

        print(run.result.answer)
        ```
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.subconscious.dev/v1",
    ):
        """
        Initialize the Subconscious client.

        Args:
            api_key: Your Subconscious API key
            base_url: API base URL (default: https://api.subconscious.dev/v1)
        """
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
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
            engine: The engine to use ("tim-large" or "tim-small-preview")
            input: Input configuration with instructions and tools
            options: Optional run options (await_completion, etc.)

        Returns:
            The created run, with results if await_completion is True

        Example:
            ```python
            run = client.run(
                engine="tim-large",
                input={
                    "instructions": "Search for AI news",
                    "tools": [{"type": "platform", "id": "parallel_search"}],
                },
                options={"await_completion": True},
            )
            ```
        """
        # Normalize input
        if isinstance(input, RunInput):
            input_dict = {"instructions": input.instructions, "tools": input.tools}
        else:
            input_dict = input

        # Normalize tools to dicts
        tools = input_dict.get("tools", [])
        normalized_tools = []
        for tool in tools:
            if hasattr(tool, "__dict__"):
                normalized_tools.append(
                    {k: v for k, v in tool.__dict__.items() if v is not None}
                )
            else:
                normalized_tools.append(tool)
        input_dict["tools"] = normalized_tools

        # Make request
        data = self._request(
            "POST",
            "/runs",
            {"engine": engine, "input": input_dict},
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
            input: Input configuration with instructions and tools

        Yields:
            StreamEvent: Delta, done, or error events

        Returns:
            The final run (if stream completes successfully)

        Example:
            ```python
            for event in client.stream(
                engine="tim-large",
                input={"instructions": "Write an essay", "tools": []},
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
        # Normalize input
        if isinstance(input, RunInput):
            input_dict = {"instructions": input.instructions, "tools": input.tools}
        else:
            input_dict = input

        # Normalize tools
        tools = input_dict.get("tools", [])
        normalized_tools = []
        for tool in tools:
            if hasattr(tool, "__dict__"):
                normalized_tools.append(
                    {k: v for k, v in tool.__dict__.items() if v is not None}
                )
            else:
                normalized_tools.append(tool)
        input_dict["tools"] = normalized_tools

        url = f"{self._base_url}/runs/stream"
        headers = {
            **self._headers(),
            "Accept": "text/event-stream",
        }

        response = requests.post(
            url,
            headers=headers,
            json={"engine": engine, "input": input_dict},
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
