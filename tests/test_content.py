"""Tests for the multimodal Image helper and client serialization."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from subconscious import (
    CreateRunBody,
    Image,
    ImageContent,
    PlatformTool,
    RequestTooLargeError,
    RunInput,
    RunInputWire,
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


def test_oversize_payload_rejected():
    huge = 'x' * (6 * 1024 * 1024)
    body = CreateRunBody.build(engine='tim-claude', input={'instructions': huge, 'tools': []})
    with pytest.raises(RequestTooLargeError):
        body.to_dict()


# ---------------------------------------------------------------------------
# RunInputWire / CreateRunBody — wire-format Pydantic models
# ---------------------------------------------------------------------------


class TestRunInputWire:
    def test_from_dict_basic(self):
        wire = RunInputWire.from_run_input(
            {
                'instructions': 'do stuff',
                'tools': [{'type': 'platform', 'id': 'fast_search'}],
            }
        )
        assert wire.instructions == 'do stuff'
        assert wire.tools == [{'type': 'platform', 'id': 'fast_search'}]
        assert wire.answer_format is None

    def test_from_dict_with_pydantic_schema(self):
        class MyFormat(BaseModel):
            answer: str

        wire = RunInputWire.from_run_input(
            {
                'instructions': 'go',
                'answerFormat': MyFormat,
            }
        )
        assert wire.answer_format is not None
        assert 'properties' in wire.answer_format
        assert 'answer' in wire.answer_format['properties']

    def test_from_run_input_dataclass(self):
        inp = RunInput(
            instructions='hello',
            tools=[PlatformTool(id='fast_search')],
        )
        wire = RunInputWire.from_run_input(inp)
        assert wire.instructions == 'hello'
        assert wire.tools[0]['type'] == 'platform'
        assert wire.tools[0]['id'] == 'fast_search'

    def test_model_dump_uses_camel_case(self):
        class Schema(BaseModel):
            value: int

        wire = RunInputWire.from_run_input(
            {
                'instructions': 'test',
                'answerFormat': Schema,
            }
        )
        dumped = wire.model_dump(by_alias=True, exclude_none=True)
        assert 'answerFormat' in dumped
        assert 'answer_format' not in dumped

    def test_none_fields_excluded(self):
        wire = RunInputWire.from_run_input({'instructions': 'minimal'})
        dumped = wire.model_dump(by_alias=True, exclude_none=True)
        assert 'answerFormat' not in dumped
        assert 'content' not in dumped
        assert 'instructions' in dumped
        assert 'tools' in dumped

    def test_content_blocks_serialized(self):
        img = Image.from_bytes(PNG_BYTES)
        wire = RunInputWire.from_run_input(
            {
                'instructions': 'look',
                'content': [img],
            }
        )
        assert wire.content is not None
        assert wire.content[0]['type'] == 'image'
        assert wire.content[0]['source']['kind'] == 'base64'


class TestCreateRunBody:
    def test_build_and_to_dict(self):
        body = CreateRunBody.build(
            engine='tim-claude',
            input={'instructions': 'search', 'tools': []},
        )
        d = body.to_dict()
        assert d['engine'] == 'tim-claude'
        assert d['input']['instructions'] == 'search'
        assert d['input']['tools'] == []
        json.dumps(d)  # must be JSON-serializable

    def test_round_trip_with_content(self):
        img = Image.from_bytes(PNG_BYTES)
        body = CreateRunBody.build(
            engine='tim-edge',
            input={'instructions': 'look', 'content': [img]},
        )
        d = body.to_dict()
        assert d['input']['content'][0]['type'] == 'image'
        json.dumps(d)
