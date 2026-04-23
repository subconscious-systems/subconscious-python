"""Tests for skills on RunInput and the widened RunOptions (timeout,
max_step_tokens, output) — including wire-format serialization and the
guarantee that client-side ``await_completion`` is stripped from the body."""

from unittest.mock import MagicMock, patch

from subconscious.client import Subconscious
from subconscious.types import (
    CreateRunBody,
    RunInput,
    RunInputWire,
    RunOptions,
    RunOutput,
)


class TestSkillsRoundTrip:
    def test_skills_from_dataclass_input(self):
        wire = RunInputWire.from_run_input(
            RunInput(instructions='hi', skills=['web-search', 'python'])
        )
        d = wire.model_dump(by_alias=True, exclude_none=True)
        assert d['skills'] == ['web-search', 'python']

    def test_skills_from_dict_input(self):
        wire = RunInputWire.from_run_input({'instructions': 'hi', 'skills': ['s1']})
        d = wire.model_dump(by_alias=True, exclude_none=True)
        assert d['skills'] == ['s1']

    def test_no_skills_key_when_absent(self):
        wire = RunInputWire.from_run_input({'instructions': 'hi'})
        d = wire.model_dump(by_alias=True, exclude_none=True)
        assert 'skills' not in d

    def test_empty_skills_list_is_normalized_to_none(self):
        # ``skills or None`` in from_run_input collapses [] → None so the
        # wire omits the key entirely (no benefit to sending an empty array).
        wire = RunInputWire.from_run_input({'instructions': 'hi', 'skills': []})
        d = wire.model_dump(by_alias=True, exclude_none=True)
        assert 'skills' not in d


class TestServerOptionsSerialization:
    def test_timeout_and_max_step_tokens_on_wire(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            RunOptions(timeout=120, max_step_tokens=1000),
        )
        d = body.to_dict()
        assert d['options'] == {'timeout': 120, 'max_step_tokens': 1000}

    def test_dict_options_accepted(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            {'timeout': 60, 'max_step_tokens': 300},
        )
        assert body.to_dict()['options'] == {'timeout': 60, 'max_step_tokens': 300}

    def test_partial_options_only_includes_set_fields(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, RunOptions(timeout=30))
        assert body.to_dict()['options'] == {'timeout': 30}

    def test_no_options_key_when_only_await_completion_set(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, RunOptions(await_completion=True))
        assert 'options' not in body.to_dict()

    def test_no_options_key_when_options_is_none(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, None)
        assert 'options' not in body.to_dict()


class TestOutputBlockSerialization:
    def test_output_camelcase_on_wire(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            RunOptions(
                output=RunOutput(
                    callback_url='https://example.com/hook',
                    response_content='answer_only',
                )
            ),
        )
        d = body.to_dict()
        assert d['output'] == {
            'callbackUrl': 'https://example.com/hook',
            'responseContent': 'answer_only',
        }

    def test_output_from_dict_accepts_snake_case(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            {'output': {'callback_url': 'https://x.com', 'response_content': 'full'}},
        )
        assert body.to_dict()['output'] == {
            'callbackUrl': 'https://x.com',
            'responseContent': 'full',
        }

    def test_output_from_dict_accepts_camel_case(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            {'output': {'callbackUrl': 'https://x.com', 'responseContent': 'full'}},
        )
        assert body.to_dict()['output'] == {
            'callbackUrl': 'https://x.com',
            'responseContent': 'full',
        }

    def test_partial_output_only_includes_set_fields(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            RunOptions(output=RunOutput(response_content='full')),
        )
        assert body.to_dict()['output'] == {'responseContent': 'full'}

    def test_no_output_key_when_unset(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, RunOptions(timeout=10))
        assert 'output' not in body.to_dict()


class TestAwaitCompletionStripped:
    def test_await_completion_never_appears_on_wire(self):
        body = CreateRunBody.build(
            'tim',
            {'instructions': 'hi'},
            RunOptions(await_completion=True, timeout=30, max_step_tokens=500),
        )
        import json

        serialized = json.dumps(body.to_dict())
        assert 'await_completion' not in serialized
        assert 'awaitCompletion' not in serialized
        # Server-side fields still make it through.
        assert body.to_dict()['options'] == {'timeout': 30, 'max_step_tokens': 500}

    def test_await_completion_triggers_wait(self):
        client = Subconscious(api_key='test-key')
        with (
            patch.object(client, '_request', return_value={'runId': 'r-1'}),
            patch.object(client, 'wait') as mock_wait,
        ):
            mock_wait.return_value = MagicMock(run_id='r-1', status='succeeded')
            client.run(
                'tim',
                {'instructions': 'hi'},
                RunOptions(await_completion=True),
            )
            mock_wait.assert_called_once_with('r-1')

    def test_no_wait_when_await_completion_false(self):
        client = Subconscious(api_key='test-key')
        with (
            patch.object(client, '_request', return_value={'runId': 'r-1'}),
            patch.object(client, 'wait') as mock_wait,
        ):
            result = client.run('tim', {'instructions': 'hi'})
            mock_wait.assert_not_called()
            assert result.run_id == 'r-1'


class TestMinimalBody:
    def test_empty_options_produces_engine_plus_input_only(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, None)
        d = body.to_dict()
        assert set(d.keys()) == {'engine', 'input'}
        assert d['engine'] == 'tim'
        assert d['input'] == {'instructions': 'hi', 'tools': []}

    def test_run_options_with_defaults_only_produces_minimal_body(self):
        body = CreateRunBody.build('tim', {'instructions': 'hi'}, RunOptions())
        assert set(body.to_dict().keys()) == {'engine', 'input'}


class TestPassthroughFromClient:
    def test_client_run_sends_full_body(self):
        client = Subconscious(api_key='test-key')
        captured: dict = {}

        def fake_request(method, path, payload=None):
            captured['payload'] = payload
            return {'runId': 'r-1'}

        with patch.object(client, '_request', side_effect=fake_request):
            client.run(
                'tim',
                RunInput(instructions='hi', skills=['web-search']),
                RunOptions(
                    await_completion=False,
                    timeout=90,
                    max_step_tokens=700,
                    output=RunOutput(callback_url='https://x.com'),
                ),
            )

        payload = captured['payload']
        assert payload['input']['skills'] == ['web-search']
        assert payload['options'] == {'timeout': 90, 'max_step_tokens': 700}
        assert payload['output'] == {'callbackUrl': 'https://x.com'}
        import json

        assert 'await_completion' not in json.dumps(payload)
