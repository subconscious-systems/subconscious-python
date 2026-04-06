"""Tests for backends, @tool decorator, dev server, and composite backend."""

import json
import os
import tempfile
import urllib.request
from pathlib import Path

import pytest

from subconscious.backends.local_shell import LocalShellBackend
from subconscious.backends.filesystem import FilesystemBackend
from subconscious.backends.composite import CompositeBackend
from subconscious.backends.protocol import (
    BackendProtocol,
    SandboxBackend,
    MemoryBackend,
)
from subconscious.tools import tool
from subconscious.dev.server import DevServer


# ── LocalShellBackend ──


class TestLocalShellBackend:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = LocalShellBackend(root_dir=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_and_read(self):
        r = self.backend.write("test.txt", "hello\nworld\n")
        assert r.error is None
        assert r.bytes_written == 12

        r = self.backend.read("test.txt")
        assert r.error is None
        assert "hello" in r.content
        assert r.total_lines == 2

    def test_read_with_offset_limit(self):
        lines = "\n".join(f"line {i}" for i in range(20)) + "\n"
        self.backend.write("big.txt", lines)

        r = self.backend.read("big.txt", offset=5, limit=3)
        assert r.error is None
        assert r.lines_returned == 3
        assert "line 5" in r.content

    def test_read_missing_file(self):
        r = self.backend.read("nonexistent.txt")
        assert r.error is not None
        assert "not found" in r.error.lower()

    def test_edit(self):
        self.backend.write("test.txt", "foo bar baz")
        r = self.backend.edit("test.txt", "bar", "qux")
        assert r.error is None

        r2 = self.backend.read("test.txt")
        assert "qux" in r2.content
        assert "bar" not in r2.content

    def test_edit_not_found(self):
        self.backend.write("test.txt", "hello")
        r = self.backend.edit("test.txt", "missing", "replacement")
        assert r.error is not None
        assert "not found" in r.error.lower()

    def test_edit_ambiguous(self):
        self.backend.write("test.txt", "aaa aaa aaa")
        r = self.backend.edit("test.txt", "aaa", "bbb")
        assert r.error is not None
        assert "3 times" in r.error

    def test_edit_replace_all(self):
        self.backend.write("test.txt", "aaa aaa aaa")
        r = self.backend.edit("test.txt", "aaa", "bbb", replace_all=True)
        assert r.error is None
        r2 = self.backend.read("test.txt")
        assert "aaa" not in r2.content

    def test_ls(self):
        self.backend.write("a.txt", "a")
        self.backend.write("b.txt", "b")
        os.mkdir(os.path.join(self.tmpdir, "subdir"))

        r = self.backend.ls(".")
        assert r.error is None
        assert len(r.entries) == 3
        names = [os.path.basename(e.path) for e in r.entries]
        assert "a.txt" in names
        assert "subdir" in names

    def test_glob(self):
        self.backend.write("a.py", "# python")
        self.backend.write("b.txt", "text")

        r = self.backend.glob("*.py")
        assert r.error is None
        assert len(r.matches) == 1
        assert r.matches[0].path.endswith(".py")

    def test_grep(self):
        self.backend.write("a.py", "def hello():\n    pass\n")
        self.backend.write("b.py", "def world():\n    return 42\n")

        r = self.backend.grep("def")
        assert r.error is None
        assert r.count == 2

    def test_execute(self):
        r = self.backend.execute("echo hello")
        assert r.exit_code == 0
        assert "hello" in r.output

    def test_execute_failure(self):
        r = self.backend.execute("exit 1")
        assert r.exit_code == 1

    def test_execute_timeout(self):
        r = self.backend.execute("sleep 10", timeout=1)
        assert r.exit_code == 124
        assert "timed out" in r.output.lower()

    def test_is_sandbox_backend(self):
        assert isinstance(self.backend, SandboxBackend)
        assert isinstance(self.backend, BackendProtocol)

    def test_get_tools(self):
        tools = self.backend.get_tools()
        names = [t["name"] for t in tools]
        assert "read" in names
        assert "write" in names
        assert "edit" in names
        assert "ls" in names
        assert "glob" in names
        assert "grep" in names
        assert "execute" in names
        assert len(tools) == 7


# ── FilesystemBackend ──


class TestFilesystemBackend:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = FilesystemBackend(root_dir=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_read_write(self):
        self.backend.write("test.txt", "content")
        r = self.backend.read("test.txt")
        assert r.error is None
        assert "content" in r.content

    def test_no_execute(self):
        assert not isinstance(self.backend, SandboxBackend)
        assert not hasattr(self.backend, "execute")

    def test_get_tools_no_execute(self):
        tools = self.backend.get_tools()
        names = [t["name"] for t in tools]
        assert "execute" not in names
        assert len(tools) == 6

    def test_virtual_mode_blocks_traversal(self):
        backend = FilesystemBackend(root_dir=self.tmpdir, virtual_mode=True)
        r = backend.read("../../etc/passwd")
        assert r.error is not None
        assert "traversal" in r.error.lower()


# ── CompositeBackend ──


class TestCompositeBackend:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.default = LocalShellBackend(root_dir=self.tmpdir)
        self.composite = CompositeBackend(default=self.default)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_delegates_filesystem(self):
        self.composite.write("test.txt", "delegated")
        r = self.composite.read("test.txt")
        assert "delegated" in r.content

    def test_delegates_execute(self):
        r = self.composite.execute("echo works")
        assert "works" in r.output

    def test_no_memory_raises(self):
        with pytest.raises(NotImplementedError):
            self.composite.memory_store("test")

    def test_get_tools_without_memory(self):
        tools = self.composite.get_tools()
        names = [t["name"] for t in tools]
        assert "execute" in names
        assert "memory_store" not in names

    def test_filesystem_only_composite(self):
        fs = FilesystemBackend(root_dir=self.tmpdir)
        composite = CompositeBackend(default=fs)
        with pytest.raises(NotImplementedError):
            composite.execute("echo test")


# ── @tool decorator ──


class TestToolDecorator:
    def test_basic_decorator(self):
        @tool
        def search(query: str) -> str:
            """Search the web."""
            return f"results for {query}"

        assert search._subcon_tool is True
        assert search._subcon_name == "search"
        assert search._subcon_description == "Search the web."
        assert search("test") == "results for test"

    def test_schema_generation(self):
        @tool
        def func(name: str, count: int, flag: bool = False) -> str:
            """A test function."""
            return ""

        schema = func._subcon_schema
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["flag"]["type"] == "boolean"
        assert "name" in schema["required"]
        assert "count" in schema["required"]
        assert "flag" not in schema["required"]

    def test_optional_params(self):
        from typing import Optional

        @tool
        def func(query: str, limit: Optional[int] = None) -> str:
            return ""

        schema = func._subcon_schema
        assert "query" in schema["required"]
        assert "limit" not in schema["required"]

    def test_decorator_with_kwargs(self):
        @tool(name="custom_name", description="Custom desc")
        def func(x: int) -> int:
            """Original doc."""
            return x

        assert func._subcon_name == "custom_name"
        assert func._subcon_description == "Custom desc"

    def test_decorator_with_sandbox(self):
        class FakeSandbox:
            pass

        sb = FakeSandbox()

        @tool(sandbox=sb)
        def func(code: str) -> str:
            return ""

        assert func._subcon_sandbox is sb


# ── DevServer ──


class TestDevServer:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.server = DevServer()

    def teardown_method(self):
        self.server.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _post(self, path, data=None):
        """Helper to POST JSON to the dev server."""
        url = f"http://127.0.0.1:{self.server.port}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data or {}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())

    def test_register_backend_and_serve(self):
        backend = LocalShellBackend(root_dir=self.tmpdir)
        tools = self.server.register_backend(backend)
        assert len(tools) == 7

        self.server.start()
        backend.write("hello.txt", "world")

        result = self._post("/backend/read", {"file_path": "hello.txt"})
        assert result["error"] is None
        assert "world" in result["result"]["content"]

    def test_register_tool_and_serve(self):
        @tool
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"

        schema = self.server.register_tool(greet)
        assert schema["name"] == "greet"
        assert schema["url"] == "/tools/greet"

        self.server.start()
        result = self._post("/tools/greet", {"name": "World"})
        assert result["error"] is None
        assert result["result"] == "Hello, World!"

    def test_health_endpoint(self):
        self.server.start()
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{self.server.port}/health"
        )
        health = json.loads(resp.read())
        assert health["status"] == "ok"

    def test_404_unknown_endpoint(self):
        self.server.start()
        try:
            self._post("/unknown/endpoint")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_execute_via_http(self):
        backend = LocalShellBackend(root_dir=self.tmpdir)
        self.server.register_backend(backend)
        self.server.start()

        result = self._post("/backend/execute", {"command": "echo test123"})
        assert result["error"] is None
        assert "test123" in result["result"]["output"]
