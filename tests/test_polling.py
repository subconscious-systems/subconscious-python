"""Tests for client.wait() polling behavior and end-to-end
client.run(..., await_completion=True) flow. Mocks the HTTP layer
(``client._request``) so the actual request loop is exercised."""

import contextlib
from unittest.mock import patch

import pytest

from subconscious.client import Subconscious
from subconscious.types import RunOptions


def _request_sequence(responses):
    """Build a side_effect callable that returns each response in order,
    recording every call for assertion."""
    calls = []
    iterator = iter(responses)
    last = [None]

    def fake(method, path, payload=None):
        calls.append({'method': method, 'path': path, 'payload': payload})
        with contextlib.suppress(StopIteration):
            last[0] = next(iterator)
        return last[0]

    return fake, calls


class TestWaitPolling:
    def test_polls_through_non_terminal_states_until_terminal(self):
        client = Subconscious(api_key='test-key')
        fake, calls = _request_sequence(
            [
                {'runId': 'r-1', 'status': 'queued'},
                {'runId': 'r-1', 'status': 'running'},
                {'runId': 'r-1', 'status': 'running'},
                {
                    'runId': 'r-1',
                    'status': 'succeeded',
                    'result': {'answer': 'done'},
                },
            ]
        )

        with patch.object(client, '_request', side_effect=fake):
            run = client.wait('r-1', {'interval_ms': 0})

        assert run.status == 'succeeded'
        assert run.result.answer == 'done'
        assert len(calls) == 4
        for c in calls:
            assert c == {'method': 'GET', 'path': '/runs/r-1', 'payload': None}

    def test_returns_failed_run_without_throwing(self):
        client = Subconscious(api_key='test-key')
        fake, _calls = _request_sequence(
            [
                {
                    'runId': 'r-2',
                    'status': 'failed',
                    'error': {'code': 'engine_error', 'message': 'boom'},
                }
            ]
        )
        with patch.object(client, '_request', side_effect=fake):
            run = client.wait('r-2', {'interval_ms': 0})

        assert run.status == 'failed'
        assert run.error.code == 'engine_error'

    @pytest.mark.parametrize('terminal_status', ['succeeded', 'failed', 'canceled', 'timed_out'])
    def test_each_terminal_status_exits_loop(self, terminal_status):
        client = Subconscious(api_key='test-key')
        fake, calls = _request_sequence([{'runId': 'r-t', 'status': terminal_status}])
        with patch.object(client, '_request', side_effect=fake):
            run = client.wait('r-t', {'interval_ms': 0})
        assert run.status == terminal_status
        assert len(calls) == 1  # single GET, no extra iterations

    def test_raises_timeout_when_max_attempts_exhausted(self):
        client = Subconscious(api_key='test-key')
        fake, _calls = _request_sequence([{'runId': 'r-3', 'status': 'running'}] * 10)
        with (
            patch.object(client, '_request', side_effect=fake),
            pytest.raises(TimeoutError, match='exceeded max attempts'),
        ):
            client.wait('r-3', {'interval_ms': 0, 'max_attempts': 3})

    def test_accepts_poll_options_dataclass(self):
        from subconscious.types import PollOptions

        client = Subconscious(api_key='test-key')
        fake, _calls = _request_sequence([{'runId': 'r-4', 'status': 'succeeded'}])
        with patch.object(client, '_request', side_effect=fake):
            run = client.wait('r-4', PollOptions(interval_ms=0, max_attempts=5))
        assert run.status == 'succeeded'


