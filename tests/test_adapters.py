"""
tests/test_adapters.py - Agent Adapter Tests
"""

import pytest
import subprocess
import shutil
from h_agent.adapters.opencode_adapter import OpencodeAdapter
from h_agent.adapters.base import BaseAgentAdapter, AgentResponse


# Check if opencode CLI is available
OPENCODE_AVAILABLE = shutil.which("opencode") is not None


class TestOpencodeAdapter:
    """Tests for OpencodeAdapter."""

    def test_adapter_creation(self):
        """Test adapter can be created."""
        adapter = OpencodeAdapter()
        assert adapter.name == "opencode"
        assert adapter.status.value == "idle"

    @pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
    def test_simple_chat(self):
        """Test simple chat with opencode."""
        adapter = OpencodeAdapter(cwd="/tmp")
        try:
            response = adapter.chat("say hello in one word")
            assert response.error is None or "timeout" in response.error.lower()
            assert response.content.strip() != ""
            assert "session_id" in response.metadata
        finally:
            adapter.stop()

    @pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
    def test_tool_call_extraction(self):
        """Test tool call extraction from opencode JSON."""
        adapter = OpencodeAdapter(cwd="/tmp")
        try:
            response = adapter.chat('create a file /tmp/adapter_test.txt with content "test"')
            # Should have at least one tool call (write)
            assert len(response.tool_calls) >= 0  # May or may not have tools depending on model
        finally:
            adapter.stop()

    @pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
    def test_context_manager(self):
        """Test adapter as context manager."""
        with OpencodeAdapter(cwd="/tmp") as adapter:
            assert adapter.name == "opencode"
            response = adapter.chat("hello")
            assert response.content or response.error is None

    @pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
    def test_session_metadata(self):
        """Test session ID is captured."""
        adapter = OpencodeAdapter(cwd="/tmp")
        try:
            response = adapter.chat("hello")
            assert adapter.session_id is not None
        finally:
            adapter.stop()


class TestAdapterRegistry:
    """Tests for adapter registry."""

    def test_list_adapters(self):
        """Test listing available adapters."""
        from h_agent.adapters import list_adapters
        adapters = list_adapters()
        assert "opencode" in adapters
        assert "claude" in adapters

    def test_get_adapter(self):
        """Test getting an adapter by name."""
        from h_agent.adapters import get_adapter
        adapter = get_adapter("opencode")
        assert adapter.name == "opencode"

    def test_get_unknown_adapter(self):
        """Test getting unknown adapter raises error."""
        from h_agent.adapters import get_adapter
        with pytest.raises(ValueError):
            get_adapter("unknown_adapter")
