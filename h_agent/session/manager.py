#!/usr/bin/env python3
"""
h_agent/session/manager.py - Session management utilities.

Provides high-level session operations with tags and groups support.
"""

import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

SESSION_DIR = Path.home() / ".h-agent" / "sessions"


class SessionManager:
    """
    Standalone session manager that works with JSON files.
    Supports tags, groups, and search.
    """

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.tags_index: Dict[str, Set[str]] = {}  # tag -> session_ids
        self.groups_index: Dict[str, Set[str]] = {}  # group_name -> session_ids
        self.current_session: Optional[str] = None
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._load_index()
        self._load_tags()

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
            json.dump(self.sessions, f, indent=2, ensure_ascii=False)

    def _tags_file(self) -> Path:
        return SESSION_DIR / "tags.json"

    def _load_tags(self):
        """Load tags index from disk."""
        tags_file = self._tags_file()
        if tags_file.exists():
            try:
                with open(tags_file) as f:
                    raw = json.load(f)
                    self.tags_index = {k: set(v) for k, v in raw.get("tags", {}).items()}
                    self.groups_index = {k: set(v) for k, v in raw.get("groups", {}).items()}
            except json.JSONDecodeError:
                self.tags_index = {}
                self.groups_index = {}
        else:
            self.tags_index = {}
            self.groups_index = {}

    def _save_tags(self):
        """Save tags and groups index to disk."""
        tags_file = self._tags_file()
        with open(tags_file, "w") as f:
            json.dump({
                "tags": {k: list(v) for k, v in self.tags_index.items()},
                "groups": {k: list(v) for k, v in self.groups_index.items()},
            }, f, indent=2, ensure_ascii=False)

    def _session_file(self, session_id: str) -> Path:
        return SESSION_DIR / f"{session_id}.jsonl"

    # ---- Basic CRUD ----

    def list_sessions(self, filter_tag: Optional[str] = None, filter_group: Optional[str] = None) -> List[Dict[str, Any]]:
        """List sessions, optionally filtered by tag or group."""
        sessions = sorted(
            self.sessions.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )

        if filter_tag:
            tag_sessions = self.tags_index.get(filter_tag, set())
            sessions = [s for s in sessions if s["session_id"] in tag_sessions]

        if filter_group:
            group_sessions = self.groups_index.get(filter_group, set())
            sessions = [s for s in sessions if s["session_id"] in group_sessions]

        return sessions

    def create_session(self, name: Optional[str] = None, group: Optional[str] = None) -> Dict[str, Any]:
        """Create a new session."""
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        meta = {
            "session_id": session_id,
            "name": name or session_id,
            "group": group,
            "tags": [],
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

        self.sessions[session_id] = meta
        self._session_file(session_id).touch()
        self._save_index()

        if group:
            if group not in self.groups_index:
                self.groups_index[group] = set()
            self.groups_index[group].add(session_id)
            self._save_tags()

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

        # Remove from tags/groups
        for tag_set in self.tags_index.values():
            tag_set.discard(session_id)
        for group_set in self.groups_index.values():
            group_set.discard(session_id)

        del self.sessions[session_id]
        self._save_index()
        self._save_tags()

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

    # ---- Tags ----

    def add_tag(self, session_id: str, tag: str) -> bool:
        """Add a tag to a session."""
        if session_id not in self.sessions:
            return False

        tag = tag.strip().lower()
        if not tag:
            return False

        meta = self.sessions[session_id]
        tags = meta.get("tags", [])
        if tag not in tags:
            tags.append(tag)
            meta["tags"] = tags
            self._save_index()

        if tag not in self.tags_index:
            self.tags_index[tag] = set()
        self.tags_index[tag].add(session_id)
        self._save_tags()
        return True

    def remove_tag(self, session_id: str, tag: str) -> bool:
        """Remove a tag from a session."""
        if session_id not in self.sessions:
            return False

        tag = tag.strip().lower()
        meta = self.sessions[session_id]
        tags = meta.get("tags", [])
        if tag in tags:
            tags.remove(tag)
            meta["tags"] = tags
            self._save_index()

        if tag in self.tags_index:
            self.tags_index[tag].discard(session_id)
            if not self.tags_index[tag]:
                del self.tags_index[tag]
            self._save_tags()
        return True

    def list_tags(self) -> Dict[str, int]:
        """List all tags with session counts."""
        return {tag: len(sessions) for tag, sessions in self.tags_index.items()}

    def get_session_tags(self, session_id: str) -> List[str]:
        """Get tags for a session."""
        return self.sessions.get(session_id, {}).get("tags", [])

    # ---- Groups ----

    def set_group(self, session_id: str, group: Optional[str]) -> bool:
        """Set or clear the group for a session."""
        if session_id not in self.sessions:
            return False

        # Remove from old group
        old_group = self.sessions[session_id].get("group")
        if old_group and old_group in self.groups_index:
            self.groups_index[old_group].discard(session_id)
            if not self.groups_index[old_group]:
                del self.groups_index[old_group]

        # Set new group
        self.sessions[session_id]["group"] = group
        self._save_index()

        if group:
            if group not in self.groups_index:
                self.groups_index[group] = set()
            self.groups_index[group].add(session_id)

        self._save_tags()
        return True

    def list_groups(self) -> Dict[str, int]:
        """List all groups with session counts."""
        return {g: len(sessions) for g, sessions in self.groups_index.items()}

    def get_sessions_in_group(self, group: str) -> List[Dict[str, Any]]:
        """Get all sessions in a group."""
        session_ids = self.groups_index.get(group, set())
        return [self.sessions[sid] for sid in session_ids if sid in self.sessions]

    # ---- Search ----

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search sessions by name, tags, or group."""
        query_lower = query.lower()
        results = []

        for session in self.sessions.values():
            name = session.get("name", "").lower()
            group = session.get("group", "") or ""
            tags = [t for t in session.get("tags", [])]

            # Check name
            name_match = query_lower in name
            # Check group
            group_match = query_lower in group.lower()
            # Check tags
            tag_match = any(query_lower in t for t in tags)
            # Check session ID
            id_match = query_lower in session.get("session_id", "").lower()

            if name_match or group_match or tag_match or id_match:
                results.append(session)

        return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)

    # ---- Rename ----

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """Rename a session."""
        if session_id not in self.sessions:
            return False
        self.sessions[session_id]["name"] = new_name
        self.sessions[session_id]["updated_at"] = datetime.now().isoformat()
        self._save_index()
        return True


# ---- Convenience functions ----

_manager: Optional[SessionManager] = None

def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager

def list_sessions(**kwargs) -> List[Dict[str, Any]]:
    return get_manager().list_sessions(**kwargs)

def create_session(name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return get_manager().create_session(name, **kwargs)

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return get_manager().get_session(session_id)

def delete_session(session_id: str) -> bool:
    return get_manager().delete_session(session_id)

def get_history(session_id: str) -> List[Dict[str, Any]]:
    return get_manager().get_history(session_id)


if __name__ == "__main__":
    mgr = SessionManager()
    print(f"Found {len(mgr.sessions)} sessions")
    for s in mgr.list_sessions()[:5]:
        print(f"  {s['session_id']}: {s.get('name', 'unnamed')} ({s.get('message_count', 0)} msgs)")
    tags = mgr.list_tags()
    if tags:
        print(f"Tags: {tags}")
    groups = mgr.list_groups()
    if groups:
        print(f"Groups: {groups}")
