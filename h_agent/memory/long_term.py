#!/usr/bin/env python3
"""
h_agent/memory/long_term.py - Long-term persistent memory for h-agent.

Stores and retrieves:
  - User preferences (coding style, tools, communication style)
  - Project information (language, framework, architecture)
  - Key decisions (why something was chosen, trade-offs discussed)
  - Facts about the user's environment

Data lives in ~/.h-agent/memory/long_term.json
Supports namespace isolation so different projects/contexts don't mix.

Usage:
    remember("user", "prefers_explain_with_examples", True)
    prefs = recall("user", "preferences")
    facts = recall("project", "tech_stack")
"""

import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, List, Dict

MEMORY_DIR = Path.home() / ".h-agent" / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
LONG_TERM_FILE = MEMORY_DIR / "long_term.json"
INDEX_FILE = MEMORY_DIR / "memory_index.json"


# ============================================================
# Memory entry types
# ============================================================

class MemoryType:
    USER = "user"           # User preferences and traits
    PROJECT = "project"     # Project-specific information
    DECISION = "decision"   # Architectural/technical decisions
    FACT = "fact"           # General facts about the environment
    ERROR = "error"         # Bugs, errors, and their solutions


# ============================================================
# LongTermMemory store
# ============================================================

class LongTermMemory:
    """
    Persistent key-value + rich memory store.

    Supports:
    - Simple key-value: remember("user", "language", "Chinese")
    - Rich entries: remember("decision", entry_with_reason)
    - Namespaces to isolate different contexts
    - Automatic indexing for fast retrieval
    """

    def __init__(self):
        self._data: Dict[str, List[Dict]] = {
            MemoryType.USER: [],
            MemoryType.PROJECT: [],
            MemoryType.DECISION: [],
            MemoryType.FACT: [],
            MemoryType.ERROR: [],
        }
        self._load()

    # ---- Persistence ----

    def _load(self):
        """Load memory from disk."""
        if LONG_TERM_FILE.exists():
            try:
                with open(LONG_TERM_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
                    # Merge with defaults in case schema grew
                    for k, v in raw.items():
                        if k in self._data:
                            self._data[k] = v
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        """Persist memory to disk."""
        try:
            with open(LONG_TERM_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
        self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild full-text search index."""
        index = {}
        for mem_type, entries in self._data.items():
            for entry in entries:
                key = entry.get("key", "")
                content = entry.get("content", "")
                value = entry.get("value", "")
                text = f"{key} {content} {value}".lower()
                for word in text.split():
                    if len(word) > 2:
                        if word not in index:
                            index[word] = []
                        index[word].append({
                            "type": mem_type,
                            "key": key,
                        })
        try:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f)
        except OSError:
            pass

    # ---- Core operations ----

    def set(self, mem_type: str, key: str, value: Any, reason: str = None, tags: List[str] = None) -> bool:
        """
        Store a memory entry.

        Args:
            mem_type: Memory type (user/project/decision/fact/error)
            key: Unique identifier within this type
            value: The value to store (any JSON-serializable type)
            reason: Why this was recorded (important for decisions)
            tags: Optional tags for retrieval

        Returns:
            True on success
        """
        if mem_type not in self._data:
            return False

        entry = {
            "id": str(uuid.uuid4())[:8],
            "key": key,
            "value": value,
            "content": str(value),
            "reason": reason or "",
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # Upsert: replace existing entry with same key
        self._data[mem_type] = [
            e for e in self._data[mem_type] if e.get("key") != key
        ]
        self._data[mem_type].append(entry)
        self._save()
        return True

    def get(self, mem_type: str, key: str) -> Optional[Any]:
        """Get a value by type and key."""
        for entry in self._data.get(mem_type, []):
            if entry.get("key") == key:
                return entry.get("value")
        return None

    def get_entry(self, mem_type: str, key: str) -> Optional[Dict]:
        """Get full entry by type and key."""
        for entry in self._data.get(mem_type, []):
            if entry.get("key") == key:
                return entry
        return None

    def delete(self, mem_type: str, key: str) -> bool:
        """Delete an entry by type and key."""
        before = len(self._data.get(mem_type, []))
        self._data[mem_type] = [
            e for e in self._data.get(mem_type, []) if e.get("key") != key
        ]
        if len(self._data[mem_type]) < before:
            self._save()
            return True
        return False

    def list_entries(self, mem_type: str) -> List[Dict]:
        """List all entries of a given type."""
        return list(self._data.get(mem_type, []))

    def search(self, query: str, mem_type: str = None) -> List[Dict]:
        """
        Search memories by keyword.

        Args:
            query: Search term
            mem_type: Optional filter by memory type

        Returns:
            List of matching entries with context
        """
        results = []
        query_lower = query.lower()
        types_to_search = [mem_type] if mem_type else list(self._data.keys())

        for mtype in types_to_search:
            for entry in self._data.get(mtype, []):
                key = entry.get("key", "").lower()
                content = entry.get("content", "").lower()
                reason = entry.get("reason", "").lower()
                tags = " ".join(entry.get("tags", [])).lower()

                if (query_lower in key or
                    query_lower in content or
                    query_lower in reason or
                    query_lower in tags):
                    results.append({
                        **entry,
                        "type": mtype,
                        "match_field": (
                            "key" if query_lower in key else
                            "reason" if query_lower in reason else
                            "content"
                        ),
                    })

        return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)

    def all_as_text(self, mem_type: str = None) -> str:
        """
        Dump memories as readable text, useful for injecting into context.

        Args:
            mem_type: Filter by type (None = all types)

        Returns:
            Formatted string suitable for system prompt injection
        """
        lines = ["[Long-term Memory]"]
        types_to_show = [mem_type] if mem_type else list(self._data.keys())

        for mtype in types_to_show:
            entries = self._data.get(mtype, [])
            if not entries:
                continue
            lines.append(f"\n## {mtype.upper()}")
            for e in entries:
                key = e.get("key", "")
                value = e.get("value", "")
                reason = e.get("reason", "")
                tags = e.get("tags", [])
                tag_str = f" [{', '.join('#'+t for t in tags)}]" if tags else ""
                reason_str = f" — reason: {reason}" if reason else ""
                lines.append(f"  • {key}: {value}{reason_str}{tag_str}")

        return "\n".join(lines)

    # ---- Stats ----

    def stats(self) -> Dict[str, int]:
        """Return memory counts by type."""
        return {k: len(v) for k, v in self._data.items()}


# ============================================================
# Module-level convenience API
# ============================================================

_memory: Optional[LongTermMemory] = None

def _get_memory() -> LongTermMemory:
    global _memory
    if _memory is None:
        _memory = LongTermMemory()
    return _memory


def remember(
    mem_type: str,
    key: str,
    value: Any,
    reason: str = None,
    tags: List[str] = None,
) -> bool:
    """
    Store a memory.

    Args:
        mem_type: 'user', 'project', 'decision', 'fact', or 'error'
        key: Memory key (unique within type)
        value: Value to store
        reason: Optional explanation (important for decisions)
        tags: Optional tags

    Returns:
        True on success

    Example:
        remember("user", "language", "Chinese", tags=["communication"])
        remember("decision", "use_sqlite", "Simplicity over scalability", reason="MVP phase")
        remember("project", "framework", "FastAPI")
    """
    return _get_memory().set(mem_type, key, value, reason=reason, tags=tags)


def recall(mem_type: str, key: str) -> Optional[Any]:
    """Retrieve a specific memory value."""
    return _get_memory().get(mem_type, key)


def recall_entry(mem_type: str, key: str) -> Optional[Dict]:
    """Retrieve full memory entry."""
    return _get_memory().get_entry(mem_type, key)


def forget(mem_type: str, key: str) -> bool:
    """Delete a memory."""
    return _get_memory().delete(mem_type, key)


def list_memories(mem_type: str = None) -> List[Dict]:
    """List all memories, optionally filtered by type."""
    return _get_memory().list_entries(mem_type) if mem_type else [
        {"type": t, "entries": entries}
        for t, entries in _get_memory()._data.items()
    ]


def search_memory(query: str, mem_type: str = None) -> List[Dict]:
    """Search memories by keyword."""
    return _get_memory().search(query, mem_type=mem_type)


def memory_dump(mem_type: str = None) -> str:
    """Get all memories as formatted text for context injection."""
    return _get_memory().all_as_text(mem_type=mem_type)


def memory_stats() -> Dict[str, int]:
    """Get memory statistics."""
    return _get_memory().stats()
