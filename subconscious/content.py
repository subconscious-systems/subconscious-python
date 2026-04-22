"""Multimodal content helpers — `Image` constructor + content type re-exports.

Lets users build canonical ImageContent blocks from a path, raw bytes, a
remote URL, or a server-side blob_ref::

    from subconscious import Client, Image, TextContent

    client.runs.create(
        engine='tim-claude',
        input={
            'instructions': 'What is in this image?',
            'content': [Image.from_path('shot.png')],
        },
    )
"""

from __future__ import annotations

import base64
import urllib.request
from pathlib import Path

from .types import (
    ImageContent,
    ImageSourceBase64,
    ImageSourceBlobRef,
    ImageSourceUrl,
)

# Mirror packages/common/schemas/content-block.ts MIME_ALLOWED.
_MIME_ALLOWED = frozenset({'image/png', 'image/jpeg', 'image/gif', 'image/webp'})


def _detect_mime(data: bytes) -> str:
    """Magic-byte mime detection — mirrors apps/api/src/core/blob-store/image-utils.ts."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    raise ValueError('unsupported image type — only PNG, JPEG, GIF, and WebP are accepted')


class Image:
    """Static factory for ImageContent blocks. Use the constructor that matches
    the bytes you have in hand."""

    @staticmethod
    def from_path(path: str | Path) -> ImageContent:
        """Read an image file from disk and emit an ImageContent(base64) block."""
        data = Path(path).read_bytes()
        mime = _detect_mime(data)
        return ImageContent(
            type='image',
            source=ImageSourceBase64(
                kind='base64',
                data=base64.b64encode(data).decode('ascii'),
                mime=mime,  # type: ignore[arg-type]
            ),
        )

    @staticmethod
    def from_bytes(data: bytes, mime: str | None = None) -> ImageContent:
        """Wrap raw bytes as an ImageContent(base64) block. Mime is detected if not provided."""
        resolved_mime = mime or _detect_mime(data)
        if resolved_mime not in _MIME_ALLOWED:
            raise ValueError(f'mime {resolved_mime} not allowed')
        return ImageContent(
            type='image',
            source=ImageSourceBase64(
                kind='base64',
                data=base64.b64encode(data).decode('ascii'),
                mime=resolved_mime,  # type: ignore[arg-type]
            ),
        )

    @staticmethod
    def from_url(url: str, *, fetch: bool = False) -> ImageContent:
        """Reference a remote image by URL.

        ``fetch=False`` (default) sends the URL through to the server, which
        forwards it to the vendor when supported. ``fetch=True`` downloads the
        bytes client-side and embeds them as base64 — useful when the vendor
        doesn't fetch URLs (e.g. some Claude paths).
        """
        if fetch:
            with urllib.request.urlopen(url) as resp:  # noqa: S310 — caller-controlled URL
                return Image.from_bytes(resp.read())
        return ImageContent(type='image', source=ImageSourceUrl(kind='url', url=url))  # type: ignore[arg-type]

    @staticmethod
    def from_blob_ref(blob_key: str, mime: str) -> ImageContent:
        """Reference an asset already stored server-side. Skip an upload roundtrip."""
        return ImageContent(
            type='image',
            source=ImageSourceBlobRef(
                kind='blob_ref',
                blob_key=blob_key,
                mime=mime,  # type: ignore[arg-type]
            ),
        )


__all__ = ['Image']
