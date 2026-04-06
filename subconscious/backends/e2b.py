"""E2BSandbox — cloud sandbox backend using E2B.

Requires: pip install subconscious-sdk[e2b]
(installs e2b-code-interpreter)

Usage::

    from subconscious.backends.e2b import E2BSandbox

    backend = E2BSandbox(
        template="python-3.12",
        packages=["pandas", "matplotlib"],
    )

    client = Subconscious()
    run = client.run(
        engine="tim-gpt",
        input={
            "instructions": "Analyze the data",
            "backend": backend,
        },
        options={"await_completion": True},
    )

    backend.close()  # or use as context manager
"""

import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from subconscious.backends.protocol import ExecuteResult
from subconscious.backends.sandbox import BaseSandbox


class E2BSandbox(BaseSandbox):
    """E2B cloud sandbox backend.

    Creates an E2B sandbox instance for isolated code execution. The sandbox
    persists for the lifetime of this object (or until ``close()`` is called).

    All filesystem operations (read, write, edit, ls, glob, grep) are
    executed inside the sandbox via BaseSandbox's script-based approach.
    The ``execute`` tool runs shell commands in the sandbox.

    Args:
        api_key: E2B API key. Falls back to ``E2B_API_KEY`` env var.
        template: E2B sandbox template (default: "base").
        timeout_ms: Sandbox lifetime in ms (default: 600000 = 10 min).
        packages: Python packages to pre-install on sandbox creation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        template: str = "base",
        timeout_ms: int = 600_000,
        packages: Optional[List[str]] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("E2B_API_KEY")
        self._template = template
        self._timeout_ms = timeout_ms
        self._packages = packages or []
        self._sandbox = None  # Lazy init
        self._id = f"e2b-{uuid.uuid4().hex[:8]}"

    @property
    def id(self) -> str:
        return self._id

    def _ensure_sandbox(self) -> None:
        """Create the E2B sandbox if not already running."""
        if self._sandbox is not None:
            return

        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            raise ImportError(
                "E2BSandbox requires e2b-code-interpreter. "
                "Install with: pip install subconscious-sdk[e2b]"
            )

        if not self._api_key:
            raise ValueError(
                "E2B API key required. Set E2B_API_KEY env var or pass api_key."
            )

        self._sandbox = Sandbox(
            template=self._template,
            api_key=self._api_key,
            timeout=self._timeout_ms // 1000,
        )

        # Pre-install packages
        if self._packages:
            pkg_str = " ".join(self._packages)
            self._sandbox.commands.run(f"pip install {pkg_str}", timeout=120)

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecuteResult:
        self._ensure_sandbox()
        try:
            result = self._sandbox.commands.run(
                command,
                timeout=timeout or (self._timeout_ms // 1000),
            )
            output = result.stdout or ""
            if result.stderr:
                stderr_lines = "\n".join(
                    f"[stderr] {line}" for line in result.stderr.strip().split("\n")
                )
                output = f"{output}\n{stderr_lines}" if output else stderr_lines

            return ExecuteResult(output=output, exit_code=result.exit_code)
        except Exception as e:
            return ExecuteResult(output=f"Error: {e}", exit_code=1)

    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[Dict[str, Any]]:
        self._ensure_sandbox()
        results = []
        for path, content in files:
            try:
                self._sandbox.files.write(path, content)
                results.append({"path": path, "success": True})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
        return results

    def download_files(self, paths: List[str]) -> List[Dict[str, Any]]:
        self._ensure_sandbox()
        results = []
        for path in paths:
            try:
                content = self._sandbox.files.read(path)
                results.append({"path": path, "content": content})
            except Exception as e:
                results.append({"path": path, "content": None, "error": str(e)})
        return results

    def close(self) -> None:
        """Kill the E2B sandbox."""
        if self._sandbox:
            try:
                self._sandbox.kill()
            except Exception:
                pass
            self._sandbox = None

    def __enter__(self) -> "E2BSandbox":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
