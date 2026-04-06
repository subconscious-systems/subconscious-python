"""Backend protocols and result types for Subconscious SDK dev mode.

Backends provide filesystem, shell, and memory capabilities that the
Subconscious cloud agent can invoke via tool calls. The SDK auto-generates
tool schemas from the backend protocol, serves them via a local HTTP server
+ tunnel, and passes them to the API as FunctionTool dicts.

Protocol hierarchy:
- BackendProtocol: filesystem ops (read, write, edit, ls, glob, grep)
- SandboxBackend(BackendProtocol): adds shell execution (execute)
- MemoryBackend: separate composable protocol for memory (store, search, get_all)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Result types ──


@dataclass
class FileInfo:
    """Metadata for a file or directory entry."""

    path: str
    is_dir: bool = False
    size: Optional[int] = None


@dataclass
class ReadResult:
    """Result of reading a file."""

    error: Optional[str] = None
    content: Optional[str] = None
    total_lines: Optional[int] = None
    lines_returned: Optional[int] = None


@dataclass
class WriteResult:
    """Result of writing a file."""

    error: Optional[str] = None
    path: Optional[str] = None
    bytes_written: Optional[int] = None


@dataclass
class EditResult:
    """Result of editing a file via string replacement."""

    error: Optional[str] = None
    path: Optional[str] = None


@dataclass
class GrepMatch:
    """A single grep match."""

    path: str
    line: int
    text: str


@dataclass
class GrepResult:
    """Result of searching file contents."""

    error: Optional[str] = None
    matches: Optional[List[GrepMatch]] = None
    count: Optional[int] = None


@dataclass
class GlobResult:
    """Result of finding files by glob pattern."""

    error: Optional[str] = None
    matches: Optional[List[FileInfo]] = None


@dataclass
class LsResult:
    """Result of listing a directory."""

    error: Optional[str] = None
    entries: Optional[List[FileInfo]] = None


@dataclass
class ExecuteResult:
    """Result of executing a shell command."""

    output: str
    exit_code: Optional[int] = None


# ── Tool schema helpers ──


def _filesystem_tool_schemas() -> List[Dict[str, Any]]:
    """Return FunctionTool-compatible schemas for the 6 filesystem operations."""
    return [
        {
            "name": "read",
            "description": (
                "Read a file from the filesystem. Returns content with line numbers. "
                "Use offset and limit for large files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to read"},
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-indexed). Defaults to 0.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Defaults to 2000.",
                    },
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "write",
            "description": "Write content to a file. Creates parent directories if needed. Overwrites if file exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["file_path", "content"],
            },
        },
        {
            "name": "edit",
            "description": (
                "Edit a file by replacing an exact string. The old_string must appear exactly once "
                "in the file unless replace_all is true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to edit"},
                    "old_string": {"type": "string", "description": "Exact text to find and replace"},
                    "new_string": {"type": "string", "description": "Text to replace it with"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences (default: false)",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
        {
            "name": "ls",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Defaults to the working directory.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "glob",
            "description": (
                'Find files matching a glob pattern. Supports *, **, ? wildcards. '
                'Example: "**/*.py" finds all Python files recursively.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern to match files against"},
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Defaults to the working directory.",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "grep",
            "description": "Search file contents for a text pattern. Returns matching lines with file paths and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in. Defaults to the working directory.",
                    },
                    "glob": {
                        "type": "string",
                        "description": 'Glob pattern to filter files (e.g., "*.py").',
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case-insensitive search (default: false)",
                    },
                },
                "required": ["pattern"],
            },
        },
    ]


def _execute_tool_schema() -> Dict[str, Any]:
    """Return FunctionTool-compatible schema for the execute (shell) operation."""
    return {
        "name": "execute",
        "description": (
            "Execute a shell command and return its output. "
            "Use for running tests, installing packages, git operations, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Defaults to the backend's configured timeout.",
                },
            },
            "required": ["command"],
        },
    }


def _memory_tool_schemas() -> List[Dict[str, Any]]:
    """Return FunctionTool-compatible schemas for memory operations."""
    return [
        {
            "name": "memory_store",
            "description": "Store a fact, observation, or memory for later retrieval across sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The content to store"},
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata to attach to the memory",
                    },
                },
                "required": ["content"],
            },
        },
        {
            "name": "memory_search",
            "description": "Search stored memories by semantic relevance to a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "memory_get_all",
            "description": "List all stored memories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                    },
                },
                "required": [],
            },
        },
    ]


# ── Protocols ──


class BackendProtocol(ABC):
    """Base protocol for all backends. Provides filesystem operations.

    Implement this to create a backend that gives the agent read/write/edit
    access to a filesystem (local, remote, or virtual) along with search
    capabilities (glob, grep).

    The agent receives 6 tools: read, write, edit, ls, glob, grep.
    """

    @abstractmethod
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """Read a file with optional line offset and limit."""
        ...

    @abstractmethod
    def write(self, file_path: str, content: str) -> WriteResult:
        """Write content to a file. Creates parent directories if needed."""
        ...

    @abstractmethod
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Replace exact string occurrences in a file."""
        ...

    @abstractmethod
    def ls(self, path: str = ".") -> LsResult:
        """List files and directories at the given path."""
        ...

    @abstractmethod
    def glob(self, pattern: str, path: Optional[str] = None) -> GlobResult:
        """Find files matching a glob pattern."""
        ...

    @abstractmethod
    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> GrepResult:
        """Search file contents for a text pattern."""
        ...

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return tool schemas for this backend's capabilities.

        Override to customize tool names, descriptions, or add extra tools.
        """
        return _filesystem_tool_schemas()


class SandboxBackend(BackendProtocol):
    """Extended backend that adds shell execution.

    In addition to the 6 filesystem tools, the agent receives an 'execute'
    tool for running shell commands.

    Implement this for backends that support command execution (local shell,
    E2B sandbox, Docker, etc.).
    """

    @abstractmethod
    def execute(self, command: str, timeout: Optional[int] = None) -> ExecuteResult:
        """Execute a shell command. Returns combined stdout/stderr and exit code."""
        ...

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return filesystem + execute tool schemas."""
        return _filesystem_tool_schemas() + [_execute_tool_schema()]


class MemoryBackend(ABC):
    """Protocol for memory providers. Composable with any BackendProtocol.

    Memory backends provide persistent storage that survives across runs.
    Combine with a filesystem/sandbox backend via CompositeBackend.

    The agent receives 3 tools: memory_store, memory_search, memory_get_all.
    """

    @abstractmethod
    def memory_store(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Store a memory for later retrieval."""
        ...

    @abstractmethod
    def memory_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search memories by semantic relevance."""
        ...

    @abstractmethod
    def memory_get_all(self, limit: int = 50) -> Dict[str, Any]:
        """List all stored memories."""
        ...

    def get_memory_tools(self) -> List[Dict[str, Any]]:
        """Return tool schemas for memory operations.

        Override to customize tool names or descriptions.
        """
        return _memory_tool_schemas()
