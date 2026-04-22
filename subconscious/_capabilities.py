"""Frozen snapshot of engine capability metadata.

Mirrors `packages/common/engines.ts` ENGINE_DATA[engine].supports.images.
Synced manually for now.

Update this whenever the monorepo flips an engine's `supports.images` flag.
"""

from __future__ import annotations

_IMAGE_CAPABLE_ENGINES: frozenset[str] = frozenset(
    {
        'tim-claude',
        'tim-claude-heavy',
    }
)


SUGGESTED_IMAGE_ENGINES = (
    'tim-claude',
    'tim-claude-heavy',
)


def engine_supports_images(engine: str) -> bool:
    """Return True if the engine accepts ImageContent blocks in run input."""
    return engine in _IMAGE_CAPABLE_ENGINES


class EngineDoesNotSupportImagesError(ValueError):
    """Raised before the API call when the user passes images on a text-only engine."""
