"""Tests for Stream Events v2 parsing in the Python SDK (R5, R8, R15, R16)."""

from typing import List
from unittest.mock import patch

from subconscious import Subconscious, StreamEvent
from subconscious.types import (
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    ResultEvent,
    StartedEvent,
    ToolCallEvent,
)


class _FakeResponse:
    """Minimal stand-in for ``requests.Response`` used in stream tests."""

    def __init__(self, lines, status_code=200, headers=None):
        self._lines = lines
        self.status_code = status_code
        self.headers = headers or {}
        self.text = ""

    def iter_lines(self, decode_unicode=True):  # noqa: D401
        for line in self._lines:
            yield line

    def json(self):
        return {}


def _frames_to_lines(frames: List[str]) -> List[str]:
    """Split SSE frames into the per-line iteration ``requests`` would produce."""
    out: List[str] = []
    for f in frames:
        for line in f.split("\n"):
            out.append(line)
    return out


def test_stream_emits_started_first_R8():
    """Canonical wire shape uses camelCase ``runId`` (matches REST responses)."""
    frames = [
        "event: meta\ndata: {\"runId\":\"run_abc\"}\n\n",
        "data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n",
        "event: result\ndata: {\"result\":{\"answer\":\"hi\",\"reasoning\":null}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "run_abc"})

    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    assert isinstance(events[0], StartedEvent)
    assert events[0].run_id == "run_abc"
    assert isinstance(events[-1], DoneEvent)
    types = [type(e) for e in events]
    assert DeltaEvent in types
    assert ResultEvent in types


def test_stream_back_compat_legacy_run_id_snake_case():
    """Older API builds emitted snake_case ``run_id``. SDKs MUST keep
    accepting the legacy shape for at least one minor release."""
    frames = [
        "event: started\ndata: {\"run_id\":\"r_legacy\"}\n\n",
        "event: result\ndata: {\"result\":{\"answer\":\"ok\",\"reasoning\":null}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "r_legacy"})
    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    assert isinstance(events[0], StartedEvent)
    assert events[0].run_id == "r_legacy"


def test_stream_parses_canceled_error_code_one_l():
    """Canonical spelling is ``canceled`` (one ``l``) — matches RunStatus."""
    frames = [
        "event: started\ndata: {\"runId\":\"r1\"}\n\n",
        "event: error\ndata: {\"code\":\"canceled\","
        "\"message\":\"The run was canceled\"}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "r1"})
    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].code == "canceled"


def test_stream_parses_result_with_usage_R15():
    frames = [
        "event: started\ndata: {\"run_id\":\"r1\"}\n\n",
        "event: result\ndata: {\"result\":{\"answer\":\"42\",\"reasoning\":null},"
        "\"usage\":{\"inputTokens\":1,\"outputTokens\":2}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "r1"})

    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    result_events = [e for e in events if isinstance(e, ResultEvent)]
    assert len(result_events) == 1
    re = result_events[0]
    assert re.result is not None
    assert re.result.answer == "42"
    assert re.usage is not None
    assert re.usage.input_tokens == 1
    assert re.usage.output_tokens == 2


def test_stream_parses_tool_call_R15():
    frames = [
        "event: started\ndata: {\"run_id\":\"r1\"}\n\n",
        "event: tool_call\ndata: {\"call\":{\"tool_name\":\"web_search\","
        "\"parameters\":{\"q\":\"x\"},\"tool_result\":{\"docs\":[]}}}\n\n",
        "event: result\ndata: {\"result\":{\"answer\":\"done\",\"reasoning\":null}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "r1"})

    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 1
    assert tool_calls[0].call is not None
    assert tool_calls[0].call.tool_name == "web_search"


def test_stream_parses_error_with_required_code_R5():
    frames = [
        "event: started\ndata: {\"run_id\":\"r1\"}\n\n",
        "event: error\ndata: {\"code\":\"rate_limited\",\"message\":\"slow down\","
        "\"details\":{\"retryAfterMs\":1000}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames), headers={"x-run-id": "r1"})

    with patch("subconscious.client.requests.post", return_value=fake):
        client = Subconscious(api_key="k")
        events = list(client.stream(engine="tim-claude", input={"instructions": "hi"}))

    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    err = errors[0]
    assert err.code == "rate_limited"
    assert err.message == "slow down"
    assert err.details == {"retryAfterMs": 1000}


def test_observe_reads_run_stream_endpoint_R16():
    frames = [
        "event: started\ndata: {\"run_id\":\"r_obs\"}\n\n",
        "data: {\"choices\":[{\"delta\":{\"content\":\"replay\"}}]}\n\n",
        "event: result\ndata: {\"result\":{\"answer\":\"replay\",\"reasoning\":null}}\n\n",
        "data: [DONE]\n\n",
    ]
    fake = _FakeResponse(_frames_to_lines(frames))

    with patch("subconscious.client.requests.get", return_value=fake) as mocked_get:
        client = Subconscious(api_key="k")
        events = list(client.observe("r_obs"))

    # Endpoint: GET /v1/runs/r_obs/stream
    call_url = mocked_get.call_args.args[0]
    assert call_url.endswith("/runs/r_obs/stream")

    types = [type(e) for e in events]
    assert StartedEvent in types
    assert DeltaEvent in types
    delta = next(e for e in events if isinstance(e, DeltaEvent))
    assert delta.content == "replay"
