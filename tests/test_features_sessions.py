"""
Tests for h_agent.features.sessions module (ContextGuard and SessionStore).
"""
import os
import tempfile
import pytest

os.environ["OPENAI_API_KEY"] = "test"
os.environ["OPENAI_API_BASE"] = "http://localhost:8000"
os.environ["MODEL_ID"] = "test-model"

from h_agent.features.sessions import (
    SessionStore,
    ContextGuard,
)


class TestContextGuard:
    """ContextGuard tests."""

    def test_estimate_tokens(self):
        guard = ContextGuard()
        messages = [{"role": "user", "content": "x" * 1000}]
        tokens = guard.estimate_tokens(messages)
        assert tokens == 250  # 1000 / 4

    def test_estimate_tokens_nested_content(self):
        guard = ContextGuard()
        messages = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
        tokens = guard.estimate_tokens(messages)
        assert tokens >= 0

    def test_should_compact_below_limit(self):
        guard = ContextGuard(safe_limit=100000)
        messages = [{"role": "user", "content": "short"}]
        assert guard.should_compact(messages) is False

    def test_should_compact_above_limit(self):
        guard = ContextGuard(safe_limit=100)
        messages = [{"role": "user", "content": "x" * 1000}]
        assert guard.should_compact(messages) is True

    def test_truncate_tool_results_short(self):
        guard = ContextGuard()
        messages = [{"role": "tool", "content": "short", "tool_call_id": "1"}]
        result = guard.truncate_tool_results(messages, max_len=100)
        assert result[0]["content"] == "short"

    def test_truncate_tool_results_long(self):
        guard = ContextGuard()
        messages = [{"role": "tool", "content": "x" * 200, "tool_call_id": "1"}]
        result = guard.truncate_tool_results(messages, max_len=100)
        assert len(result[0]["content"]) < 200

    def test_compact_messages_preserves_recent(self):
        guard = ContextGuard(safe_limit=100)
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = guard.compact_messages(messages)
        # Should preserve system and recent messages
        assert len(result) <= len(messages)

    def test_compact_messages_few_messages(self):
        guard = ContextGuard()
        messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        result = guard.compact_messages(messages)
        assert result == messages

    def test_guard_api_call_no_compact(self):
        guard = ContextGuard(safe_limit=100000)
        messages = [{"role": "user", "content": "hello"}]
        result, level = guard.guard_api_call(messages)
        assert level == 0
        assert result == messages

    def test_guard_api_call_truncation(self):
        guard = ContextGuard(safe_limit=10)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "x" * 500, "tool_call_id": "1"},
        ]
        result, level = guard.guard_api_call(messages)
        assert level >= 1

    def test_generate_summary(self):
        guard = ContextGuard()
        messages = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second question"},
        ]
        summary = guard._generate_summary(messages)
        assert summary is not None
        assert "first question" in summary or "second question" in summary


class TestSessionStore:
    """SessionStore tests using temp directory."""

    @pytest.fixture
    def store(self, tmp_path):
        return SessionStore(agent_id="test-agent")

    def test_create_session(self, store):
        session_id = store.create_session()
        assert session_id.startswith("sess-")
        assert store.current_session_id == session_id

    def test_load_session_empty(self, store):
        session_id = store.create_session()
        messages = store.load_session(session_id)
        assert messages == []

    def test_save_and_load_turn(self, store):
        session_id = store.create_session()
        store.save_turn("user", "Hello!")
        store.save_turn("assistant", "Hi there!")
        messages = store.load_session(session_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"

    def test_get_recent_sessions(self, store):
        s1 = store.create_session()
        s2 = store.create_session()
        recent = store.get_recent_sessions(limit=5)
        # Should include the 2 we just created
        recent_ids = {r["session_id"] for r in recent}
        assert s1 in recent_ids
        assert s2 in recent_ids

    def test_delete_session(self, store):
        session_id = store.create_session()
        assert store.delete_session(session_id) is True
        assert store.delete_session("nonexistent") is False

    def test_load_nonexistent_session(self, store):
        messages = store.load_session("nonexistent-id")
        assert messages == []

    def test_current_session_default(self, store):
        # Initially no current session
        assert store.current_session_id is None
        # Creating a session sets it as current
        sid = store.create_session()
        assert store.current_session_id == sid
