"""CompositeBackend — combines a default backend with optional memory."""

from typing import Any, Dict, List, Optional

from subconscious.backends.protocol import (
    BackendProtocol,
    EditResult,
    GlobResult,
    GrepResult,
    LsResult,
    MemoryBackend,
    ReadResult,
    WriteResult,
)


class CompositeBackend:
    """Combines a filesystem/sandbox backend with optional memory.

    All filesystem and shell operations delegate to the ``default`` backend.
    Memory operations delegate to the ``memory`` backend if provided.

    Example::

        from subconscious.backends import LocalShellBackend, CompositeBackend
        from subconscious.backends.memory import Mem0Memory

        backend = CompositeBackend(
            default=LocalShellBackend(root_dir="/my/project"),
            memory=Mem0Memory(),
        )
    """

    def __init__(
        self,
        default: BackendProtocol,
        memory: Optional[MemoryBackend] = None,
    ) -> None:
        self.default = default
        self.memory = memory

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return aggregated tool schemas from default + memory backends."""
        tools = self.default.get_tools()
        if self.memory:
            tools.extend(self.memory.get_memory_tools())
        return tools

    # ── Delegate filesystem ops to default backend ──

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self.default.read(file_path, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        return self.default.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self.default.edit(file_path, old_string, new_string, replace_all)

    def ls(self, path: str = ".") -> LsResult:
        return self.default.ls(path)

    def glob(self, pattern: str, path: Optional[str] = None) -> GlobResult:
        return self.default.glob(pattern, path)

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> GrepResult:
        return self.default.grep(pattern, path, glob, case_insensitive)

    # ── Delegate execute if default supports it ──

    def execute(self, command: str, timeout: Optional[int] = None):
        if not hasattr(self.default, "execute"):
            raise NotImplementedError(
                "The default backend does not support execute(). "
                "Use a SandboxBackend (e.g., LocalShellBackend) as the default."
            )
        return self.default.execute(command, timeout)

    # ── Delegate memory ops ──

    def memory_store(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.memory:
            raise NotImplementedError("No memory backend configured.")
        return self.memory.memory_store(content, metadata)

    def memory_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        if not self.memory:
            raise NotImplementedError("No memory backend configured.")
        return self.memory.memory_search(query, limit)

    def memory_get_all(self, limit: int = 50) -> Dict[str, Any]:
        if not self.memory:
            raise NotImplementedError("No memory backend configured.")
        return self.memory.memory_get_all(limit)
