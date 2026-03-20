#!/usr/bin/env python3
"""
h_agent/daemon/server.py - Backend daemon service.

Uses TCP socket for IPC (more compatible than Unix sockets).
Cross-platform: works on Linux/macOS/Windows.

Features:
- Session auto-recovery on startup
- Daemon status reporting
- Crash handler integration
- Session management with tags/groups
"""

import asyncio
import json
import os
import sys
import signal
from pathlib import Path
from typing import Dict, Any

from h_agent.platform_utils import daemon_pid_file, IS_WINDOWS
from h_agent.session.manager import SessionManager
from h_agent.daemon.recovery import SessionRecovery, CrashHandler, AutoStartManager, AutoStartConfig

# Configuration
DAEMON_PORT = int(os.environ.get("H_AGENT_PORT", 19527))
PID_FILE = str(daemon_pid_file())


class DaemonServer:
    """Async IPC server using TCP socket."""

    def __init__(self, port: int = DAEMON_PORT):
        self.port = port
        self.session_manager = SessionManager()
        self.running = False
        self.server = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single client connection."""
        try:
            data = await reader.read(65536)
            if not data:
                return

            request = json.loads(data.decode())
            response = await self.process_request(request)

            writer.write(json.dumps(response).encode())
            await writer.drain()
        except Exception as e:
            error_response = {"error": str(e), "success": False}
            writer.write(json.dumps(error_response).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def process_request(self, request: Dict) -> Dict:
        """Process a JSON-RPC style request."""
        method = request.get("method", "")
        params = request.get("params", {})
        mgr = self.session_manager

        if method == "ping":
            return {"success": True, "result": "pong"}

        elif method == "status":
            return {
                "success": True,
                "result": {
                    "running": self.running,
                    "port": self.port,
                    "current_session": mgr.get_current(),
                    "session_count": len(mgr.sessions),
                }
            }

        elif method == "session.list":
            filter_tag = params.get("tag")
            filter_group = params.get("group")
            return {"success": True, "result": mgr.list_sessions(filter_tag, filter_group)}

        elif method == "session.create":
            name = params.get("name")
            group = params.get("group")
            result = mgr.create_session(name, group)
            return {"success": True, "result": result}

        elif method == "session.get":
            session_id = params.get("session_id")
            session = mgr.get_session(session_id)
            if session:
                return {"success": True, "result": session}
            return {"success": False, "error": "Session not found"}

        elif method == "session.delete":
            session_id = params.get("session_id")
            deleted = mgr.delete_session(session_id)
            return {"success": deleted, "result": None if deleted else "Session not found"}

        elif method == "session.history":
            session_id = params.get("session_id")
            history = mgr.get_history(session_id)
            return {"success": True, "result": history}

        elif method == "session.set_current":
            session_id = params.get("session_id")
            ok = mgr.set_current(session_id)
            return {"success": ok, "result": None if ok else "Session not found"}

        elif method == "session.add_message":
            session_id = params.get("session_id")
            role = params.get("role", "user")
            content = params.get("content", "")
            added = mgr.add_message(session_id, role, content)
            return {"success": added, "result": None if added else "Failed"}

        elif method == "session.get_current":
            current = mgr.get_current()
            return {"success": True, "result": current}

        elif method == "session.search":
            query = params.get("query", "")
            results = mgr.search(query)
            return {"success": True, "result": results}

        elif method == "session.rename":
            session_id = params.get("session_id")
            new_name = params.get("name")
            ok = mgr.rename_session(session_id, new_name)
            return {"success": ok, "result": None if ok else "Session not found"}

        # ---- Tags ----
        elif method == "session.tag.add":
            session_id = params.get("session_id")
            tag = params.get("tag")
            ok = mgr.add_tag(session_id, tag)
            return {"success": ok, "result": None if ok else "Failed"}

        elif method == "session.tag.remove":
            session_id = params.get("session_id")
            tag = params.get("tag")
            ok = mgr.remove_tag(session_id, tag)
            return {"success": ok, "result": None if ok else "Failed"}

        elif method == "session.tag.list":
            tags = mgr.list_tags()
            return {"success": True, "result": tags}

        elif method == "session.tag.get":
            session_id = params.get("session_id")
            tags = mgr.get_session_tags(session_id)
            return {"success": True, "result": tags}

        # ---- Groups ----
        elif method == "session.group.set":
            session_id = params.get("session_id")
            group = params.get("group")
            ok = mgr.set_group(session_id, group)
            return {"success": ok, "result": None if ok else "Failed"}

        elif method == "session.group.list":
            groups = mgr.list_groups()
            return {"success": True, "result": groups}

        elif method == "session.group.sessions":
            group = params.get("group")
            sessions = mgr.get_sessions_in_group(group)
            return {"success": True, "result": sessions}

        else:
            return {"success": False, "error": f"Unknown method: {method}"}

    async def start(self):
        """Start the daemon server."""
        self.server = await asyncio.start_server(
            self.handle_client,
            host="127.0.0.1",
            port=self.port
        )
        self.running = True

        # Save PID and port
        Path(PID_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, "w") as f:
            json.dump({"pid": os.getpid(), "port": self.port}, f)

        print(f"Daemon started on port {self.port}")

        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        """Stop the daemon."""
        self.running = False
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)


def daemon_status() -> Dict[str, Any]:
    """Check if daemon is running."""
    pid_file = Path(PID_FILE)
    if not pid_file.exists():
        return {"running": False}

    try:
        with open(pid_file) as f:
            data = json.load(f)
        pid = data.get("pid", 0)
        port = data.get("port", DAEMON_PORT)

        # Check if process is alive
        os.kill(pid, 0)
        return {"running": True, "pid": pid, "port": port}
    except (ValueError, ProcessLookupError, PermissionError, json.JSONDecodeError):
        return {"running": False}


def run_daemon(port: int = DAEMON_PORT):
    """Run the daemon (blocking)."""
    daemon = DaemonServer(port)

    # Integrate session recovery
    recovery = SessionRecovery()
    recovery_report = recovery.recover(daemon.session_manager)
    if recovery_report.get("recovered"):
        print(f"[Recovery] Restored session {recovery_report['session_id']} "
              f"({recovery_report['message_count']} messages)")
    if recovery_report.get("crashed"):
        print(f"[Recovery] Previous session crashed, recovered gracefully")

    def signal_handler(sig, frame):
        daemon.stop()
        sys.exit(0)

    if not IS_WINDOWS:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    else:
        def windows_signal_handler(sig):
            daemon.stop()
            sys.exit(0)
        try:
            signal.signal(signal.CTRL_C_EVENT, windows_signal_handler)
        except (AttributeError, ValueError):
            pass

    try:
        asyncio.run(daemon.start())
    except Exception as e:
        # Record crash and re-raise
        import traceback
        tb = traceback.format_exc()
        CrashHandler.record_crash(
            exception_type=type(e).__name__,
            exception_message=str(e),
            traceback=tb,
            session_id=daemon.session_manager.get_current(),
        )
        raise


if __name__ == "__main__":
    run_daemon()
