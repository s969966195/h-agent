#!/usr/bin/env python3
"""
h_agent/daemon/client.py - Client for communicating with daemon.

Uses TCP socket to send JSON-RPC style requests.
Cross-platform: works on Linux/macOS/Windows.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from h_agent.platform_utils import daemon_pid_file

DAEMON_PORT = int(os.environ.get("H_AGENT_PORT", 19527))
PID_FILE = str(daemon_pid_file())
TIMEOUT = 30.0


def get_daemon_port() -> int:
    """Get daemon port from PID file."""
    try:
        with open(PID_FILE) as f:
            data = json.load(f)
            return data.get("port", DAEMON_PORT)
    except (FileNotFoundError, json.JSONDecodeError):
        return DAEMON_PORT


class DaemonClient:
    """Async client for daemon IPC."""
    
    def __init__(self, port: Optional[int] = None):
        self.port = port or DAEMON_PORT
    
    async def _send_request(self, method: str, params: Dict = None) -> Dict:
        """Send request to daemon and get response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.port),
                timeout=TIMEOUT
            )
        except asyncio.TimeoutError:
            raise ConnectionError(f"Daemon not responding (timeout)")
        except OSError:
            raise ConnectionError(f"Daemon not running (port {self.port})")
        
        request = {"method": method, "params": params or {}}
        writer.write(json.dumps(request).encode())
        await writer.drain()
        
        data = await asyncio.wait_for(reader.read(65536), timeout=TIMEOUT)
        writer.close()
        await writer.wait_closed()
        
        return json.loads(data.decode())
    
    def call(self, method: str, params: Dict = None) -> Any:
        """Synchronous wrapper for _send_request."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self._send_request(method, params))
    
    def ping(self) -> bool:
        """Check if daemon is alive."""
        try:
            result = self.call("ping")
            return result.get("success", False)
        except ConnectionError:
            return False
    
    def status(self) -> Dict[str, Any]:
        """Get daemon status."""
        return self.call("status")
    
    # Session methods
    def session_list(self) -> List[Dict]:
        """List all sessions."""
        result = self.call("session.list")
        return result.get("result", [])
    
    def session_create(self, name: Optional[str] = None) -> Dict:
        """Create a new session."""
        return self.call("session.create", {"name": name})
    
    def session_get(self, session_id: str) -> Optional[Dict]:
        """Get session metadata."""
        result = self.call("session.get", {"session_id": session_id})
        return result.get("result")
    
    def session_delete(self, session_id: str) -> bool:
        """Delete a session."""
        result = self.call("session.delete", {"session_id": session_id})
        return result.get("success", False)
    
    def session_history(self, session_id: str) -> List[Dict]:
        """Get session message history."""
        result = self.call("session.history", {"session_id": session_id})
        return result.get("result", [])
    
    def session_set_current(self, session_id: str) -> bool:
        """Set current active session."""
        result = self.call("session.set_current", {"session_id": session_id})
        return result.get("success", False)
    
    def session_get_current(self) -> Optional[str]:
        """Get current session ID."""
        result = self.call("session.get_current")
        return result.get("result")
    
    def session_add_message(self, session_id: str, role: str, content: Any) -> bool:
        """Add a message to session."""
        result = self.call("session.add_message", {
            "session_id": session_id,
            "role": role,
            "content": content,
        })
        return result.get("success", False)


def is_daemon_running() -> bool:
    """Check if daemon process is running."""
    from h_agent.daemon.server import daemon_status as check_daemon_status
    return check_daemon_status().get("running", False)


def get_client() -> DaemonClient:
    """Get client connected to running daemon."""
    port = get_daemon_port()
    return DaemonClient(port)


if __name__ == "__main__":
    # Simple test
    print(f"Daemon running: {is_daemon_running()}")
    if is_daemon_running():
        client = get_client()
        print(f"Status: {client.status()}")
        print(f"Sessions: {client.session_list()}")