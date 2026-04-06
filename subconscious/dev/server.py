"""DevServer — local HTTP server exposing backends, tools, and MCP proxies.

Runs in a background daemon thread. The Subconscious cloud agent calls
these endpoints via a tunnel URL during execution.
"""

import json
import logging
import socket
import traceback
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("subconscious.dev.server")


def _serialize_result(result: Any) -> Any:
    """Convert dataclass results to dicts for JSON serialization."""
    if is_dataclass(result) and not isinstance(result, type):
        d = {}
        for k, v in result.__dict__.items():
            if v is None:
                continue
            if isinstance(v, list):
                d[k] = [_serialize_result(item) for item in v]
            elif is_dataclass(v) and not isinstance(v, type):
                d[k] = _serialize_result(v)
            else:
                d[k] = v
        return d
    return result


def _find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DevServer:
    """Local HTTP tool server for dev mode.

    Registers backend methods, @tool functions, and MCP proxies as HTTP
    endpoints. Runs in a background daemon thread.

    The server responds to POST requests with JSON bodies and returns
    JSON responses in the format: ``{"result": ..., "error": null}``
    or ``{"result": null, "error": "..."}``.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._port: Optional[int] = None
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None

    @property
    def port(self) -> Optional[int]:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def register_handler(self, path: str, handler: Callable[..., Any]) -> None:
        """Register a handler for a given path (e.g., '/backend/read')."""
        self._handlers[path] = handler

    def register_backend(self, backend: Any) -> List[Dict[str, Any]]:
        """Register a backend's methods as HTTP endpoints.

        Returns FunctionTool-compatible schemas with relative URL paths.
        """
        from subconscious.backends.protocol import BackendProtocol, SandboxBackend, MemoryBackend
        from subconscious.backends.composite import CompositeBackend

        tools: List[Dict[str, Any]] = []

        # Get the actual backend (unwrap composite)
        actual_backend = backend.default if isinstance(backend, CompositeBackend) else backend

        # Register filesystem methods
        fs_methods = ["read", "write", "edit", "ls", "glob", "grep"]
        for method_name in fs_methods:
            fn = getattr(backend, method_name, None)
            if fn:
                self.register_handler(f"/backend/{method_name}", fn)

        # Register execute if supported
        if hasattr(actual_backend, "execute"):
            self.register_handler("/backend/execute", backend.execute)

        # Register memory methods if composite with memory
        if isinstance(backend, CompositeBackend) and backend.memory:
            for method_name in ["memory_store", "memory_search", "memory_get_all"]:
                fn = getattr(backend, method_name, None)
                if fn:
                    self.register_handler(f"/backend/{method_name}", fn)

        # Build tool schemas with URL paths
        tool_schemas = backend.get_tools()
        for schema in tool_schemas:
            tool = dict(schema)
            tool["url"] = f"/backend/{schema['name']}"
            tools.append(tool)

        return tools

    def register_tool(self, func: Callable) -> Dict[str, Any]:
        """Register a @tool-decorated function.

        Returns a FunctionTool-compatible schema with relative URL path.
        """
        name = getattr(func, "_subcon_name", func.__name__)
        path = f"/tools/{name}"
        self.register_handler(path, func)

        return {
            "name": name,
            "description": getattr(func, "_subcon_description", func.__doc__ or ""),
            "parameters": getattr(func, "_subcon_schema", {}),
            "url": path,
        }

    def register_mcp_proxy(self, server: Any) -> List[Dict[str, Any]]:
        """Register MCP tool proxies.

        Discovers tools from the MCP server and creates proxy handlers.
        Returns FunctionTool-compatible schemas with relative URL paths.
        """
        tools: List[Dict[str, Any]] = []
        # Delegate to the MCPStdioServer's discovery
        discovered_tools = server.discover_tools()

        for tool_info in discovered_tools:
            tool_name = tool_info["name"]
            path = f"/mcp/{server.name}/{tool_name}"

            def make_handler(srv: Any, tn: str):
                def handler(**params: Any) -> Any:
                    return srv.call_tool(tn, params)
                return handler

            self.register_handler(path, make_handler(server, tool_name))

            tools.append({
                "name": f"{server.name}_{tool_name}" if server.name else tool_name,
                "description": tool_info.get("description", ""),
                "parameters": tool_info.get("inputSchema", {}),
                "url": path,
            })

        return tools

    def start(self) -> int:
        """Start the HTTP server in a background thread. Returns the port."""
        if self.is_running:
            return self._port  # type: ignore

        self._port = _find_free_port()
        handlers = self._handlers

        class RequestHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                # Read body
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length else b"{}"

                try:
                    params = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    self._respond(400, {"result": None, "error": "Invalid JSON"})
                    return

                # Find handler
                handler = handlers.get(self.path)
                if not handler:
                    self._respond(404, {"result": None, "error": f"Unknown endpoint: {self.path}"})
                    return

                # Execute
                try:
                    result = handler(**params)
                    serialized = _serialize_result(result)
                    self._respond(200, {"result": serialized, "error": None})
                except TypeError as e:
                    self._respond(400, {"result": None, "error": f"Parameter error: {e}"})
                except Exception as e:
                    logger.exception(f"Error in handler {self.path}")
                    self._respond(500, {"result": None, "error": f"{type(e).__name__}: {e}"})

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._respond(200, {"status": "ok", "handlers": list(handlers.keys())})
                else:
                    self._respond(404, {"error": "Not found"})

            def _respond(self, status: int, data: dict) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress default access logs; use our logger
                logger.debug(f"DevServer: {format % args}")

        self._server = HTTPServer(("127.0.0.1", self._port), RequestHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"DevServer started on port {self._port}")
        return self._port

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        self._port = None
        logger.info("DevServer stopped")
