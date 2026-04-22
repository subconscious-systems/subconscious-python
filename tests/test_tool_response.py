"""Tests for the ToolResponse envelope + builder."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from subconscious import (
    AudioContent,
    FileContent,
    Image,
    ImageContent,
    SourceBase64,
    SourceBlobRef,
    SourceUrl,
    TextContent,
    ToolResponse,
)

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


# ---------------------------------------------------------------------------
# Optional tool_call_id
# ---------------------------------------------------------------------------


def test_tool_call_id_is_optional():
    resp = ToolResponse(content=[TextContent(type='text', text='hi')])
    assert resp.tool_call_id is None


def test_build_with_no_tool_call_id():
    resp = ToolResponse.build(None, 'done')
    dumped = resp.model_dump(mode='json', exclude_none=True)
    assert 'tool_call_id' not in dumped
    assert dumped['content'] == [{'type': 'text', 'text': 'done'}]


def test_tool_call_id_present_when_set():
    resp = ToolResponse.build('call_abc', 'done')
    assert resp.tool_call_id == 'call_abc'


# ---------------------------------------------------------------------------
# AudioContent paths
# ---------------------------------------------------------------------------


def test_build_from_audio_content():
    audio = AudioContent(
        type='audio',
        source=SourceBase64(kind='base64', data='AAAA', mime='audio/wav'),
    )
    resp = ToolResponse.build('tc_1', audio)
    assert len(resp.content) == 1
    assert isinstance(resp.content[0], AudioContent)


def test_audio_base64_wire_shape():
    audio = AudioContent(
        type='audio',
        source=SourceBase64(kind='base64', data='AAAA', mime='audio/mp3'),
    )
    dumped = ToolResponse.build('tc_1', audio).model_dump(mode='json', exclude_none=True)
    block = dumped['content'][0]
    assert block['type'] == 'audio'
    assert block['source'] == {'kind': 'base64', 'data': 'AAAA', 'mime': 'audio/mp3'}


def test_audio_url_wire_shape():
    audio = AudioContent(
        type='audio',
        source=SourceUrl(kind='url', url='https://example.com/clip.wav', mime='audio/wav'),
    )
    dumped = ToolResponse.build('tc_1', audio).model_dump(mode='json', exclude_none=True)
    source = dumped['content'][0]['source']
    assert source['kind'] == 'url'
    assert source['url'] == 'https://example.com/clip.wav'
    assert source['mime'] == 'audio/wav'


def test_audio_blob_ref_wire_shape():
    audio = AudioContent(
        type='audio',
        source=SourceBlobRef(kind='blob_ref', blob_key='org/run/r1/clip.mp3', mime='audio/mp3'),
    )
    dumped = ToolResponse.build('tc_1', audio).model_dump(mode='json', exclude_none=True)
    source = dumped['content'][0]['source']
    assert source['kind'] == 'blob_ref'
    assert source['blob_key'] == 'org/run/r1/clip.mp3'
    assert source['mime'] == 'audio/mp3'
    assert 'size_bytes' not in source
    assert 'attachment_id' not in source


def test_audio_blob_ref_with_metadata():
    audio = AudioContent(
        type='audio',
        source=SourceBlobRef(
            kind='blob_ref',
            blob_key='org/run/r1/clip.mp3',
            mime='audio/mp3',
            size_bytes=4096,
            attachment_id='att_xyz',
        ),
    )
    dumped = ToolResponse.build('tc_1', audio).model_dump(mode='json', exclude_none=True)
    source = dumped['content'][0]['source']
    assert source['size_bytes'] == 4096
    assert source['attachment_id'] == 'att_xyz'


# ---------------------------------------------------------------------------
# FileContent paths
# ---------------------------------------------------------------------------


def test_build_from_file_content():
    f = FileContent(
        type='file',
        source=SourceBase64(kind='base64', data='AAAA', mime='application/pdf'),
        filename='report.pdf',
    )
    resp = ToolResponse.build('tc_1', f)
    assert len(resp.content) == 1
    assert isinstance(resp.content[0], FileContent)


def test_file_base64_wire_shape():
    f = FileContent(
        type='file',
        source=SourceBase64(kind='base64', data='AAAA', mime='application/pdf'),
        filename='doc.pdf',
        mime='application/pdf',
    )
    dumped = ToolResponse.build('tc_1', f).model_dump(mode='json', exclude_none=True)
    block = dumped['content'][0]
    assert block['type'] == 'file'
    assert block['source']['mime'] == 'application/pdf'
    assert block['filename'] == 'doc.pdf'
    assert block['mime'] == 'application/pdf'


def test_file_url_wire_shape():
    f = FileContent(
        type='file',
        source=SourceUrl(kind='url', url='https://example.com/data.csv'),
        filename='data.csv',
    )
    dumped = ToolResponse.build('tc_1', f).model_dump(mode='json', exclude_none=True)
    block = dumped['content'][0]
    assert block['type'] == 'file'
    assert block['source']['kind'] == 'url'
    assert block['source']['url'] == 'https://example.com/data.csv'
    assert block['filename'] == 'data.csv'


def test_file_optional_fields_excluded():
    f = FileContent(
        type='file',
        source=SourceBase64(kind='base64', data='AAAA', mime='text/plain'),
    )
    dumped = ToolResponse.build('tc_1', f).model_dump(mode='json', exclude_none=True)
    block = dumped['content'][0]
    assert 'filename' not in block
    assert 'mime' not in block


# ---------------------------------------------------------------------------
# Mixed-modality lists
# ---------------------------------------------------------------------------


def test_mixed_list_text_audio_file():
    resp = ToolResponse.build(
        'tc_1',
        [
            'summary text',
            AudioContent(
                type='audio',
                source=SourceBase64(kind='base64', data='AAAA', mime='audio/wav'),
            ),
            FileContent(
                type='file',
                source=SourceBase64(kind='base64', data='BBBB', mime='application/pdf'),
                filename='report.pdf',
            ),
        ],
    )
    assert len(resp.content) == 3
    assert isinstance(resp.content[0], TextContent)
    assert isinstance(resp.content[1], AudioContent)
    assert isinstance(resp.content[2], FileContent)


def test_mixed_list_image_and_audio():
    resp = ToolResponse.build(
        'tc_1',
        [
            Image.from_bytes(PNG_BYTES),
            AudioContent(
                type='audio',
                source=SourceUrl(kind='url', url='https://example.com/clip.wav'),
            ),
        ],
    )
    assert isinstance(resp.content[0], ImageContent)
    assert isinstance(resp.content[1], AudioContent)


# ---------------------------------------------------------------------------
# Source discriminator validation
# ---------------------------------------------------------------------------


def test_source_rejects_invalid_kind():
    with pytest.raises(ValidationError):
        AudioContent(
            type='audio',
            source={'kind': 'unknown', 'data': 'AAA', 'mime': 'audio/wav'},  # type: ignore[arg-type]
        )


def test_audio_accepts_arbitrary_mime():
    # General Source types accept any MIME string (unlike ImageMime which is restricted).
    audio = AudioContent(
        type='audio',
        source=SourceBase64(kind='base64', data='AAAA', mime='audio/ogg; codecs=opus'),
    )
    assert audio.source.mime == 'audio/ogg; codecs=opus'


def test_file_accepts_arbitrary_mime():
    f = FileContent(
        type='file',
        source=SourceBase64(kind='base64', data='AAAA', mime='application/vnd.ms-excel'),
    )
    assert f.source.mime == 'application/vnd.ms-excel'
