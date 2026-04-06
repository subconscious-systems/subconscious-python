"""FilesystemBackend — read/write/edit/ls/glob/grep without shell access.

A safer alternative to LocalShellBackend when shell execution is not needed.
Supports optional virtual_mode to restrict all paths within root_dir.
"""

import glob as glob_module
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from subconscious.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)


class FilesystemBackend(BackendProtocol):
    """Backend providing filesystem access without shell execution.

    Args:
        root_dir: Base directory for all operations. Defaults to cwd.
        virtual_mode: When True, all paths are anchored to root_dir and
            path traversal (``..``, ``~``) is blocked. Useful for restricting
            agent access to a specific directory tree.
    """

    def __init__(
        self,
        root_dir: Optional[str] = None,
        virtual_mode: bool = False,
    ) -> None:
        self.root_dir = Path(root_dir or os.getcwd()).resolve()
        self.virtual_mode = virtual_mode

    def _resolve(self, file_path: str) -> Path:
        """Resolve a path, enforcing virtual_mode if active."""
        if self.virtual_mode:
            # Block path traversal
            if ".." in file_path or "~" in file_path:
                raise ValueError(f"Path traversal not allowed in virtual mode: {file_path}")
            # All paths relative to root
            resolved = (self.root_dir / file_path.lstrip("/")).resolve()
            # Verify still within root
            if not str(resolved).startswith(str(self.root_dir)):
                raise ValueError(f"Path escapes root directory: {file_path}")
            return resolved

        p = Path(file_path)
        if p.is_absolute():
            return p
        return self.root_dir / p

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            path = self._resolve(file_path)
        except ValueError as e:
            return ReadResult(error=str(e))

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

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            path = self._resolve(file_path)
        except ValueError as e:
            return WriteResult(error=str(e))

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = content.encode("utf-8")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return WriteResult(path=str(path), bytes_written=len(encoded))
        except OSError as e:
            return WriteResult(error=str(e))

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            path = self._resolve(file_path)
        except ValueError as e:
            return EditResult(error=str(e))

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
                    "Use replace_all=true or provide more context."
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

    def ls(self, path: str = ".") -> LsResult:
        try:
            resolved = self._resolve(path)
        except ValueError as e:
            return LsResult(error=str(e))

        if not resolved.exists():
            return LsResult(error=f"Path not found: {path}")
        if not resolved.is_dir():
            return LsResult(error=f"Not a directory: {path}")

        try:
            entries = []
            for entry in sorted(resolved.iterdir(), key=lambda p: p.name):
                info = FileInfo(path=str(entry), is_dir=entry.is_dir())
                if entry.is_file():
                    try:
                        info.size = entry.stat().st_size
                    except OSError:
                        pass
                entries.append(info)
            return LsResult(entries=entries)
        except OSError as e:
            return LsResult(error=str(e))

    def glob(self, pattern: str, path: Optional[str] = None) -> GlobResult:
        try:
            base = str(self._resolve(path)) if path else str(self.root_dir)
        except ValueError as e:
            return GlobResult(error=str(e))

        full_pattern = os.path.join(base, pattern)
        try:
            matches = glob_module.glob(full_pattern, recursive=True)
            matches.sort(
                key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0,
                reverse=True,
            )
            entries = []
            for m in matches:
                p = Path(m)
                if self.virtual_mode and not str(p.resolve()).startswith(str(self.root_dir)):
                    continue
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

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> GrepResult:
        try:
            search_path = str(self._resolve(path)) if path else str(self.root_dir)
        except ValueError as e:
            return GrepResult(error=str(e))

        # Try ripgrep first
        try:
            cmd: List[str] = ["rg", "-n", "--no-heading"]
            if case_insensitive:
                cmd.append("-i")
            if glob:
                cmd.extend(["--glob", glob])
            cmd.append(pattern)
            cmd.append(search_path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode not in (0, 1):
                raise FileNotFoundError("rg failed")

            matches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append(
                        GrepMatch(path=parts[0], line=int(parts[1]), text=parts[2])
                    )
            return GrepResult(matches=matches, count=len(matches))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback to Python regex
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return GrepResult(error=f"Invalid pattern: {e}")

        matches = []
        root = Path(search_path)
        files = [root] if root.is_file() else root.rglob(glob or "*")

        for fp in files:
            if not fp.is_file():
                continue
            if self.virtual_mode and not str(fp.resolve()).startswith(str(self.root_dir)):
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
