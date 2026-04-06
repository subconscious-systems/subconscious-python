"""MCPStdioServer — stdio-to-HTTP transport bridge for local MCP servers.

Spawns a stdio MCP server as a subprocess, pre-initializes it, then
exposes a single HTTP endpoint that proxies MCP JSON-RPC requests between
the Subconscious API and the subprocess.

The API's native MCP client (StreamableHTTPClientTransport) connects to
the tunnel URL and handles tool discovery, allowedTools filtering, and
invocation — the SDK doesn't unfold tools at all.
"""

import json
import logging
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("subconscious.dev.mcp_proxy")


class MCPStdioServer:
    """Bridge a local stdio MCP server to HTTP for the Subconscious API.

    Spawns the MCP server subprocess, initializes it, then provides a
    ``handle_request()`` method that proxies JSON-RPC over HTTP to stdin/stdout.
    When registered on the DevServer, the API can connect to it as a standard
    MCP server via ``MCPTool(url=tunnel_url/mcp/{name})``.

    Args:
        name: Server name (used as the URL path component).
        command: Command to run (e.g., "npx", "python").
        args: Command arguments.
        env: Extra environment variables for the subprocess.
        allowed_tools: Optional tool filter — passed to the API via MCPTool.allowedTools.

    Example::

        server = MCPStdioServer(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self.env = {**os.environ, **(env or {})}
        self.allowed_tools = allowed_tools
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._init_response: Optional[Dict[str, Any]] = None

    def _ensure_started(self) -> None:
        """Start the subprocess and run the MCP initialize handshake."""
        if self._process and self._process.poll() is None:
            return

        cmd = [self.command] + self.args
        logger.info(f"Starting MCP server '{self.name}': {' '.join(cmd)}")

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )

        # Initialize and cache the response for later replay
        self._init_response = self._send_jsonrpc({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "subconscious-sdk-bridge", "version": "1.0.0"},
            },
        })

        # Send initialized notification (no response expected)
        self._write_to_stdin({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })

        logger.info(f"MCP server '{self.name}' initialized")

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _write_to_stdin(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to the subprocess stdin."""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError(f"MCP server '{self.name}' is not running")
        line = json.dumps(message) + "\n"
        self._process.stdin.write(line)  # type: ignore
        self._process.stdin.flush()  # type: ignore

    def _read_response(self, expected_id: int) -> Dict[str, Any]:
        """Read a JSON-RPC response with the given ID from stdout."""
        while True:
            line = self._process.stdout.readline()  # type: ignore
            if not line:
                raise RuntimeError(f"MCP server '{self.name}' closed stdout")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Skip notifications (no id)
            if "id" not in msg:
                continue
            if msg.get("id") == expected_id:
                return msg

    def _send_jsonrpc(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request to the subprocess and return the full response."""
        with self._lock:
            request_id = request.get("id")
            self._write_to_stdin(request)
            if request_id is not None:
                return self._read_response(request_id)
            return {}

    # ── HTTP transport bridge ──

    def handle_request(self, body: bytes) -> tuple:
        """Handle an incoming HTTP request from the API's MCP client.

        Proxies the JSON-RPC message to the stdio subprocess and returns
        the response. Handles initialize replay and notifications.

        Args:
            body: Raw HTTP request body (JSON-RPC message).

        Returns:
            (status_code, response_body_dict)
        """
        self._ensure_started()

        if not body or not body.strip():
            return 400, {"error": "Empty request body"}

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            return 400, {"error": "Invalid JSON"}

        method = request.get("method", "")
        request_id = request.get("id")

        # ── Initialize: replay cached response (subprocess already initialized) ──
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._init_response.get("result", self._init_response)
                if self._init_response
                else {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": "1.0.0"},
                },
            }
            return 200, response

        # ── Notifications: accept without forwarding ──
        if request_id is None or method.startswith("notifications/"):
            return 200, {}

        # ── Everything else: proxy to subprocess with our own ID tracking ──
        proxy_id = self._next_id()
        proxy_request = {**request, "id": proxy_id}

        try:
            response = self._send_jsonrpc(proxy_request)
            # Rewrite the ID back to what the caller sent
            response["id"] = request_id
            return 200, response
        except RuntimeError as e:
            return 502, {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)},
            }

    def stop(self) -> None:
        """Stop the MCP server subprocess."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._init_response = None
        logger.info(f"MCP server '{self.name}' stopped")

    def __del__(self) -> None:
        self.stop()
