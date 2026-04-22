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


# ---------------------------------------------------------------------------
# Canonical wire-shape contract
# ---------------------------------------------------------------------------
#
# These assertions pin the exact JSON structure the SDK sends to the API
# for a tool response. They mirror the canonical ``ToolResponse`` /
# ``ContentBlock`` / ``ImageSource`` zod schemas in
# ``subconscious-monorepo/packages/common/schemas/index.ts``. If the
# monorepo schema changes, these fail first — keeping the two sides in
# sync without needing a live API round-trip.


def test_wire_shape_text_only():
    dumped = ToolResponse.build('tc_1', 'ok').model_dump(mode='json', exclude_none=True)
    assert set(dumped.keys()) == {'tool_call_id', 'content', 'is_error'}
    assert dumped['content'] == [{'type': 'text', 'text': 'ok'}]


def test_wire_shape_image_base64_source():
    dumped = ToolResponse.build('tc_1', Image.from_bytes(PNG_BYTES)).model_dump(
        mode='json', exclude_none=True
    )
    source = dumped['content'][0]['source']
    # Exactly the three keys the canonical ``ImageSourceBase64`` zod requires.
    assert set(source.keys()) == {'kind', 'data', 'mime'}
    assert source['kind'] == 'base64'
    assert source['mime'] == 'image/png'
    assert isinstance(source['data'], str) and source['data']


def test_wire_shape_image_url_source():
    from subconscious import Image as _Image

    dumped = ToolResponse.build('tc_1', _Image.from_url('https://example.com/x.png')).model_dump(
        mode='json', exclude_none=True
    )
    source = dumped['content'][0]['source']
    assert source['kind'] == 'url'
    assert source['url'] == 'https://example.com/x.png'


def test_wire_shape_image_blob_ref_source():
    from subconscious import Image as _Image

    dumped = ToolResponse.build(
        'tc_1',
        _Image.from_blob_ref('org/00000000-0000-0000-0000-000000000000/run/r/x.png', 'image/png'),
    ).model_dump(mode='json', exclude_none=True)
    source = dumped['content'][0]['source']
    assert source['kind'] == 'blob_ref'
    assert source['blob_key'].startswith('org/')
    assert source['mime'] == 'image/png'
    # Optional fields excluded when unset — keeps the wire payload compact.
    assert 'width' not in source
    assert 'height' not in source
    assert 'attachment_id' not in source
