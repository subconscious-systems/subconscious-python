"""MCPStdioServer — proxy for stdio-based MCP servers.

Spawns an MCP server as a subprocess, discovers its tools, and proxies
tool calls from the dev server HTTP endpoints to the stdio transport.
"""

import json
import logging
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("subconscious.dev.mcp_proxy")


class MCPStdioServer:
    """Connect to a local stdio MCP server.

    Spawns the MCP server as a subprocess and communicates via stdin/stdout
    using JSON-RPC 2.0 (the MCP stdio transport protocol).

    Args:
        name: Display name for the server (used as tool name prefix).
        command: Command to run (e.g., "npx", "python").
        args: Command arguments (e.g., ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]).
        env: Extra environment variables for the subprocess.
        allowed_tools: Optional whitelist of tool names. None = all tools.

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
        self._tools: Optional[List[Dict[str, Any]]] = None

    def _ensure_started(self) -> None:
        """Start the subprocess if not already running."""
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

        # Send initialize request
        init_response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "subconscious-sdk", "version": "0.3.0"},
        })

        # Send initialized notification
        self._send_notification("notifications/initialized", {})

        logger.info(f"MCP server '{self.name}' initialized")

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError(f"MCP server '{self.name}' is not running")

        with self._lock:
            self._request_id += 1
            request_id = self._request_id

            message = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }

            line = json.dumps(message) + "\n"
            self._process.stdin.write(line)  # type: ignore
            self._process.stdin.flush()  # type: ignore

            # Read response (skip notifications)
            while True:
                response_line = self._process.stdout.readline()  # type: ignore
                if not response_line:
                    raise RuntimeError(f"MCP server '{self.name}' closed stdout")

                response_line = response_line.strip()
                if not response_line:
                    continue

                try:
                    response = json.loads(response_line)
                except json.JSONDecodeError:
                    continue

                # Skip notifications (no id)
                if "id" not in response:
                    continue

                if response.get("id") == request_id:
                    if "error" in response:
                        error = response["error"]
                        raise RuntimeError(
                            f"MCP error: {error.get('message', 'Unknown error')} "
                            f"(code: {error.get('code')})"
                        )
                    return response.get("result", {})

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or self._process.poll() is not None:
            return

        with self._lock:
            message = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            line = json.dumps(message) + "\n"
            self._process.stdin.write(line)  # type: ignore
            self._process.stdin.flush()  # type: ignore

    def discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available tools from the MCP server.

        Starts the server if needed, calls tools/list, and returns tool schemas.
        """
        if self._tools is not None:
            return self._tools

        self._ensure_started()

        result = self._send_request("tools/list", {})
        tools = result.get("tools", [])

        # Apply allowed_tools filter
        if self.allowed_tools is not None:
            allowed_lower = {t.lower() for t in self.allowed_tools}
            tools = [t for t in tools if t.get("name", "").lower() in allowed_lower]

        self._tools = tools
        logger.info(f"MCP server '{self.name}' discovered {len(tools)} tools")
        return tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: The tool name as returned by discover_tools().
            arguments: Tool arguments dict.

        Returns:
            The tool result content.
        """
        self._ensure_started()

        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        # MCP tool results have a "content" array
        content = result.get("content", [])
        if content:
            # Return text content joined
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            if texts:
                return "\n".join(texts)

            # Return raw content if no text
            return content

        return result

    def stop(self) -> None:
        """Stop the MCP server subprocess."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._tools = None
        logger.info(f"MCP server '{self.name}' stopped")

    def __del__(self) -> None:
        self.stop()
