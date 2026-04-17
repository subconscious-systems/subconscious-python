"""Tests for the multimodal Image helper and client serialization."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from subconscious import (
    EngineDoesNotSupportImagesError,
    Image,
    ImageContent,
    RequestTooLargeError,
    TextContent,
    engine_supports_images,
)
from subconscious.client import (
    _build_input_dict,
    _check_capabilities_and_size,
    _content_has_images,
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


def test_content_has_images_handles_pydantic_and_dict():
    text_block = TextContent(type='text', text='hi')
    image_block = Image.from_bytes(PNG_BYTES)
    assert _content_has_images([text_block]) is False
    assert _content_has_images([text_block, image_block]) is True
    assert _content_has_images([{'type': 'image', 'source': {}}]) is True
    assert _content_has_images([]) is False
    assert _content_has_images(None) is False


def test_engine_supports_images_snapshot():
    assert engine_supports_images('tim-claude') is True
    assert engine_supports_images('tim-gpt') is True
    assert engine_supports_images('timini') is True
    assert engine_supports_images('tim') is True
    assert engine_supports_images('tim-edge') is True
    # Non-image engines from the snapshot
    assert engine_supports_images('tim-oss-local') is False
    assert engine_supports_images('tim-1.5') is False
    # Unknown engine — fail closed
    assert engine_supports_images('unknown-engine') is False


def test_build_input_dict_serializes_pydantic_content():
    img = Image.from_bytes(PNG_BYTES)
    payload = _build_input_dict({'instructions': 'look', 'content': [img]})
    assert payload['content'][0]['type'] == 'image'
    assert payload['content'][0]['source']['kind'] == 'base64'
    # Serializable as JSON
    json.dumps(payload)


def test_check_capabilities_rejects_image_on_text_only_engine():
    img = Image.from_bytes(PNG_BYTES)
    payload = {'engine': 'tim-oss-local', 'input': _build_input_dict({'instructions': 'x', 'content': [img]})}
    with pytest.raises(EngineDoesNotSupportImagesError):
        _check_capabilities_and_size('tim-oss-local', payload)


def test_check_capabilities_passes_for_capable_engine():
    img = Image.from_bytes(PNG_BYTES)
    payload = {'engine': 'tim-claude', 'input': _build_input_dict({'instructions': 'x', 'content': [img]})}
    _check_capabilities_and_size('tim-claude', payload)  # no raise


def test_check_capabilities_rejects_oversize_payload():
    huge = 'x' * (6 * 1024 * 1024)
    payload = {'engine': 'tim-claude', 'input': {'instructions': huge, 'tools': []}}
    with pytest.raises(RequestTooLargeError):
        _check_capabilities_and_size('tim-claude', payload)
