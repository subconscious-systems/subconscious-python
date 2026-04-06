"""Memory backends for Subconscious SDK.

Provides persistent memory that survives across agent runs.
Combine with a filesystem/sandbox backend via CompositeBackend.

Usage::

    from subconscious.backends import LocalShellBackend, CompositeBackend
    from subconscious.backends.memory import Mem0Memory

    backend = CompositeBackend(
        default=LocalShellBackend(root_dir="/my/project"),
        memory=Mem0Memory(),
    )
"""

import os
from typing import Any, Dict, List, Optional

from subconscious.backends.protocol import MemoryBackend


class Mem0Memory(MemoryBackend):
    """Memory backend using Mem0.

    Provides persistent semantic memory that survives across agent runs.
    Memories are scoped to a user_id (defaults to org-level) and optionally
    an agent_id.

    Requires: pip install subconscious-sdk[mem0]
    (installs mem0ai)

    Args:
        api_key: Mem0 API key. Falls back to ``MEM0_API_KEY`` env var.
        user_id: Scope memories to this user. Defaults to "default".
        agent_id: Optional agent-level scoping.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: str = "default",
        agent_id: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("MEM0_API_KEY")
        self._user_id = user_id
        self._agent_id = agent_id
        self._client = None  # Lazy init

    def _ensure_client(self) -> None:
        if self._client is not None:
            return

        try:
            from mem0 import MemoryClient
        except ImportError:
            raise ImportError(
                "Mem0Memory requires mem0ai. "
                "Install with: pip install subconscious-sdk[mem0]"
            )

        if not self._api_key:
            raise ValueError(
                "Mem0 API key required. Set MEM0_API_KEY env var or pass api_key."
            )

        self._client = MemoryClient(api_key=self._api_key)

    def memory_store(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._ensure_client()
        kwargs: Dict[str, Any] = {"user_id": self._user_id}
        if self._agent_id:
            kwargs["agent_id"] = self._agent_id
        if metadata:
            kwargs["metadata"] = metadata

        self._client.add(
            [{"role": "assistant", "content": content}],
            **kwargs,
        )
        return {"stored": True}

    def memory_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        self._ensure_client()
        kwargs: Dict[str, Any] = {"user_id": self._user_id, "limit": limit}
        if self._agent_id:
            kwargs["agent_id"] = self._agent_id

        results = self._client.search(query, **kwargs)
        memories = []
        for r in results:
            entry: Dict[str, Any] = {"content": r.get("memory", "")}
            if "score" in r:
                entry["score"] = r["score"]
            if "id" in r:
                entry["id"] = r["id"]
            memories.append(entry)

        return {"memories": memories, "count": len(memories)}

    def memory_get_all(self, limit: int = 50) -> Dict[str, Any]:
        self._ensure_client()
        kwargs: Dict[str, Any] = {"user_id": self._user_id}
        if self._agent_id:
            kwargs["agent_id"] = self._agent_id

        results = self._client.get_all(**kwargs)
        # Mem0 get_all may return a list or paginated response
        if isinstance(results, list):
            items = results[:limit]
        else:
            items = results.get("results", results.get("memories", []))[:limit]

        memories = []
        for r in items:
            entry: Dict[str, Any] = {}
            if isinstance(r, dict):
                entry["content"] = r.get("memory", "")
                if "id" in r:
                    entry["id"] = r["id"]
            else:
                entry["content"] = str(r)
            memories.append(entry)

        return {"memories": memories, "count": len(memories)}