class TestRunAwaitCompletionEndToEnd:
    def test_run_posts_then_polls_to_terminal(self):
        """client.run(..., await_completion=True) should POST /runs,
        then poll GET /runs/:id until terminal, and return the final Run."""
        client = Subconscious(api_key='test-key')
        call_log = []

        def fake(method, path, payload=None):
            call_log.append({'method': method, 'path': path})
            if method == 'POST' and path == '/runs':
                return {'runId': 'r-end'}
            if method == 'GET' and path == '/runs/r-end':
                # Progress through states based on number of prior GETs.
                get_count = sum(
                    1 for c in call_log if c['method'] == 'GET' and c['path'] == '/runs/r-end'
                )
                if get_count == 1:
                    return {'runId': 'r-end', 'status': 'queued'}
                if get_count == 2:
                    return {'runId': 'r-end', 'status': 'running'}
                return {
                    'runId': 'r-end',
                    'status': 'succeeded',
                    'result': {'answer': '42'},
                }
            raise AssertionError(f'unexpected call {method} {path}')

        with (
            patch.object(client, '_request', side_effect=fake),
            patch('subconscious.client.time.sleep'),
        ):
            # Patch time.sleep so the default 1000ms interval inside wait()
            # doesn't stall the test (run() calls wait() without options).
            run = client.run(
                'tim',
                {'instructions': 'hi'},
                RunOptions(await_completion=True),
            )

        assert run.status == 'succeeded'
        assert run.result.answer == '42'
        # 1 POST + 3 GET polls = 4 calls total
        assert len(call_log) == 4
        assert call_log[0] == {'method': 'POST', 'path': '/runs'}
        for c in call_log[1:]:
            assert c == {'method': 'GET', 'path': '/runs/r-end'}

    def test_run_without_await_completion_does_not_poll(self):
        """When await_completion is absent/False, run() should return
        immediately with only run_id — no GET calls."""
        client = Subconscious(api_key='test-key')
        call_log = []

        def fake(method, path, payload=None):
            call_log.append({'method': method, 'path': path})
            return {'runId': 'r-nowait'}

        with patch.object(client, '_request', side_effect=fake):
            run = client.run('tim', {'instructions': 'hi'})

        assert run.run_id == 'r-nowait'
        assert len(call_log) == 1
        assert call_log[0] == {'method': 'POST', 'path': '/runs'}


class TestParsedAnswerIntegration:
    """The SDK attaches a best-effort ``parsed_answer`` on every response
    path that flows through ``_parse_run`` (``get``, ``wait``, ``cancel``,
    and transitively ``run(..., await_completion=True)``)."""

    def test_get_populates_parsed_answer_when_answer_is_json(self):
        client = Subconscious(api_key='test-key')
        fake, _ = _request_sequence(
            [
                {
                    'runId': 'r-json',
                    'status': 'succeeded',
                    'result': {'answer': '{"name":"ada","age":36}'},
                }
            ]
        )
        with patch.object(client, '_request', side_effect=fake):
            run = client.get('r-json')

        assert run.result.answer == '{"name":"ada","age":36}'
        assert run.result.parsed_answer == {'name': 'ada', 'age': 36}

    def test_get_leaves_parsed_answer_none_when_answer_is_plain_text(self):
        client = Subconscious(api_key='test-key')
        fake, _ = _request_sequence(
            [{'runId': 'r-txt', 'status': 'succeeded', 'result': {'answer': 'free text'}}]
        )
        with patch.object(client, '_request', side_effect=fake):
            run = client.get('r-txt')

        assert run.result.answer == 'free text'
        assert run.result.parsed_answer is None

    def test_cancel_populates_parsed_answer(self):
        client = Subconscious(api_key='test-key')
        fake, _ = _request_sequence(
            [
                {
                    'runId': 'r-c',
                    'status': 'canceled',
                    'result': {'answer': '{"partial":true}'},
                }
            ]
        )
        with patch.object(client, '_request', side_effect=fake):
            run = client.cancel('r-c')

        assert run.status == 'canceled'
        assert run.result.parsed_answer == {'partial': True}

    def test_run_with_await_completion_populates_parsed_answer(self):
        client = Subconscious(api_key='test-key')
        call_log = []

        def fake(method, path, payload=None):
            call_log.append({'method': method, 'path': path})
            if method == 'POST':
                return {'runId': 'r-ac'}
            return {
                'runId': 'r-ac',
                'status': 'succeeded',
                'result': {'answer': '[1,2,3]'},
            }

        with (
            patch.object(client, '_request', side_effect=fake),
            patch('subconscious.client.time.sleep'),
        ):
            run = client.run(
                'tim',
                {'instructions': 'hi'},
                RunOptions(await_completion=True),
            )

        assert run.result.parsed_answer == [1, 2, 3]
