#!/usr/bin/env python3
"""
h_agent/daemon/server.py - Backend daemon service.

Uses TCP socket for IPC (more compatible than Unix sockets).
"""

import asyncio
import json
import os
import sys
import signal
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Configuration
DAEMON_PORT = int(os.environ.get("H_AGENT_PORT", 19527))
PID_FILE = str(Path.home() / ".h-agent" / "daemon.pid")
SESSION_DIR = Path.home() / ".h-agent" / "sessions"


class SessionManager:
    """Manages sessions with JSON file persistence."""
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.current_session: Optional[str] = None
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._load_index()
    
    def _load_index(self):
        """Load session index from disk."""
        index_file = SESSION_DIR / "index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    self.sessions = json.load(f)
            except json.JSONDecodeError:
                self.sessions = {}
    
    def _save_index(self):
        """Save session index to disk."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        index_file = SESSION_DIR / "index.json"
        with open(index_file, "w") as f:
            json.dump(self.sessions, f, indent=2)
    
    def _session_file(self, session_id: str) -> Path:
        return SESSION_DIR / f"{session_id}.jsonl"
    
    def list_sessions(self) -> list:
        """List all sessions."""
        return sorted(
            self.sessions.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
    
    def create_session(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new session."""
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        meta = {
            "session_id": session_id,
            "name": name or session_id,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }
        
        self.sessions[session_id] = meta
        self._session_file(session_id).touch()
        self._save_index()
        self.current_session = session_id
        return meta
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id not in self.sessions:
            return False
        
        session_file = self._session_file(session_id)
        if session_file.exists():
            session_file.unlink()
        
        del self.sessions[session_id]
        self._save_index()
        
        if self.current_session == session_id:
            self.current_session = None
        return True
    
    def add_message(self, session_id: str, role: str, content: Any) -> bool:
        """Add a message to session history."""
        if session_id not in self.sessions:
            return False
        
        session_file = self._session_file(session_id)
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        
        with open(session_file, "a") as f:
            f.write(json.dumps(turn, ensure_ascii=False) + "\n")
        
        self.sessions[session_id]["message_count"] += 1
        self.sessions[session_id]["updated_at"] = datetime.now().isoformat()
        self._save_index()
        return True
    
    def get_history(self, session_id: str) -> list:
        """Get session message history."""
        session_file = self._session_file(session_id)
        if not session_file.exists():
            return []
        
        messages = []
        with open(session_file) as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return messages
    
    def set_current(self, session_id: str) -> bool:
        """Set current active session."""
        if session_id in self.sessions:
            self.current_session = session_id
            return True
        return False
    
    def get_current(self) -> Optional[str]:
        return self.current_session


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
        
        if method == "ping":
            return {"success": True, "result": "pong"}
        
        elif method == "status":
            return {
                "success": True,
                "result": {
                    "running": self.running,
                    "port": self.port,
                    "current_session": self.session_manager.get_current(),
                    "session_count": len(self.session_manager.sessions),
                }
            }
        
        elif method == "session.list":
            return {
                "success": True,
                "result": self.session_manager.list_sessions()
            }
        
        elif method == "session.create":
            name = params.get("name")
            result = self.session_manager.create_session(name)
            return {"success": True, "result": result}
        
        elif method == "session.get":
            session_id = params.get("session_id")
            session = self.session_manager.get_session(session_id)
            if session:
                return {"success": True, "result": session}
            return {"success": False, "error": "Session not found"}
        
        elif method == "session.delete":
            session_id = params.get("session_id")
            deleted = self.session_manager.delete_session(session_id)
            return {"success": deleted, "result": None if deleted else "Session not found"}
        
        elif method == "session.history":
            session_id = params.get("session_id")
            history = self.session_manager.get_history(session_id)
            return {"success": True, "result": history}
        
        elif method == "session.set_current":
            session_id = params.get("session_id")
            set_ = self.session_manager.set_current(session_id)
            return {"success": set_, "result": None if set_ else "Session not found"}
        
        elif method == "session.add_message":
            session_id = params.get("session_id")
            role = params.get("role", "user")
            content = params.get("content", "")
            added = self.session_manager.add_message(session_id, role, content)
            return {"success": added, "result": None if added else "Failed"}
        
        elif method == "session.get_current":
            current = self.session_manager.get_current()
            return {"success": True, "result": current}
        
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
    
    def signal_handler(sig, frame):
        daemon.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    asyncio.run(daemon.start())


if __name__ == "__main__":
    run_daemon()