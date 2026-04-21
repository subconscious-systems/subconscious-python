"""Tests for the ToolResponse envelope + builder."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from subconscious import Image, ImageContent, TextContent, ToolResponse

PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def test_build_from_string():
    resp = ToolResponse.build('tc_1', 'done')
    dumped = resp.model_dump(mode='json', exclude_none=True)
    assert dumped == {
        'tool_call_id': 'tc_1',
        'content': [{'type': 'text', 'text': 'done'}],
        'is_error': False,
    }


def test_build_from_image():
    resp = ToolResponse.build('tc_1', Image.from_bytes(PNG_BYTES))
    assert len(resp.content) == 1
    block = resp.content[0]
    assert isinstance(block, ImageContent)
    assert block.source.kind == 'base64'
    assert block.source.mime == 'image/png'


def test_build_from_mixed_list():
    resp = ToolResponse.build('tc_1', ['here:', Image.from_bytes(PNG_BYTES)])
    assert len(resp.content) == 2
    assert isinstance(resp.content[0], TextContent)
    assert resp.content[0].text == 'here:'
    assert isinstance(resp.content[1], ImageContent)


def test_build_preserves_is_error():
    resp = ToolResponse.build('tc_err', 'rate limited', is_error=True)
    assert resp.is_error is True


def test_strict_constructor_round_trip():
    resp = ToolResponse(
        tool_call_id='tc_1',
        content=[
            TextContent(type='text', text='hi'),
            Image.from_bytes(PNG_BYTES),
        ],
    )
    assert resp.model_dump(mode='json', exclude_none=True)['content'][0] == {
        'type': 'text',
        'text': 'hi',
    }


def test_rejects_unsupported_mime():
    with pytest.raises(ValidationError):
        ToolResponse(
            tool_call_id='tc_1',
            content=[
                {
                    'type': 'image',
                    'source': {'kind': 'base64', 'data': 'AAA', 'mime': 'image/bmp'},
                },
            ],
        )
