#!/usr/bin/env python3
"""
h_agent/session/manager.py - Session management utilities.

Provides high-level session operations, independent of daemon.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

SESSION_DIR = Path.home() / ".h-agent" / "sessions"


class SessionManager:
    """
    Standalone session manager that works with JSON files.
    Can be used directly or through the daemon.
    """
    
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
        index_file = SESSION_DIR / "index.json"
        with open(index_file, "w") as f:
            json.dump(self.sessions, f, indent=2)
    
    def _session_file(self, session_id: str) -> Path:
        return SESSION_DIR / f"{session_id}.jsonl"
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions, sorted by updated_at descending."""
        return sorted(
            self.sessions.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
    
    def create_session(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new session."""
        import uuid
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
        """Get session metadata."""
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its history."""
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
    
    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get session message history as list of messages."""
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
    
    def set_current(self, session_id: str) -> bool:
        """Set current active session."""
        if session_id in self.sessions:
            self.current_session = session_id
            return True
        return False
    
    def get_current(self) -> Optional[str]:
        """Get current session ID."""
        return self.current_session


# Standalone instance for direct usage
_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


# Convenience functions
def list_sessions() -> List[Dict[str, Any]]:
    return get_manager().list_sessions()


def create_session(name: Optional[str] = None) -> Dict[str, Any]:
    return get_manager().create_session(name)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return get_manager().get_session(session_id)


def delete_session(session_id: str) -> bool:
    return get_manager().delete_session(session_id)


def get_history(session_id: str) -> List[Dict[str, Any]]:
    return get_manager().get_history(session_id)


if __name__ == "__main__":
    # Quick test
    mgr = SessionManager()
    print(f"Found {len(mgr.sessions)} sessions")
    for s in mgr.list_sessions()[:5]:
        print(f"  {s['session_id']}: {s.get('name', 'unnamed')} ({s.get('message_count', 0)} msgs)")
