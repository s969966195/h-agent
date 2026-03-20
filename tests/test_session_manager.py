"""
Tests for h_agent.session.manager module.
"""
import os
import sys
import tempfile
import pytest

# Set test environment
os.environ["OPENAI_API_KEY"] = "test"
os.environ["OPENAI_API_BASE"] = "http://localhost:8000"
os.environ["MODEL_ID"] = "test-model"

from h_agent.session.manager import (
    SessionManager,
    get_manager,
    create_session,
    get_session,
    delete_session,
    list_sessions,
    get_history,
)


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    """Create a SessionManager with temp storage."""
    # Patch SESSION_DIR to temp location
    from h_agent.session import manager as sm_module
    test_dir = tmp_path / "sessions"
    test_dir.mkdir()
    monkeypatch.setattr(sm_module, "SESSION_DIR", test_dir)
    m = SessionManager()
    yield m
    # Reset singleton
    sm_module._manager = None


class TestSessionManager:
    """SessionManager tests."""

    def test_create_session(self, mgr):
        session = mgr.create_session()
        assert "session_id" in session
        assert session["session_id"].startswith("sess-")
        assert mgr.current_session == session["session_id"]

    def test_create_named_session(self, mgr):
        session = mgr.create_session(name="my-project")
        assert session["name"] == "my-project"

    def test_create_session_with_group(self, mgr):
        session = mgr.create_session(group="work")
        assert session["group"] == "work"

    def test_get_session(self, mgr):
        created = mgr.create_session()
        fetched = mgr.get_session(created["session_id"])
        assert fetched is not None
        assert fetched["session_id"] == created["session_id"]

    def test_get_session_not_found(self, mgr):
        assert mgr.get_session("nonexistent") is None

    def test_delete_session(self, mgr):
        session = mgr.create_session()
        sid = session["session_id"]
        assert mgr.delete_session(sid) is True
        assert mgr.get_session(sid) is None

    def test_delete_session_not_found(self, mgr):
        assert mgr.delete_session("nonexistent") is False

    def test_add_message(self, mgr):
        session = mgr.create_session()
        sid = session["session_id"]
        result = mgr.add_message(sid, "user", "Hello!")
        assert result is True
        history = mgr.get_history(sid)
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello!"

    def test_add_message_not_found(self, mgr):
        result = mgr.add_message("nonexistent", "user", "Hello!")
        assert result is False

    def test_get_history_empty(self, mgr):
        session = mgr.create_session()
        history = mgr.get_history(session["session_id"])
        assert history == []

    def test_get_history(self, mgr):
        session = mgr.create_session()
        sid = session["session_id"]
        mgr.add_message(sid, "user", "Hello")
        mgr.add_message(sid, "assistant", "Hi there")
        history = mgr.get_history(sid)
        assert len(history) == 2

    def test_list_sessions(self, mgr):
        mgr.create_session()
        mgr.create_session()
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_filter_tag(self, mgr):
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        mgr.add_tag(s1["session_id"], "important")
        sessions = mgr.list_sessions(filter_tag="important")
        assert len(sessions) == 1

    def test_list_sessions_filter_group(self, mgr):
        mgr.create_session(group="work")
        mgr.create_session(group="personal")
        sessions = mgr.list_sessions(filter_group="work")
        assert len(sessions) == 1

    def test_set_current(self, mgr):
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        mgr.set_current(s1["session_id"])
        assert mgr.get_current() == s1["session_id"]
        mgr.set_current(s2["session_id"])
        assert mgr.get_current() == s2["session_id"]

    def test_set_current_invalid(self, mgr):
        assert mgr.set_current("nonexistent") is False


class TestSessionTags:
    """Tag management tests."""

    def test_add_tag(self, mgr):
        session = mgr.create_session()
        result = mgr.add_tag(session["session_id"], "urgent")
        assert result is True
        tags = mgr.get_session_tags(session["session_id"])
        assert "urgent" in tags

    def test_add_duplicate_tag(self, mgr):
        session = mgr.create_session()
        mgr.add_tag(session["session_id"], "urgent")
        mgr.add_tag(session["session_id"], "urgent")
        tags = mgr.get_session_tags(session["session_id"])
        assert tags.count("urgent") == 1

    def test_remove_tag(self, mgr):
        session = mgr.create_session()
        mgr.add_tag(session["session_id"], "urgent")
        result = mgr.remove_tag(session["session_id"], "urgent")
        assert result is True
        assert "urgent" not in mgr.get_session_tags(session["session_id"])

    def test_list_tags(self, mgr):
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        mgr.add_tag(s1["session_id"], "work")
        mgr.add_tag(s2["session_id"], "work")
        mgr.add_tag(s1["session_id"], "urgent")
        tags = mgr.list_tags()
        assert tags.get("work") == 2
        assert tags.get("urgent") == 1

    def test_tag_normalized_to_lowercase(self, mgr):
        session = mgr.create_session()
        mgr.add_tag(session["session_id"], "IMPORTANT")
        tags = mgr.get_session_tags(session["session_id"])
        assert "important" in tags


class TestSessionGroups:
    """Group management tests."""

    def test_set_group(self, mgr):
        session = mgr.create_session()
        result = mgr.set_group(session["session_id"], "project-a")
        assert result is True
        updated = mgr.get_session(session["session_id"])
        assert updated["group"] == "project-a"

    def test_clear_group(self, mgr):
        session = mgr.create_session(group="old")
        mgr.set_group(session["session_id"], None)
        updated = mgr.get_session(session["session_id"])
        assert updated.get("group") is None

    def test_list_groups(self, mgr):
        mgr.create_session(group="work")
        mgr.create_session(group="work")
        mgr.create_session(group="personal")
        groups = mgr.list_groups()
        assert groups.get("work") == 2
        assert groups.get("personal") == 1

    def test_get_sessions_in_group(self, mgr):
        mgr.create_session(group="work")
        mgr.create_session(group="personal")
        sessions = mgr.get_sessions_in_group("work")
        assert len(sessions) == 1
        assert sessions[0]["group"] == "work"


class TestSessionSearch:
    """Search functionality tests."""

    def test_search_by_name(self, mgr):
        mgr.create_session(name="my-project")
        mgr.create_session(name="other")
        results = mgr.search("my-project")
        assert len(results) == 1
        assert results[0]["name"] == "my-project"

    def test_search_by_tag(self, mgr):
        s1 = mgr.create_session()
        mgr.create_session()
        mgr.add_tag(s1["session_id"], "important")
        results = mgr.search("important")
        assert len(results) == 1

    def test_search_by_group(self, mgr):
        mgr.create_session(group="secret-project")
        mgr.create_session()
        results = mgr.search("secret")
        assert len(results) == 1

    def test_search_no_results(self, mgr):
        mgr.create_session()
        results = mgr.search("nonexistent")
        assert len(results) == 0


class TestSessionRename:
    """Rename functionality tests."""

    def test_rename_session(self, mgr):
        session = mgr.create_session(name="old-name")
        result = mgr.rename_session(session["session_id"], "new-name")
        assert result is True
        updated = mgr.get_session(session["session_id"])
        assert updated["name"] == "new-name"

    def test_rename_not_found(self, mgr):
        result = mgr.rename_session("nonexistent", "new-name")
        assert result is False


class TestConvenienceFunctions:
    """Module-level convenience function tests."""

    def test_convenience_functions(self, mgr):
        # These use the singleton manager
        s1 = create_session(name="test-conv")
        assert s1["name"] == "test-conv"
        s2 = get_session(s1["session_id"])
        assert s2 is not None
        sessions = list_sessions()
        assert len(sessions) >= 1
