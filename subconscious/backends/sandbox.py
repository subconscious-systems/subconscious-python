"""BaseSandbox — abstract base for remote sandbox backends.

Implements all BackendProtocol filesystem methods by delegating to just
three abstract methods: execute(), upload_files(), download_files().
This means new sandbox providers (E2B, Modal, Docker, etc.) only need
to implement those three methods.

Inspired by LangChain Deep Agents' BaseSandbox pattern.
"""

import base64
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

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

# Python scripts executed inside the sandbox via execute().
# We use base64 encoding for paths to avoid escaping issues.

_READ_SCRIPT = '''
import sys, base64, os, json
path = base64.b64decode(sys.argv[1]).decode()
offset = int(sys.argv[2])
limit = int(sys.argv[3])
try:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    start = max(0, offset)
    selected = lines[start:start + limit]
    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i:6}\\t{line.rstrip()}")
    print(json.dumps({"content": "\\n".join(numbered), "total_lines": total, "lines_returned": len(selected)}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''

_LS_SCRIPT = '''
import sys, base64, os, json
path = base64.b64decode(sys.argv[1]).decode()
try:
    entries = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        is_dir = os.path.isdir(full)
        size = os.path.getsize(full) if not is_dir else None
        e = {"path": full, "is_dir": is_dir}
        if size is not None:
            e["size"] = size
        entries.append(e)
    print(json.dumps({"entries": entries}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''

_GLOB_SCRIPT = '''
import sys, base64, os, json, glob
pattern = base64.b64decode(sys.argv[1]).decode()
base = base64.b64decode(sys.argv[2]).decode() if len(sys.argv) > 2 and sys.argv[2] else os.getcwd()
try:
    full_pattern = os.path.join(base, pattern)
    matches = glob.glob(full_pattern, recursive=True)
    matches.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
    entries = []
    for m in matches:
        is_dir = os.path.isdir(m)
        e = {"path": m, "is_dir": is_dir}
        if not is_dir:
            try:
                e["size"] = os.path.getsize(m)
            except:
                pass
        entries.append(e)
    print(json.dumps({"matches": entries}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''

_EDIT_SCRIPT = '''
import sys, base64, json
path = base64.b64decode(sys.argv[1]).decode()
old = base64.b64decode(sys.argv[2]).decode()
new = base64.b64decode(sys.argv[3]).decode()
replace_all = sys.argv[4] == "true"
try:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print(json.dumps({"error": f"old_string not found in {path}"}))
        sys.exit(0)
    if not replace_all:
        count = content.count(old)
        if count > 1:
            print(json.dumps({"error": f"old_string appears {count} times. Use replace_all=true."}))
            sys.exit(0)
        content = content.replace(old, new, 1)
    else:
        content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(json.dumps({"path": path}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''


def _b64(s: str) -> str:
    """Base64-encode a string for safe shell interpolation."""
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


class BaseSandbox(SandboxBackend, ABC):
    """Abstract base for remote sandbox backends.

    Subclasses only need to implement three methods:
    - ``execute(command, timeout)`` — run a shell command
    - ``upload_files(files)`` — upload files to the sandbox
    - ``download_files(paths)`` — download files from the sandbox

    All BackendProtocol filesystem methods (read, write, edit, ls, glob, grep)
    are automatically implemented by running Python scripts inside the sandbox
    via ``execute()`` and transferring files via ``upload_files()``/``download_files()``.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this sandbox instance."""
        ...

    @abstractmethod
    def execute(self, command: str, timeout: Optional[int] = None) -> ExecuteResult:
        """Execute a shell command in the sandbox."""
        ...

    @abstractmethod
    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
        """Upload files to the sandbox.

        Args:
            files: List of (path, content_bytes) tuples.

        Returns:
            List of {"path": str, "success": bool, "error": str?} dicts.
        """
        ...

    @abstractmethod
    def download_files(self, paths: List[str]) -> List[Dict[str, Any]]:
        """Download files from the sandbox.

        Args:
            paths: List of file paths to download.

        Returns:
            List of {"path": str, "content": bytes?, "error": str?} dicts.
        """
        ...

    def close(self) -> None:
        """Shut down the sandbox. Override in subclasses."""
        pass

    # ── Filesystem ops implemented via execute() ──

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        result = self.execute(
            f"python3 -c '{_READ_SCRIPT}' {_b64(file_path)} {offset} {limit}"
        )
        return self._parse_json_result(result, ReadResult)

    def write(self, file_path: str, content: str) -> WriteResult:
        # Create parent dirs, then upload
        dir_path = "/".join(file_path.rsplit("/", 1)[:-1]) if "/" in file_path else ""
        if dir_path:
            self.execute(f"mkdir -p '{dir_path}'")

        upload_result = self.upload_files([(file_path, content.encode("utf-8"))])
        if upload_result and upload_result[0].get("error"):
            return WriteResult(error=upload_result[0]["error"])
        return WriteResult(path=file_path, bytes_written=len(content.encode("utf-8")))

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self.execute(
            f"python3 -c '{_EDIT_SCRIPT}' {_b64(file_path)} {_b64(old_string)} "
            f"{_b64(new_string)} {'true' if replace_all else 'false'}"
        )
        return self._parse_json_result(result, EditResult)

    def ls(self, path: str = ".") -> LsResult:
        result = self.execute(f"python3 -c '{_LS_SCRIPT}' {_b64(path)}")
        try:
            data = json.loads(result.output.strip())
            if "error" in data:
                return LsResult(error=data["error"])
            entries = [FileInfo(**e) for e in data.get("entries", [])]
            return LsResult(entries=entries)
        except (json.JSONDecodeError, ValueError):
            return LsResult(error=f"Failed to parse ls output: {result.output[:200]}")

    def glob(self, pattern: str, path: Optional[str] = None) -> GlobResult:
        path_b64 = _b64(path) if path else ""
        result = self.execute(
            f"python3 -c '{_GLOB_SCRIPT}' {_b64(pattern)} {path_b64}"
        )
        try:
            data = json.loads(result.output.strip())
            if "error" in data:
                return GlobResult(error=data["error"])
            entries = [FileInfo(**e) for e in data.get("matches", [])]
            return GlobResult(matches=entries)
        except (json.JSONDecodeError, ValueError):
            return GlobResult(error=f"Failed to parse glob output: {result.output[:200]}")

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> GrepResult:
        # Use grep -rHnF in the sandbox
        cmd_parts = ["grep", "-rHn"]
        if case_insensitive:
            cmd_parts.append("-i")
        # Use -F for fixed string (safer) unless pattern looks like regex
        cmd_parts.append("-F")
        cmd_parts.append(f"'{pattern}'")

        search_path = path or "."
        if glob:
            cmd_parts.extend(["--include", f"'{glob}'"])
        cmd_parts.append(f"'{search_path}'")

        result = self.execute(" ".join(cmd_parts))

        matches: List[GrepMatch] = []
        for line in result.output.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                try:
                    matches.append(
                        GrepMatch(path=parts[0], line=int(parts[1]), text=parts[2])
                    )
                except ValueError:
                    continue

        return GrepResult(matches=matches, count=len(matches))

    # ── Helpers ──

    def _parse_json_result(self, exec_result: ExecuteResult, result_cls: type) -> Any:
        """Parse JSON output from a sandbox script into a result dataclass."""
        try:
            data = json.loads(exec_result.output.strip())
            if "error" in data and data["error"]:
                return result_cls(error=data["error"])
            # Map JSON keys to constructor kwargs
            kwargs = {k: v for k, v in data.items() if k != "error"}
            return result_cls(**kwargs)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            return result_cls(error=f"Failed to parse output: {exec_result.output[:200]}")
