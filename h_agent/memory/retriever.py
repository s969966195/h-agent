#!/usr/bin/env python3
"""
h_agent/memory/retriever.py - Memory retrieval from historical sessions.

Provides semantic and keyword-based search across all past sessions,
extracted summaries, and long-term memories. Helps the agent recall
relevant context from previous conversations without reloading full history.

Usage:
    results = search_memory("authentication JWT refresh")
    for r in results:
        print(f"[{r['source']}] {r['session_id']}: {r['excerpt']}")
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Shared session history path
SESSION_DIR = Path.home() / ".h-agent" / "sessions"
MEMORY_DIR = Path.home() / ".h-agent" / "memory"
SUMMARIES_DIR = MEMORY_DIR / "summaries"


# ============================================================
# Memory Retriever
# ============================================================

class MemoryRetriever:
    """
    Search across historical sessions and stored memories.

    Capabilities:
    - Keyword search in session histories
    - Load and search stored LLM summaries
    - Search long-term memory entries
    - Combine results with relevance ranking
    - Time-based filtering (last N days)
    """

    def __init__(self, session_dir: Path = None, summaries_dir: Path = None):
        self.session_dir = session_dir or SESSION_DIR
        self.summaries_dir = summaries_dir or SUMMARIES_DIR

    # ---- Session history search ----

    def search_sessions(
        self,
        query: str,
        limit: int = 10,
        days_back: int = None,
        session_ids: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search historical sessions by keyword.

        Args:
            query: Search query
            limit: Max results to return
            days_back: Only search sessions from last N days (None = all)
            session_ids: Optional list of specific session IDs to search

        Returns:
            List of result dicts with session_id, excerpt, timestamp, score
        """
        results = []
        query_lower = query.lower()

        # Determine which session files to search
        if session_ids:
            files_to_search = [
                (sid, self.session_dir / f"{sid}.jsonl")
                for sid in session_ids
            ]
        else:
            if not self.session_dir.exists():
                return []
            files_to_search = []
            for f in self.session_dir.glob("*.jsonl"):
                if f.name == "index.json" or f.name == "tags.json":
                    continue
                session_id = f.stem
                files_to_search.append((session_id, f))

        cutoff_time = None
        if days_back:
            cutoff_time = datetime.now() - timedelta(days=days_back)

        for session_id, session_file in files_to_search:
            if not session_file.exists():
                continue

            try:
                messages = self._load_messages(session_file)
            except (json.JSONDecodeError, OSError):
                continue

            # Time filter
            if cutoff_time:
                recent_enough = False
                for msg in messages:
                    ts = msg.get("timestamp", "")
                    if ts:
                        try:
                            msg_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if msg_time.replace(tzinfo=None) >= cutoff_time:
                                recent_enough = True
                                break
                        except ValueError:
                            pass
                if not recent_enough:
                    continue

            # Search in messages
            matches = self._find_matches(query_lower, messages)
            if matches:
                # Score = number of matches * recency factor
                score = len(matches)
                results.append({
                    "source": "session",
                    "session_id": session_id,
                    "matches": matches,
                    "message_count": len(messages),
                    "score": score,
                    "excerpts": [m["excerpt"] for m in matches[:3]],
                })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def _load_messages(self, path: Path) -> List[Dict]:
        """Load messages from a JSONL session file."""
        messages = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return messages

    def _find_matches(
        self,
        query_lower: str,
        messages: List[Dict],
    ) -> List[Dict]:
        """Find query matches in messages."""
        matches = []
        query_words = query_lower.split()

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            content_lower = content.lower()

            # Word-level matching
            word_hits = sum(1 for w in query_words if w in content_lower)
            if word_hits == 0:
                continue

            # Exact phrase match is strongest
            phrase_hit = query_lower in content_lower

            # Extract relevant snippet
            excerpt = self._extract_snippet(content, query_lower)

            matches.append({
                "role": role,
                "excerpt": excerpt,
                "phrase_hit": phrase_hit,
                "word_hits": word_hits,
            })

        return matches

    def _extract_snippet(self, content: str, query: str, context: int = 80) -> str:
        """Extract a relevant snippet around the query match."""
        content_lower = content.lower()
        idx = content_lower.find(query)

        if idx == -1:
            # Find first query word
            for word in query.split():
                idx = content_lower.find(word)
                if idx != -1:
                    break

        if idx == -1:
            return content[:200] + "..." if len(content) > 200 else content

        start = max(0, idx - context)
        end = min(len(content), idx + len(query) + context)
        snippet = content[start:end]

        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet.replace("\n", " ").strip()

    # ---- Summary search ----

    def search_summaries(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search across LLM-generated session summaries.

        These summaries are more semantically rich than raw session text.
        """
        if not self.summaries_dir.exists():
            return []

        results = []
        query_lower = query.lower()

        for summary_file in self.summaries_dir.glob("*.json"):
            try:
                with open(summary_file, encoding="utf-8") as f:
                    data = json.load(f)

                summary = data.get("summary", "")
                session_id = data.get("session_id", summary_file.stem)

                if not summary:
                    continue

                if query_lower in summary.lower():
                    snippet = self._extract_snippet(summary, query_lower)
                    results.append({
                        "source": "summary",
                        "session_id": session_id,
                        "summary": summary,
                        "excerpt": snippet,
                        "score": summary.lower().count(query_lower),
                    })
            except (json.JSONDecodeError, OSError):
                pass

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # ---- Unified search ----

    def search(
        self,
        query: str,
        limit: int = 10,
        include_sessions: bool = True,
        include_summaries: bool = True,
        include_long_term: bool = True,
        days_back: int = 30,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Unified search across all memory sources.

        Returns a dict with keys: 'sessions', 'summaries', 'long_term'
        """
        results = {}

        if include_sessions:
            results["sessions"] = self.search_sessions(
                query, limit=limit, days_back=days_back
            )

        if include_summaries:
            results["summaries"] = self.search_summaries(query, limit=limit)

        if include_long_term:
            from h_agent.memory.long_term import search_memory
            results["long_term"] = search_memory(query)

        return results

    # ---- Recent context loader ----

    def get_recent_context(self, session_ids: List[str] = None, max_messages: int = 20) -> str:
        """
        Build a context string from recent session history.

        Useful for giving the agent quick access to recent conversations
        without loading full history.
        """
        parts = ["[Recent Session History]"]

        if not session_ids:
            # Get most recent sessions
            if self.session_dir.exists():
                sessions = []
                for f in self.session_dir.glob("*.jsonl"):
                    if f.name in ("index.json", "tags.json"):
                        continue
                    stat = f.stat()
                    sessions.append((f.stem, stat.st_mtime))
                sessions.sort(key=lambda x: x[1], reverse=True)
                session_ids = [s[0] for s in sessions[:3]]
            else:
                return ""

        for sid in session_ids[:3]:
            session_file = self.session_dir / f"{sid}.jsonl"
            if not session_file.exists():
                continue

            messages = self._load_messages(session_file)
            if not messages:
                continue

            parts.append(f"\n## Session {sid}")

            # Get last N messages
            recent = messages[-max_messages:]
            for msg in recent:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    content = content[:300] + "..." if len(content) > 300 else content
                    content = content.replace("\n", " ")
                    parts.append(f"[{role}]: {content}")

        return "\n".join(parts)


# ============================================================
# Convenience function
# ============================================================

_retriever: Optional[MemoryRetriever] = None

def _get_retriever() -> MemoryRetriever:
    global _retriever
    if _retriever is None:
        _retriever = MemoryRetriever()
    return _retriever


def search_memory(
    query: str,
    limit: int = 10,
    include_sessions: bool = True,
    include_summaries: bool = True,
    include_long_term: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search across all memory sources.

    Returns dict with keys: sessions, summaries, long_term
    """
    return _get_retriever().search(
        query,
        limit=limit,
        include_sessions=include_sessions,
        include_summaries=include_summaries,
        include_long_term=include_long_term,
    )
