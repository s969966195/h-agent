#!/usr/bin/env python3
"""
h_agent/tests/test_async_team.py - TDD tests for s09 Async Agent Teams

Tests cover:
1. AsyncMessageBus: send(), read_inbox(), broadcast(), drain behavior
2. TeammateManager: spawn(), shutdown(), list_members(), get_status()
3. _teammate_loop: inbox polling, send_message tool, idle state
4. Lead integration: talk_to_async()

Run with: pytest h_agent/tests/test_async_team.py -v
"""

import json
import os
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def temp_inbox_dir(tmp_path):
    """Temporary inbox directory for tests."""
    inbox_dir = tmp_path / "inboxes"
    inbox_dir.mkdir()
    return inbox_dir


@pytest.fixture
def async_bus(temp_inbox_dir):
    """AsyncMessageBus instance with temp directory."""
    from h_agent.team.async_team import AsyncMessageBus
    return AsyncMessageBus(inbox_dir=temp_inbox_dir)


# ============================================================
# Phase 2: AsyncMessageBus Tests
# ============================================================

class TestAsyncMessageBus:
    """Tests for AsyncMessageBus JSONL inbox operations."""
    
    def test_send_and_read_inbox(self, async_bus):
        """Roundtrip: send message, read_inbox returns it."""
        async_bus.send("alice", "bob", "hello world")
        inbox = async_bus.read_inbox("bob")
        
        assert len(inbox) == 1
        assert inbox[0]["content"] == "hello world"
        assert inbox[0]["from"] == "alice"
        assert inbox[0]["type"] == "message"
    
    def test_read_inbox_drains(self, async_bus):
        """read_inbox clears inbox after read (drain-on-read pattern)."""
        async_bus.send("alice", "bob", "hello")
        async_bus.read_inbox("bob")
        
        # Second read should return empty
        assert async_bus.read_inbox("bob") == []
    
    def test_broadcast_to_all(self, async_bus):
        """broadcast() sends message to all teammates except sender."""
        async_bus.broadcast("lead", ["alice", "bob", "charlie"], "announcement")
        
        alice_inbox = async_bus.read_inbox("alice")
        bob_inbox = async_bus.read_inbox("bob")
        charlie_inbox = async_bus.read_inbox("charlie")
        
        assert len(alice_inbox) == 1
        assert alice_inbox[0]["content"] == "announcement"
        assert len(bob_inbox) == 1
        assert len(charlie_inbox) == 1
        
        # Lead should NOT receive
        lead_inbox = async_bus.read_inbox("lead")
        assert lead_inbox == []
    
    def test_multiple_messages(self, async_bus):
        """Multiple messages to same recipient are queued."""
        async_bus.send("alice", "bob", "msg1")
        async_bus.send("charlie", "bob", "msg2")
        async_bus.send("lead", "bob", "msg3")
        
        inbox = async_bus.read_inbox("bob")
        assert len(inbox) == 3
    
    def test_message_with_extra_fields(self, async_bus):
        """send() accepts extra fields like msg_type, timestamp."""
        async_bus.send(
            "alice", "bob", "task assignment",
            msg_type="task",
            task_id="task-123"
        )
        
        inbox = async_bus.read_inbox("bob")
        assert len(inbox) == 1
        assert inbox[0]["type"] == "task"
        assert inbox[0]["task_id"] == "task-123"
    
    def test_concurrent_read_write(self, async_bus):
        """Concurrent send and read are thread-safe."""
        errors = []
        
        def sender():
            for i in range(100):
                try:
                    async_bus.send("alice", "bob", f"msg-{i}")
                except Exception as e:
                    errors.append(e)
        
        def reader():
            for _ in range(100):
                try:
                    async_bus.read_inbox("bob")
                except Exception as e:
                    errors.append(e)
        
        t1 = threading.Thread(target=sender)
        t2 = threading.Thread(target=reader)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"


# ============================================================
# Phase 3: TeammateManager Tests
# ============================================================

