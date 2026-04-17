"""Tests for densify_trace.

The helper hits real HTTP endpoints (trace + presigned URL + R2). We mock all
three to keep the test offline and assert: walk picks up nested blob_keys,
parallel fetch happens with bounded concurrency, JSONL output is per-message.
"""

from __future__ import annotations

import base64
import io
import json
import threading
from typing import Any, Dict, List
from unittest.mock import patch

from subconscious.traces import (
    _replace_blob_refs_with_base64,
    _walk_blob_keys,
    densify_trace,
)


def test_walk_blob_keys_finds_deep_refs():
    trace = {
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'caption'},
                    {
                        'type': 'image',
                        'source': {'kind': 'blob_ref', 'blob_key': 'a', 'mime': 'image/png'},
                    },
                ],
            },
            {
                'role': 'tool',
                'tool_call_id': 'tc1',
                'content': [
                    {
                        'type': 'image',
                        'source': {'kind': 'blob_ref', 'blob_key': 'b', 'mime': 'image/png'},
                    },
                ],
            },
        ]
    }
    out: List[str] = []
    _walk_blob_keys(trace, out)
    assert out == ['a', 'b']


def test_replace_blob_refs_inlines_base64():
    msg = {
        'content': [
            {
                'type': 'image',
                'source': {'kind': 'blob_ref', 'blob_key': 'k1', 'mime': 'image/png'},
            },
        ]
    }
    dense = _replace_blob_refs_with_base64(msg, {'k1': 'aGVsbG8='})
    assert dense['content'][0]['source'] == {
        'kind': 'base64',
        'data': 'aGVsbG8=',
        'mime': 'image/png',
    }


class _FakeClient:
    """Minimum surface densify_trace pokes through: ``_base_url`` + ``_headers``."""

    def __init__(self) -> None:
        self._base_url = 'https://api.fake'

    def _headers(self) -> Dict[str, str]:
        return {'Authorization': 'Bearer test'}


def test_densify_trace_streams_jsonl_per_message():
    client = _FakeClient()

    blob_bytes = {
        'k1': b'image-bytes-1',
        'k2': b'image-bytes-2',
    }
    presigned_urls = {
        'k1': 'https://r2.fake/k1?sig=...',
        'k2': 'https://r2.fake/k2?sig=...',
    }

    trace_payload = {
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'first'},
                    {'type': 'image', 'source': {'kind': 'blob_ref', 'blob_key': 'k1', 'mime': 'image/png'}},
                ],
            },
            {
                'role': 'tool',
                'content': [
                    {'type': 'image', 'source': {'kind': 'blob_ref', 'blob_key': 'k2', 'mime': 'image/png'}},
                ],
            },
        ],
    }

    def fake_get(url: str, headers: Any = None, timeout: int = 0) -> Any:
        class _Resp:
            def __init__(self, payload: Any, content: bytes = b''):
                self._payload = payload
                self.content = content

            def raise_for_status(self) -> None:  # noqa: D401
                return None

            def json(self) -> Any:
                return self._payload

        if url.endswith('/runs/run-1'):
            return _Resp(trace_payload)
        for key, signed in presigned_urls.items():
            if url.endswith(f'/assets/{key}/url'):
                return _Resp({'url': signed, 'expiresAt': '2099-01-01T00:00:00Z'})
            if url == signed:
                return _Resp(None, content=blob_bytes[key])
        raise AssertionError(f'unexpected URL: {url}')

    out = io.StringIO()
    with patch('subconscious.traces.requests.get', side_effect=fake_get):
        with patch('subconscious.traces._fetch_bytes') as fb:
            fb.side_effect = lambda url, timeout=30: next(
                blob_bytes[k] for k, v in presigned_urls.items() if v == url
            )
            densify_trace(client, 'run-1', output=out)

    lines = [json.loads(line) for line in out.getvalue().splitlines() if line]
    assert len(lines) == 2

    # Each blob_ref turned into base64.
    assert lines[0]['content'][1]['source'] == {
        'kind': 'base64',
        'data': base64.b64encode(blob_bytes['k1']).decode(),
        'mime': 'image/png',
    }
    assert lines[1]['content'][0]['source'] == {
        'kind': 'base64',
        'data': base64.b64encode(blob_bytes['k2']).decode(),
        'mime': 'image/png',
    }


def test_densify_trace_returns_string_when_no_output():
    client = _FakeClient()

    trace_payload = {'messages': [{'role': 'user', 'content': 'hi'}]}

    def fake_get(url: str, headers: Any = None, timeout: int = 0) -> Any:
        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> Any:
                return trace_payload

        return _Resp()

    with patch('subconscious.traces.requests.get', side_effect=fake_get):
        result = densify_trace(client, 'run-x', output=None)

    assert isinstance(result, str)
    assert json.loads(result.strip())['role'] == 'user'


def test_densify_trace_concurrency_bounded():
    """Fetches dispatch in parallel up to the concurrency limit."""
    client = _FakeClient()
    n_blobs = 6

    trace_payload: Dict[str, Any] = {
        'messages': [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'kind': 'blob_ref',
                            'blob_key': f'k{i}',
                            'mime': 'image/png',
                        },
                    }
                    for i in range(n_blobs)
                ],
            }
        ]
    }

    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def fake_get(url: str, headers: Any = None, timeout: int = 0) -> Any:
        class _Resp:
            def __init__(self, payload: Any):
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> Any:
                return self._payload

        if url.endswith('/runs/run-c'):
            return _Resp(trace_payload)
        return _Resp({'url': url + '?signed', 'expiresAt': '2099-01-01T00:00:00Z'})

    def fake_fetch(url: str, timeout: int = 30) -> bytes:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        # Just enough work that overlap is observable.
        import time
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return b'x'

    with patch('subconscious.traces.requests.get', side_effect=fake_get):
        with patch('subconscious.traces._fetch_bytes', side_effect=fake_fetch):
            densify_trace(client, 'run-c', output=io.StringIO(), concurrency=3)

    # We capped concurrency at 3; max in-flight should not exceed it.
    assert max_in_flight <= 3
    # And at least 2 should have overlapped — otherwise we're effectively serial.
    assert max_in_flight >= 2
