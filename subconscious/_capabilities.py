"""Frozen snapshot of engine capability metadata.

Mirrors `packages/common/engines.ts` ENGINE_DATA[engine].supports.images.
Synced manually for now; a future iteration may pull this from the
``GET /v1/capabilities`` endpoint or the published `subconscious-sdk-core`
artifact (post-MM Phase 1).

Update this whenever the monorepo flips an engine's `supports.images` flag.
"""

from __future__ import annotations

from typing import FrozenSet

# Snapshot generated from packages/common/engines.ts on 2026-04-17.
_IMAGE_CAPABLE_ENGINES: FrozenSet[str] = frozenset(
    {
        # Compound engines — image support GA via TIM-large.
        'tim-gpt',
        'tim-gpt-heavy',
        'tim-gpt-heavy-tc',
        'tim-claude',
        'tim-claude-heavy',
        'timini',
        # Unified engines — gated by MM_UNIFIED_IMAGE_ENABLED on the server.
        'tim',
        'tim-edge',
    }
)


SUGGESTED_IMAGE_ENGINES = (
    'tim-claude',
    'tim-claude-heavy',
    'tim-gpt',
    'tim-gpt-heavy',
    'timini',
)


def engine_supports_images(engine: str) -> bool:
    """Return True if the engine accepts ImageContent blocks in run input."""
    return engine in _IMAGE_CAPABLE_ENGINES


class EngineDoesNotSupportImagesError(ValueError):
    """Raised before the API call when the user passes images on a text-only engine."""
