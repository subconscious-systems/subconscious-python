"""Tests for the multimodal Image helper and client serialization."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from subconscious import (
    Image,
    ImageContent,
    RequestTooLargeError,
)
from subconscious.client import (
    _build_input_dict,
    _check_request_size,
)

# 1x1 PNG (valid magic bytes).
PNG_HEAD = b'\x89PNG\r\n\x1a\n'
PNG_BYTES = PNG_HEAD + b'\x00' * 100


def test_image_from_bytes_detects_mime():
    img = Image.from_bytes(PNG_BYTES)
    assert isinstance(img, ImageContent)
    assert img.source.kind == 'base64'
    assert img.source.mime == 'image/png'
    # The data is raw base64 (no data: prefix)
    decoded = base64.b64decode(img.source.data)
    assert decoded == PNG_BYTES


def test_image_from_path(tmp_path: Path):
    p = tmp_path / 'shot.png'
    p.write_bytes(PNG_BYTES)
    img = Image.from_path(p)
    assert img.source.mime == 'image/png'


def test_image_from_url_default_does_not_fetch():
    img = Image.from_url('https://example.com/x.png')
    assert img.source.kind == 'url'
    # Pydantic's AnyUrl is not equal to a raw str — compare the string form.
    assert str(img.source.url) == 'https://example.com/x.png'


def test_image_from_blob_ref():
    img = Image.from_blob_ref(
        'org/00000000-0000-0000-0000-000000000000/run/r1/screenshot/x.png',
        mime='image/png',
    )
    assert img.source.kind == 'blob_ref'
    assert img.source.mime == 'image/png'


def test_image_rejects_non_image_bytes():
    with pytest.raises(ValueError, match='unsupported image type'):
        Image.from_bytes(b'not an image at all')


def test_image_rejects_disallowed_mime():
    with pytest.raises(ValueError, match='not allowed'):
        Image.from_bytes(b'whatever', mime='image/bmp')


def test_build_input_dict_serializes_pydantic_content():
    img = Image.from_bytes(PNG_BYTES)
    payload = _build_input_dict({'instructions': 'look', 'content': [img]})
    assert payload['content'][0]['type'] == 'image'
    assert payload['content'][0]['source']['kind'] == 'base64'
    # Serializable as JSON
    json.dumps(payload)


def test_check_request_size_rejects_oversize_payload():
    huge = 'x' * (6 * 1024 * 1024)
    payload = {'engine': 'tim-claude', 'input': {'instructions': huge, 'tools': []}}
    with pytest.raises(RequestTooLargeError):
        _check_request_size(payload)
