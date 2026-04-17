"""Trace densification — fetch a run's trace + all attachments and inline the
images as base64 in a single dense JSONL stream.

Use case: post-training data collection. The server keeps traces in pointer
form (small SSE frames, durable storage), but training pipelines want the full
multimodal context inline. ``densify_trace`` does the round-trip and writes
JSONL to whatever ``output`` you pass.

Design notes:
- Bounded concurrency on the blob fetches (default 8) — the dev API and R2
  both throttle, and runaway parallelism wastes file descriptors.
- Streaming write: we flush after every message and never hold more than the
  current message's resolved bytes in memory. Trace size scales linearly with
  message count, not total image bytes.
- Sync I/O (``requests``) so the helper works without an asyncio loop. Callers
  needing async can wrap each call in ``asyncio.to_thread``.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, TextIO, Union

import requests


DEFAULT_CONCURRENCY = 8


def _walk_blob_keys(node: Any, out: List[str]) -> None:
    """Collect every blob_key referenced under ImageContent(blob_ref) sources."""
    if isinstance(node, dict):
        if node.get('type') == 'image':
            source = node.get('source') or {}
            if source.get('kind') == 'blob_ref' and isinstance(source.get('blob_key'), str):
                out.append(source['blob_key'])
        for v in node.values():
            _walk_blob_keys(v, out)
    elif isinstance(node, list):
        for item in node:
            _walk_blob_keys(item, out)


def _replace_blob_refs_with_base64(node: Any, key_to_b64: Dict[str, str]) -> Any:
    """Return a copy of ``node`` with every blob_ref source rewritten to base64."""
    if isinstance(node, dict):
        if node.get('type') == 'image':
            source = node.get('source') or {}
            if source.get('kind') == 'blob_ref':
                blob_key = source.get('blob_key')
                if blob_key in key_to_b64:
                    return {
                        'type': 'image',
                        'source': {
                            'kind': 'base64',
                            'data': key_to_b64[blob_key],
                            'mime': source.get('mime', 'image/png'),
                        },
                    }
        return {k: _replace_blob_refs_with_base64(v, key_to_b64) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_blob_refs_with_base64(item, key_to_b64) for item in node]
    return node


def _fetch_bytes(url: str, *, timeout: int = 30) -> bytes:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def densify_trace(
    client: Any,
    run_id: str,
    *,
    output: Optional[TextIO] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> Optional[str]:
    """Densify a run's trace to JSONL.

    Args:
        client: A ``Subconscious`` client instance (used for API calls).
        run_id: The run to densify.
        output: A file-like object to stream JSONL into. If ``None``, returns
            the densified trace as a string instead.
        concurrency: Max parallel blob fetches (default 8).

    Returns:
        ``None`` when ``output`` is provided; otherwise the densified trace
        as a single string.
    """
    # Pull the trace. The Subconscious API exposes the trace via GET /v1/runs/{id}
    # — its full output blob includes the canonical message stream we need.
    api_base = client._base_url  # noqa: SLF001 — internal access intentional
    headers = client._headers()  # noqa: SLF001
    trace_resp = requests.get(f'{api_base}/runs/{run_id}', headers=headers, timeout=30)
    trace_resp.raise_for_status()
    trace = trace_resp.json()

    # Collect blob_keys referenced anywhere in the trace.
    blob_keys: List[str] = []
    _walk_blob_keys(trace, blob_keys)
    blob_keys = list(dict.fromkeys(blob_keys))  # de-dup, preserve order

    # Mint presigned URLs for each unique key, fetch in parallel.
    key_to_b64: Dict[str, str] = {}
    if blob_keys:
        urls: Dict[str, str] = {}
        for key in blob_keys:
            url_resp = requests.get(
                f'{api_base}/assets/{key}/url',
                headers=headers,
                timeout=15,
            )
            url_resp.raise_for_status()
            urls[key] = url_resp.json()['url']

        with ThreadPoolExecutor(max_workers=min(concurrency, len(blob_keys))) as pool:
            future_to_key = {
                pool.submit(_fetch_bytes, urls[key]): key for key in blob_keys
            }
            for fut in as_completed(future_to_key):
                key = future_to_key[fut]
                key_to_b64[key] = base64.b64encode(fut.result()).decode('ascii')

    # The trace may expose messages under different keys depending on output
    # format; we accept either ``messages`` or ``output`` and fall back to the
    # whole trace as a single record.
    messages: Union[List[Any], None] = None
    if isinstance(trace, dict):
        if isinstance(trace.get('messages'), list):
            messages = trace['messages']
        elif isinstance(trace.get('output'), dict) and isinstance(
            trace['output'].get('messages'), list
        ):
            messages = trace['output']['messages']

    if messages is None:
        dense = _replace_blob_refs_with_base64(trace, key_to_b64)
        line = json.dumps(dense)
        if output is None:
            return line + '\n'
        output.write(line + '\n')
        output.flush()
        return None

    if output is None:
        # No streaming target — collect into a single string. Memory cost is
        # one message at a time, same as the streaming path.
        chunks: List[str] = []
        for msg in messages:
            dense = _replace_blob_refs_with_base64(msg, key_to_b64)
            chunks.append(json.dumps(dense))
        return '\n'.join(chunks) + '\n'

    for msg in messages:
        dense = _replace_blob_refs_with_base64(msg, key_to_b64)
        output.write(json.dumps(dense) + '\n')
        output.flush()
    return None