class TestTeammateManager:
    """Tests for TeammateManager thread management."""
    
    def test_spawn_creates_thread(self):
        """spawn() creates a running daemon thread."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        mock_handler = MagicMock()
        
        result = manager.spawn("alice", "coder", "You are a coder", mock_handler)
        
        assert "Spawned" in result
        assert manager.get_status("alice") == "working"
        
        manager.shutdown("alice")
    
    def test_spawn_updates_status(self):
        """spawn() updates internal status tracking."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        mock_handler = MagicMock()
        
        manager.spawn("alice", "coder", "You are a coder", mock_handler)
        
        assert manager.get_status("alice") == "working"
        
        manager.shutdown("alice")
    
    def test_shutdown_transitions_state(self):
        """shutdown() transitions member to shutdown state."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        mock_handler = MagicMock()
        
        manager.spawn("alice", "coder", "You are a coder", mock_handler)
        assert manager.get_status("alice") == "working"
        
        manager.shutdown("alice")
        # After shutdown, thread should eventually stop
        time.sleep(0.5)
        assert manager.get_status("alice") == "shutdown"
    
    def test_list_members(self):
        """list_members() returns team roster with statuses."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        mock_handler = MagicMock()
        
        manager.spawn("alice", "coder", "You are a coder", mock_handler)
        manager.spawn("bob", "reviewer", "You are a reviewer", mock_handler)
        
        members = manager.list_members()
        assert len(members) == 2
        names = {m["name"] for m in members}
        assert "alice" in names
        assert "bob" in names
        
        manager.shutdown("alice")
        manager.shutdown("bob")
    
    def test_get_status_unknown_member(self):
        """get_status() returns None for non-existent member."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        assert manager.get_status("nonexistent") is None
    
    def test_multiple_teammates_concurrent(self):
        """Multiple teammates can run concurrently."""
        from h_agent.team.async_team import TeammateManager
        
        manager = TeammateManager()
        mock_handler = MagicMock()
        
        manager.spawn("alice", "coder", "You are alice", mock_handler)
        manager.spawn("bob", "reviewer", "You are bob", mock_handler)
        manager.spawn("charlie", "devops", "You are charlie", mock_handler)
        
        assert manager.get_status("alice") == "working"
        assert manager.get_status("bob") == "working"
        assert manager.get_status("charlie") == "working"
        
        manager.shutdown("alice")
        manager.shutdown("bob")
        manager.shutdown("charlie")


# ============================================================
# Phase 4: _teammate_loop Tests
# ============================================================

class TestTeammateLoop:
    """Tests for _teammate_loop inbox polling and state transitions."""
    
    def test_receives_inbox_messages(self):
        """Messages in inbox become LLM inputs."""
        from h_agent.team.async_team import _teammate_loop, AsyncMessageBus, TeammateManager
        
        # This test would need a real handler with LLM calls
        # Placeholder for TDD - implementation follows
        pass
    
    def test_send_message_tool_writes_to_inbox(self):
        """send_message tool writes to recipient inbox."""
        from h_agent.team.async_team import AsyncMessageBus
        
        bus = AsyncMessageBus()
        bus.send("alice", "bob", "hello via tool")
        
        inbox = bus.read_inbox("bob")
        assert len(inbox) == 1
        assert inbox[0]["content"] == "hello via tool"
    
    def test_idle_polling(self):
        """No work → idle state → polls inbox every 5s."""
        # This test would verify idle cycle behavior
        pass
    
    def test_shutdown_stops_loop(self):
        """shutdown signal stops _teammate_loop."""
        pass


# ============================================================
# Phase 5: Lead Integration Tests
# ============================================================

class TestLeadIntegration:
    """Tests for lead agent using send_message tool."""
    
    def test_talk_to_async(self):
        """AgentTeam.talk_to_async() sends message and returns response."""
        from h_agent.team.async_team import AsyncMessageBus
        
        bus = AsyncMessageBus()
        # talk_to_async would use bus.send() and wait for response
        pass
    
    def test_broadcast_to_all(self, async_bus):
        """Lead can broadcast to all teammates."""
        async_bus.broadcast("lead", ["alice", "bob"], "start working")
        
        assert len(async_bus.read_inbox("alice")) == 1
        assert len(async_bus.read_inbox("bob")) == 1
        assert len(async_bus.read_inbox("lead")) == 0
    
    def test_delegate_task(self):
        """Lead can delegate task to specific teammate."""
        pass


# ============================================================
# Integration Tests
# ============================================================

class TestAsyncTeamIntegration:
    """End-to-end integration tests."""
    
    def test_full_message_flow(self):
        """Lead → Teammate → Lead full message exchange."""
        from h_agent.team.async_team import AsyncMessageBus, TeammateManager
        
        bus = AsyncMessageBus()
        manager = TeammateManager()
        
        # Spawn teammate
        # Send task
        # Verify response
        pass
    
    def test_parallel_teammates(self):
        """Multiple teammates process tasks in parallel."""
        pass


# ============================================================
# Message Format Tests
# ============================================================

class TestMessageFormat:
    """Tests for JSONL message format validation."""
    
    def test_valid_jsonl_format(self, async_bus):
        """Messages are stored as valid JSONL."""
        async_bus.send("alice", "bob", "test")
        
        inbox_file = async_bus.inbox_dir / "bob.jsonl"
        content = inbox_file.read_text()
        
        # Should be one JSON object per line
        lines = content.strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["content"] == "test"
    
    def test_required_fields(self, async_bus):
        """Messages have required fields: type, from, content, timestamp."""
        async_bus.send("alice", "bob", "test")
        
        inbox = async_bus.read_inbox("bob")
        msg = inbox[0]
        
        assert "type" in msg
        assert "from" in msg
        assert "content" in msg
        assert "timestamp" in msg


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Tests for edge cases and error conditions."""
    
    def test_empty_inbox(self, async_bus):
        """read_inbox on empty inbox returns []."""
        assert async_bus.read_inbox("nonexistent") == []
    
    def test_send_to_nonexistent_receiver(self, async_bus):
        """send() to nonexistent receiver creates inbox file."""
        async_bus.send("alice", "newcomer", "welcome")
        
        inbox = async_bus.read_inbox("newcomer")
        assert len(inbox) == 1
        assert inbox[0]["content"] == "welcome"
    
    def test_broadcast_empty_list(self, async_bus):
        """broadcast() with empty list does nothing."""
        result = async_bus.broadcast("lead", [], "nothing")
        # Should not raise
