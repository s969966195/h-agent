#!/usr/bin/env python3
"""
h_agent/memory/summarizer.py - LLM-powered intelligent context summarization.

Replaces the naive "extract user messages" approach with actual LLM-generated
summaries that preserve key information: decisions, facts, code changes, etc.

Used by ContextGuard when context overflow is detected.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "sk-dummy"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
MODEL = os.getenv("MODEL_ID", "gpt-4o")

# Memory store directory (shared with long_term)
MEMORY_DIR = Path.home() / ".h-agent" / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

SUMMARIES_DIR = MEMORY_DIR / "summaries"
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Core summarizer
# ============================================================

class SmartSummarizer:
    """
    LLM-based message summarizer that generates high-quality context summaries.

    Key improvements over naive approach:
    - Uses actual LLM to understand what matters in the conversation
    - Preserves decisions, facts, code changes, and preferences
    - Removes noise while keeping essential context
    - Stores summaries for later retrieval
    """

    SYSTEM_PROMPT = """You are a context summarizer for an AI coding agent session.

Your job is to create a concise but information-dense summary of the conversation history.

FORMAT REQUIREMENTS:
- Write in English or match the language of the conversation
- Be terse and factual — no filler, no opinions
- Preserve: decisions made, facts stated, code written, user preferences, errors encountered, solutions found
- Remove: greetings, pleasantries, obvious repetitions, debugging noise
- Structure as bullet points grouped by topic

KEEP:
  ✓ Decisions: "User prefers feature flags over AB testing"
  ✓ Facts: "Project uses Python 3.11, FastAPI, PostgreSQL"
  ✓ Code changes: "Added auth middleware to /api routes"
  ✓ Preferences: "User wants verbose logging in development"
  ✓ Errors: "Bug: race condition in worker pool (fixed by adding lock)"
  ✓ Questions asked: "User asked how to deploy to Fly.io"
  ✓ Goals: "User is building a REST API for task management"

DROP:
  ✗ "Hello", "Thanks", "Please help me"
  ✗ Repeated restatements of the same request
  ✗ Tool output noise (unless it contains decisions/errors)
  ✗ Empty or trivial exchanges

OUTPUT: A structured summary, max 600 words.
"""

    def __init__(self, model: str = None):
        self.model = model or MODEL
        self.client = client

    def summarize(self, messages: List[Dict[str, Any]], session_id: str = None) -> str:
        """
        Generate an LLM summary of a list of messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            session_id: Optional session ID for storage

        Returns:
            A high-quality summary string
        """
        if not messages:
            return ""

        # Format messages for the prompt
        formatted = self._format_messages(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Summarize this conversation:\n\n{formatted}"},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            summary = response.choices[0].message.content or ""
        except Exception as e:
            # Fallback: extract user messages only
            summary = self._fallback_summary(messages)

        # Store the summary
        if session_id:
            self._save_summary(session_id, messages, summary)

        return summary

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages for the summarization prompt."""
        lines = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")

            # Handle tool messages — truncate to first 500 chars
            if role == "tool":
                content = content[:500] + "..." if len(content) > 500 else content
                lines.append(f"[TOOL RESULT]: {content}")
            elif role == "system":
                # Skip system prompts in summary (they're usually boilerplate)
                continue
            else:
                # Truncate very long messages
                if len(content) > 2000:
                    content = content[:2000] + "..."
                lines.append(f"[{role.upper()}]: {content}")

        return "\n".join(lines)

    def _fallback_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Fallback when LLM is unavailable — simple extraction."""
        user_msgs = []
        assistant_msgs = []

        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:500] if msg.get("content") else ""

            if role == "user":
                user_msgs.append(content)
            elif role == "assistant" and content:
                assistant_msgs.append(content[:200])

        parts = []
        if user_msgs:
            parts.append("User requests: " + "; ".join(user_msgs[-5:]))
        if assistant_msgs:
            parts.append("Agent responses (excerpts): " + "; ".join(assistant_msgs[-3:]))

        return " | ".join(parts) if parts else "Summary unavailable."

    def _save_summary(self, session_id: str, original_messages: List[Dict], summary: str):
        """Persist summary for potential later retrieval."""
        path = SUMMARIES_DIR / f"{session_id}.json"
        data = {
            "session_id": session_id,
            "message_count": len(original_messages),
            "summary": summary,
            "saved_at": self._iso_now(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Non-fatal if we can't write

    def load_summary(self, session_id: str) -> Optional[str]:
        """Load a previously saved summary for a session."""
        path = SUMMARIES_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("summary")
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime
        return datetime.now().isoformat()


# ============================================================
# Convenience function
# ============================================================

def summarize_messages(
    messages: List[Dict[str, Any]],
    session_id: str = None,
    model: str = None,
) -> str:
    """
    Summarize a list of messages using LLM.

    Args:
        messages: Conversation messages
        session_id: Optional session ID for caching
        model: Override model ID

    Returns:
        Summary string
    """
    summarizer = SmartSummarizer(model=model)
    return summarizer.summarize(messages, session_id=session_id)
