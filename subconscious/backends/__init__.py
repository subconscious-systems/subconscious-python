"""Backends for Subconscious SDK dev mode.

A backend provides filesystem, shell, and optionally memory capabilities
that the Subconscious cloud agent can use via tool calls.

Built-in backends:
- LocalShellBackend: filesystem + shell on the developer's machine
- FilesystemBackend: filesystem only (no shell), optional virtual_mode
- CompositeBackend: combines a default backend with optional memory

Cloud sandbox backends (require extra dependencies):
- E2BSandbox: E2B cloud sandbox (pip install subconscious-sdk[e2b])
"""

from subconscious.backends.protocol import (
    BackendProtocol,
    SandboxBackend,
    MemoryBackend,
    FileInfo,
    ReadResult,
    WriteResult,
    EditResult,
    GrepMatch,
    GrepResult,
    GlobResult,
    LsResult,
    ExecuteResult,
)
from subconscious.backends.local_shell import LocalShellBackend
from subconscious.backends.filesystem import FilesystemBackend
from subconscious.backends.composite import CompositeBackend

__all__ = [
    # Protocols
    "BackendProtocol",
    "SandboxBackend",
    "MemoryBackend",
    # Backends
    "LocalShellBackend",
    "FilesystemBackend",
    "CompositeBackend",
    # Result types
    "FileInfo",
    "ReadResult",
    "WriteResult",
    "EditResult",
    "GrepMatch",
    "GrepResult",
    "GlobResult",
    "LsResult",
    "ExecuteResult",
]
