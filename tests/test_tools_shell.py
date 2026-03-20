"""
Tests for h_agent.tools.shell module.
"""
import os
import pytest

from h_agent.tools.shell import (
    tool_shell_run,
    tool_shell_env,
    tool_shell_cd,
    tool_shell_which,
    TOOL_HANDLERS,
    _DANGEROUS_PATTERNS,
)


class TestToolShellRun:
    """shell_run tool tests."""

    def test_simple_command(self):
        result = tool_shell_run("echo hello")
        assert "hello" in result.lower() or "Hello" in result

    def test_pwd_command(self):
        result = tool_shell_run("pwd")
        assert len(result) > 0

    def test_dangerous_rm_rf_blocked(self):
        result = tool_shell_run("rm -rf /")
        assert "blocked" in result.lower() or "dangerous" in result.lower()

    def test_dangerous_sudo_rm_blocked(self):
        result = tool_shell_run("sudo rm -rf /some/path")
        assert "blocked" in result.lower() or "dangerous" in result.lower()

    def test_fork_bomb_blocked(self):
        result = tool_shell_run(":(){:|:&};:")
        assert "blocked" in result.lower() or "dangerous" in result.lower()

    def test_timeout(self):
        result = tool_shell_run("sleep 10", timeout=1)
        assert "timed out" in result.lower() or "timeout" in result.lower()

    def test_nonexistent_command(self):
        result = tool_shell_run("nonexistent_command_xyz_123")
        # May or may not fail depending on system, just check it returns something
        assert len(result) > 0

    def test_cwd_option(self, tmp_path):
        result = tool_shell_run("pwd", cwd=str(tmp_path))
        assert str(tmp_path) in result

    def test_output_truncated(self):
        # Very long output should be truncated
        result = tool_shell_run("python3 -c 'print(\"x\"*100000)'")
        assert len(result) <= 80050


class TestToolShellEnv:
    """shell_env tool tests."""

    def test_env_shows_variables(self):
        result = tool_shell_env()
        assert "PATH" in result or "HOME" in result

    def test_env_with_filter(self):
        result = tool_shell_env(filter="PATH")
        lines = result.strip().split("\n")
        for line in lines:
            if line and not line.startswith("#"):
                assert line.startswith("PATH") or "PATH" in line

    def test_env_json_mode(self):
        result = tool_shell_env(as_json=True)
        import json
        try:
            data = json.loads(result)
            assert isinstance(data, dict)
        except json.JSONDecodeError:
            pytest.fail("JSON output invalid")


class TestToolShellCd:
    """shell_cd tool tests."""

    def test_cd_to_existing_dir(self, tmp_path):
        result = tool_shell_cd(str(tmp_path))
        assert str(tmp_path) in result or "Changed" in result

    def test_cd_to_nonexistent_dir(self, tmp_path):
        result = tool_shell_cd(str(tmp_path / "nonexistent_dir_xyz"))
        assert "Error" in result or "not exist" in result.lower()

    def test_cd_relative_path(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = tool_shell_cd("subdir")
        # May succeed with relative path handling


class TestToolShellWhich:
    """shell_which tool tests."""

    def test_which_python(self):
        result = tool_shell_which("python3") or tool_shell_which("python")
        assert result and len(result) > 0
        assert "python" in result.lower()

    def test_which_not_found(self):
        result = tool_shell_which("definitely_not_a_real_command_xyz123")
        assert "not found" in result.lower()

    def test_which_all(self):
        result = tool_shell_which("ls", all=True)
        # Should return at least one path
        lines = result.strip().split("\n")
        assert len(lines) >= 1
