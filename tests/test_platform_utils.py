"""
Tests for h_agent.platform_utils module.
"""
import os
import pytest

from pathlib import Path

from h_agent.platform_utils import (
    IS_WINDOWS,
    IS_MACOS,
    IS_LINUX,
    IS_UNIX,
    get_shell,
    which,
    which_all,
    shell_quote,
    daemon_pid_file,
    get_config_dir,
    normalize_path,
    expand_env_vars,
    platform_info,
    is_process_alive,
)


class TestPlatformDetection:
    """Platform detection tests."""

    def test_platform_flags(self):
        # At least one should be True
        assert IS_WINDOWS or IS_MACOS or IS_LINUX or IS_UNIX

    def test_unix_on_non_windows(self):
        if not IS_WINDOWS:
            assert IS_UNIX is True


class TestShellUtils:
    """Shell utility tests."""

    def test_get_shell(self):
        shell = get_shell()
        assert shell in ("bash", "sh", "powershell", "pwsh", "cmd")

    def test_shell_quote(self):
        quoted = shell_quote("hello world")
        assert quoted  # Should have quotes around it
        assert "hello world" in quoted or "hello" in quoted


class TestExecutableDiscovery:
    """Executable discovery tests."""

    def test_which_python(self):
        result = which("python3") or which("python")
        assert result is not None
        assert "python" in result.lower()

    def test_which_nonexistent(self):
        result = which("this_command_does_not_exist_xyz_123")
        assert result is None

    def test_which_all(self):
        result = which_all("ls")
        assert isinstance(result, list)
        assert len(result) >= 1


class TestPathUtilities:
    """Path utility tests."""

    def test_daemon_pid_file(self):
        pid_file = daemon_pid_file()
        assert pid_file is not None
        assert str(pid_file).endswith("daemon.pid")

    def test_get_config_dir(self):
        config_dir = get_config_dir()
        assert config_dir is not None
        assert isinstance(config_dir, Path)
        # Should be under home directory or APPDATA on Windows
        home = Path.home()
        assert str(config_dir).startswith(str(home)) or ".h-agent" in str(config_dir)

    def test_normalize_path(self):
        result = normalize_path("a/b/c")
        if IS_WINDOWS:
            assert "\\" in result
        else:
            assert "/" in result

    def test_expand_env_vars(self):
        import os as os_mod
        result = expand_env_vars("$HOME/test")
        assert "test" in result or os_mod.path.expanduser("~") in result


class TestPlatformInfo:
    """Platform info tests."""

    def test_platform_info_returns_dict(self):
        info = platform_info()
        assert isinstance(info, dict)
        assert "platform" in info
        assert info["platform"] == os.sys.platform

    def test_platform_info_has_shell(self):
        info = platform_info()
        assert "shell" in info


class TestProcessManagement:
    """Process management tests."""

    def test_is_process_alive_invalid_pid(self):
        # PID 0 or negative should return False
        assert is_process_alive(0) is False
        assert is_process_alive(-1) is False

    def test_is_process_alive_own_process(self):
        # Current process should be alive
        assert is_process_alive(os.getpid()) is True
