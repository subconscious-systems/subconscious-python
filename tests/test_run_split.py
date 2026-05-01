"""Tests for the run / run_and_wait split (R18) and client overlay options (R9, R13)."""

import json
from unittest.mock import patch

from subconscious import Subconscious, tools
from subconscious.types import RunInput

try:
    from pydantic import BaseModel  # type: ignore[import-not-found]

    HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    HAS_PYDANTIC = False


class _FakeJSONResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = json.dumps(body)
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._body


def test_run_returns_immediately_R18():
    captured = {}

    def fake_request(method, url, headers=None, json=None):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json
        return _FakeJSONResponse({"runId": "run_abc"})

    with patch("subconscious.client.requests.request", side_effect=fake_request):
        client = Subconscious(api_key="k")
        run = client.run(engine="tim-claude", input={"instructions": "hi"})

    assert run.run_id == "run_abc"
    assert run.status is None
    assert run.result is None
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/runs")


def test_run_and_wait_polls_until_terminal_R18():
    poll_count = {"n": 0}

    def fake_request(method, url, headers=None, json=None):
        if method == "POST":
            return _FakeJSONResponse({"runId": "run_xyz"})
        # GET poll
        poll_count["n"] += 1
        if poll_count["n"] < 2:
            return _FakeJSONResponse({"runId": "run_xyz", "status": "running"})
        return _FakeJSONResponse(
            {
                "runId": "run_xyz",
                "status": "succeeded",
                "result": {"answer": "done", "reasoning": None},
            }
        )

    with patch("subconscious.client.requests.request", side_effect=fake_request):
        client = Subconscious(api_key="k")
        run = client.run_and_wait(
            engine="tim-claude",
            input={"instructions": "hi"},
            poll_options={"interval_ms": 1},
        )

    assert run.status == "succeeded"
    assert run.result is not None
    assert run.result.answer == "done"
    assert poll_count["n"] >= 2


def test_default_function_tool_headers_overlay_R9():
    captured = {}

    def fake_request(method, url, headers=None, json=None):
        captured["body"] = json
        return _FakeJSONResponse({"runId": "r"})

    with patch("subconscious.client.requests.request", side_effect=fake_request):
        client = Subconscious(
            api_key="k",
            default_function_tool_headers={"Authorization": "Bearer xyz"},
        )
        client.run(
            engine="tim-claude",
            input={
                "instructions": "hi",
                "tools": [
                    tools.function(
                        name="send",
                        url="https://api.example.com",
                        parameters={"type": "object", "properties": {}, "required": []},
                    )
                ],
            },
        )

    sent_tools = captured["body"]["input"]["tools"]
    assert sent_tools[0]["headers"] == {"Authorization": "Bearer xyz"}


def test_runinput_dataclass_input_supports_resources_skills_agent_id_R1():
    captured = {}

    def fake_request(method, url, headers=None, json=None):
        captured["body"] = json
        return _FakeJSONResponse({"runId": "r"})

    with patch("subconscious.client.requests.request", side_effect=fake_request):
        client = Subconscious(api_key="k")
        client.run(
            engine="tim-claude",
            input=RunInput(
                instructions="hi",
                images=["data:image/png;base64,iVBORw0K"],
                skills=["skill_42"],
                agent_id="agent_x",
            ),
        )

    body_input = captured["body"]["input"]
    assert body_input["images"] == ["data:image/png;base64,iVBORw0K"]
    assert body_input["skills"] == ["skill_42"]
    assert body_input["agentId"] == "agent_x"


if HAS_PYDANTIC:

    def test_run_accepts_pydantic_answer_format_R13():
        captured = {}

        def fake_request(method, url, headers=None, json=None):
            captured["body"] = json
            return _FakeJSONResponse({"runId": "r"})

        class Result(BaseModel):  # type: ignore[misc]
            summary: str
            score: float

        with patch("subconscious.client.requests.request", side_effect=fake_request):
            client = Subconscious(api_key="k")
            client.run(
                engine="tim-claude",
                input={"instructions": "hi", "answerFormat": Result},
            )

        af = captured["body"]["input"]["answerFormat"]
        assert af["type"] == "object"
        assert set(af["properties"].keys()) == {"summary", "score"}
