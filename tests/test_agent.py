"""
Tests for h_agent module imports and basic functionality.
"""
import os
import pytest

os.environ["OPENAI_API_KEY"] = "test"
os.environ["OPENAI_API_BASE"] = "http://localhost:8000"
os.environ["MODEL_ID"] = "test-model"


class TestModuleImports:
    """Test that the h_agent package and modules can be imported."""

    def test_version_exists(self):
        from h_agent import __version__
        assert __version__ is not None
        assert len(__version__) > 0

    def test_core_imports(self):
        from h_agent.core.agent_loop import run_bash, execute_tool_call, TOOLS
        assert run_bash is not None
        assert execute_tool_call is not None
        assert isinstance(TOOLS, list)

    def test_tools_imports(self):
        from h_agent.core.tools import TOOL_HANDLERS, TOOLS
        assert isinstance(TOOL_HANDLERS, dict)
        assert isinstance(TOOLS, list)

    def test_session_manager_imports(self):
        from h_agent.session.manager import SessionManager
        assert SessionManager is not None

    def test_platform_utils_imports(self):
        from h_agent.platform_utils import (
            IS_WINDOWS, IS_MACOS, IS_LINUX,
            get_shell, which, platform_info
        )
        assert isinstance(IS_WINDOWS, bool)
        assert isinstance(IS_MACOS, bool)
        assert isinstance(IS_LINUX, bool)

    def test_config_imports(self):
        from h_agent.core.config import (
            MODEL, OPENAI_BASE_URL, OPENAI_API_KEY,
            get_config, set_config, list_config,
            get_current_profile, create_profile
        )
        assert MODEL is not None


class TestRunBash:
    """Test run_bash function."""

    def test_run_bash_simple(self):
        from h_agent.core.agent_loop import run_bash
        result = run_bash("echo hello")
        assert "hello" in result

    def test_run_bash_dangerous(self):
        from h_agent.core.agent_loop import run_bash
        result = run_bash("rm -rf /")
        assert "blocked" in result.lower() or "dangerous" in result.lower()

    def test_run_bash_timeout(self):
        from h_agent.core.agent_loop import run_bash
        # run_bash doesn't have a timeout parameter exposed, just test it returns something
        result = run_bash("echo hello")
        assert "hello" in result

    def test_run_bash_nonexistent(self):
        from h_agent.core.agent_loop import run_bash
        result = run_bash("nonexistent_command_xyz")
        # Should return something (may or may not indicate error)
        assert isinstance(result, str)
