"""Tunnel providers for exposing the local dev server to the internet.

The Subconscious cloud agent needs a public URL to call tool endpoints.
Tunnel providers bridge local HTTP to a public HTTPS URL.

Providers:
- LocalTunnel: uses bore CLI (pip install bore-cli) or SSH fallback (serveo.net)
- NgrokTunnel: uses ngrok (pip install pyngrok)
"""

import logging
import os
import shutil
import subprocess
import time
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("subconscious.dev.tunnel")


@runtime_checkable
class TunnelProvider(Protocol):
    """Protocol for tunnel providers."""

    def start(self, local_port: int) -> str:
        """Start the tunnel and return the public URL."""
        ...

    def stop(self) -> None:
        """Stop the tunnel."""
        ...

    def is_alive(self) -> bool:
        """Check if the tunnel is still active."""
        ...


class LocalTunnel:
    """Default tunnel using bore CLI or SSH fallback.

    Tries in order:
    1. ``bore`` CLI (``pip install bore-cli``) — most reliable
    2. SSH reverse tunnel to serveo.net — zero-dep fallback

    Args:
        bore_server: Override bore relay server (default: bore.pub).
    """

    def __init__(self, bore_server: str = "bore.pub") -> None:
        self._bore_server = bore_server
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._method: Optional[str] = None

    def start(self, local_port: int) -> str:
        if self._public_url and self.is_alive():
            return self._public_url

        # Try bore first
        if shutil.which("bore"):
            return self._start_bore(local_port)

        # Fallback to SSH + serveo
        if shutil.which("ssh"):
            return self._start_ssh(local_port)

        raise RuntimeError(
            "No tunnel provider available. Install one of:\n"
            "  pip install bore-cli    (recommended)\n"
            "  pip install pyngrok     (alternative, use NgrokTunnel)\n"
            "Or ensure 'ssh' is available on PATH for serveo.net fallback."
        )

    def _start_bore(self, local_port: int) -> str:
        """Start bore tunnel."""
        self._process = subprocess.Popen(
            ["bore", "local", str(local_port), "--to", self._bore_server],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._method = "bore"

        # Read output to find the public URL
        # bore outputs something like: "listening at bore.pub:NNNNN"
        deadline = time.time() + 15
        while time.time() < deadline:
            line = self._process.stdout.readline()  # type: ignore
            if not line:
                if self._process.poll() is not None:
                    raise RuntimeError(f"bore exited with code {self._process.returncode}")
                time.sleep(0.1)
                continue

            line = line.strip()
            logger.debug(f"bore: {line}")

            if "bore.pub:" in line or "listening" in line.lower():
                # Extract port from bore output
                for part in line.split():
                    if self._bore_server in part:
                        self._public_url = f"https://{part}"
                        if not self._public_url.startswith("https://"):
                            self._public_url = f"https://{part}"
                        logger.info(f"Bore tunnel: {self._public_url}")
                        return self._public_url

        raise RuntimeError("Timed out waiting for bore tunnel URL")

    def _start_ssh(self, local_port: int) -> str:
        """Start SSH reverse tunnel via serveo.net."""
        self._process = subprocess.Popen(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-R", f"80:localhost:{local_port}",
                "serveo.net",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._method = "ssh/serveo"

        # serveo outputs: "Forwarding HTTP traffic from https://xxxxx.serveo.net"
        deadline = time.time() + 15
        while time.time() < deadline:
            line = self._process.stdout.readline()  # type: ignore
            if not line:
                if self._process.poll() is not None:
                    raise RuntimeError(f"SSH tunnel exited with code {self._process.returncode}")
                time.sleep(0.1)
                continue

            line = line.strip()
            logger.debug(f"ssh: {line}")

            if "https://" in line:
                # Extract URL
                for part in line.split():
                    if part.startswith("https://"):
                        self._public_url = part
                        logger.info(f"SSH tunnel: {self._public_url}")
                        return self._public_url

        raise RuntimeError("Timed out waiting for SSH tunnel URL")

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._public_url = None
        self._method = None

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None


class NgrokTunnel:
    """Tunnel using ngrok (requires ``pip install pyngrok``).

    Args:
        authtoken: ngrok auth token. Falls back to ``NGROK_AUTHTOKEN`` env var.
        region: ngrok region (default: auto).
        domain: Custom ngrok domain (for paid plans).
    """

    def __init__(
        self,
        authtoken: Optional[str] = None,
        region: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> None:
        self._authtoken = authtoken or os.environ.get("NGROK_AUTHTOKEN")
        self._region = region
        self._domain = domain
        self._tunnel = None
        self._public_url: Optional[str] = None

    def start(self, local_port: int) -> str:
        if self._public_url and self.is_alive():
            return self._public_url

        try:
            from pyngrok import ngrok, conf
        except ImportError:
            raise ImportError(
                "NgrokTunnel requires pyngrok. Install with: pip install pyngrok"
            )

        if self._authtoken:
            ngrok.set_auth_token(self._authtoken)

        options = {"addr": str(local_port)}
        if self._region:
            pyngrok_config = conf.get_default()
            pyngrok_config.region = self._region
        if self._domain:
            options["domain"] = self._domain

        self._tunnel = ngrok.connect(**options)
        self._public_url = self._tunnel.public_url
        logger.info(f"ngrok tunnel: {self._public_url}")

        # Ensure HTTPS
        if self._public_url and self._public_url.startswith("http://"):
            self._public_url = self._public_url.replace("http://", "https://", 1)

        return self._public_url  # type: ignore

    def stop(self) -> None:
        if self._tunnel:
            try:
                from pyngrok import ngrok
                ngrok.disconnect(self._tunnel.public_url)
            except Exception:
                pass
            self._tunnel = None
        self._public_url = None

    def is_alive(self) -> bool:
        if not self._tunnel:
            return False
        try:
            from pyngrok import ngrok
            tunnels = ngrok.get_tunnels()
            return any(t.public_url == self._tunnel.public_url for t in tunnels)
        except Exception:
            return False
