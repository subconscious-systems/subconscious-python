"""LocalShellBackend — filesystem + shell execution on the developer's machine.

Implements SandboxBackend: all 6 filesystem ops + execute (shell).
Inspired by LangChain's LocalShellBackend and the Subconscious MCP
reference server.
"""

import glob as glob_module
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from subconscious.backends.protocol import (
    EditResult,
    ExecuteResult,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackend,
    WriteResult,
)

_DEFAULT_TIMEOUT = 120
_DEFAULT_MAX_OUTPUT = 100_000


class LocalShellBackend(SandboxBackend):
    """Backend that runs on the developer's local machine.

    Provides filesystem access (read/write/edit/ls/glob/grep) and shell
    execution (execute) rooted at ``root_dir``.

    Args:
        root_dir: Working directory for all operations. Defaults to cwd.
        timeout: Default shell command timeout in seconds.
        max_output_bytes: Truncate shell output beyond this size.
        env: Extra environment variables for shell commands.
        inherit_env: If True (default), inherit ``os.environ`` and overlay ``env``.
    """

    def __init__(
        self,
        root_dir: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT,
        env: Optional[Dict[str, str]] = None,
        inherit_env: bool = True,
    ) -> None:
        self.root_dir = Path(root_dir or os.getcwd()).resolve()
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self._env: Dict[str, str] = {}
        if inherit_env:
            self._env.update(os.environ)
        if env:
            self._env.update(env)
        self.id = f"local-{uuid.uuid4().hex[:8]}"

    # ── Path helpers ──

    def _resolve(self, file_path: str) -> Path:
        """Resolve a path relative to root_dir."""
        p = Path(file_path)
        if p.is_absolute():
            return p
        return self.root_dir / p

    # ── Filesystem: read ──

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        path = self._resolve(file_path)
        if not path.exists():
            return ReadResult(error=f"File not found: {file_path}")
        if not path.is_file():
            return ReadResult(error=f"Not a file: {file_path}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            return ReadResult(error=str(e))

        total = len(lines)
        start = max(0, offset)
        end = start + limit
        selected = lines[start:end]

        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:6}\t{line.rstrip()}")

        return ReadResult(
            content="\n".join(numbered),
            total_lines=total,
            lines_returned=len(selected),
        )

    # ── Filesystem: write ──

    def write(self, file_path: str, content: str) -> WriteResult:
        path = self._resolve(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = content.encode("utf-8")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return WriteResult(path=str(path), bytes_written=len(encoded))
        except OSError as e:
            return WriteResult(error=str(e))

    # ── Filesystem: edit ──

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        path = self._resolve(file_path)
        if not path.exists():
            return EditResult(error=f"File not found: {file_path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return EditResult(error=str(e))

        if old_string not in content:
            return EditResult(error=f"old_string not found in {file_path}")

        if not replace_all:
            count = content.count(old_string)
            if count > 1:
                return EditResult(
                    error=f"old_string appears {count} times in {file_path}. "
                    "Use replace_all=true or provide more context to make it unique."
                )
            new_content = content.replace(old_string, new_string, 1)
        else:
            new_content = content.replace(old_string, new_string)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            return EditResult(error=str(e))

        return EditResult(path=str(path))

    # ── Filesystem: ls ──

    def ls(self, path: str = ".") -> LsResult:
        resolved = self._resolve(path)
        if not resolved.exists():
            return LsResult(error=f"Path not found: {path}")
        if not resolved.is_dir():
            return LsResult(error=f"Not a directory: {path}")

        try:
            entries = []
            for entry in sorted(resolved.iterdir(), key=lambda p: p.name):
                info = FileInfo(
                    path=str(entry),
                    is_dir=entry.is_dir(),
                )
                if entry.is_file():
                    try:
                        info.size = entry.stat().st_size
                    except OSError:
                        pass
                entries.append(info)
            return LsResult(entries=entries)
        except OSError as e:
            return LsResult(error=str(e))

    # ── Filesystem: glob ──

    def glob(self, pattern: str, path: Optional[str] = None) -> GlobResult:
        base = str(self._resolve(path)) if path else str(self.root_dir)
        full_pattern = os.path.join(base, pattern)

        try:
            matches = glob_module.glob(full_pattern, recursive=True)
            # Sort by modification time (most recent first)
            matches.sort(
                key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0,
                reverse=True,
            )
            entries = []
            for m in matches:
                p = Path(m)
                info = FileInfo(path=m, is_dir=p.is_dir())
                if p.is_file():
                    try:
                        info.size = p.stat().st_size
                    except OSError:
                        pass
                entries.append(info)
            return GlobResult(matches=entries)
        except OSError as e:
            return GlobResult(error=str(e))

    # ── Filesystem: grep ──

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> GrepResult:
        search_path = str(self._resolve(path)) if path else str(self.root_dir)

        # Try ripgrep first
        try:
            return self._grep_rg(pattern, search_path, glob, case_insensitive)
        except FileNotFoundError:
            pass

        # Fallback to Python regex
        return self._grep_python(pattern, search_path, glob, case_insensitive)

    def _grep_rg(
        self,
        pattern: str,
        search_path: str,
        glob_filter: Optional[str],
        case_insensitive: bool,
    ) -> GrepResult:
        """Search using ripgrep (rg)."""
        cmd: List[str] = ["rg", "-n", "--no-heading"]
        if case_insensitive:
            cmd.append("-i")
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        cmd.append(pattern)
        cmd.append(search_path)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode not in (0, 1):  # 1 = no matches
            raise FileNotFoundError("rg not found or failed")

        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: path:line:text
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append(
                    GrepMatch(path=parts[0], line=int(parts[1]), text=parts[2])
                )

        return GrepResult(matches=matches, count=len(matches))

    def _grep_python(
        self,
        pattern: str,
        search_path: str,
        glob_filter: Optional[str],
        case_insensitive: bool,
    ) -> GrepResult:
        """Fallback grep using Python regex."""
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return GrepResult(error=f"Invalid pattern: {e}")

        matches: List[GrepMatch] = []
        root = Path(search_path)
        files = [root] if root.is_file() else root.rglob(glob_filter or "*")

        for fp in files:
            if not fp.is_file():
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append(
                                GrepMatch(path=str(fp), line=i, text=line.rstrip())
                            )
            except OSError:
                continue

        return GrepResult(matches=matches, count=len(matches))

    # ── Shell: execute ──

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecuteResult:
        if not command or not isinstance(command, str):
            return ExecuteResult(output="Error: command must be a non-empty string", exit_code=1)

        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=str(self.root_dir),
                env=self._env or None,
            )

            output = result.stdout
            if result.stderr:
                stderr_lines = "\n".join(
                    f"[stderr] {line}" for line in result.stderr.strip().split("\n")
                )
                output = f"{output}\n{stderr_lines}" if output else stderr_lines

            # Truncate large output
            if len(output) > self.max_output_bytes:
                output = output[: self.max_output_bytes] + "\n... (output truncated)"

            return ExecuteResult(output=output, exit_code=result.returncode)

        except subprocess.TimeoutExpired:
            return ExecuteResult(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=124,
            )
        except OSError as e:
            return ExecuteResult(output=f"Error: {e}", exit_code=1)
