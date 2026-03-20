#!/usr/bin/env python3
"""
h_agent/platform_utils.py - Cross-platform compatibility utilities

Detects OS and provides platform-specific utilities for:
- Process management (start/stop daemons)
- Shell commands
- Path handling
- Executable discovery
"""

import sys
import os
import signal
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple

# ============================================================
# Platform Detection
# ============================================================

PLATFORM = sys.platform
"""One of: 'darwin', 'linux', 'windows', 'cygwin', 'freebsd'."""

IS_WINDOWS = PLATFORM in ("win32", "cygwin", "msys")
"""True if running on Windows (including MSYS2/Cygwin)."""

IS_MACOS = PLATFORM == "darwin"
"""True if running on macOS."""

IS_LINUX = PLATFORM == "linux"
"""True if running on Linux."""

IS_UNIX = PLATFORM in ("darwin", "linux", "freebsd", "cygwin", "msys")
"""True if running on a Unix-like system (including macOS, Linux, BSD, MSYS2)."""


# ============================================================
# Shell Detection
# ============================================================

def get_shell() -> str:
    """Get the default shell for running commands.
    
    Returns:
        'powershell', 'cmd', or 'bash' depending on platform.
    """
    if IS_WINDOWS:
        # Check if PowerShell is available
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh:
            return "powershell"
        return "cmd"
    return "bash"


def shell_quote(s: str) -> str:
    """Quote a string for shell safety (Windows-aware)."""
    if IS_WINDOWS:
        # Double up existing quotes and wrap in quotes
        return '"' + s.replace('"', '""') + '"'
    # Unix: single-quote for safety
    return "'" + s.replace("'", "'\\''") + "'"


# ============================================================
# Executable Discovery
# ============================================================

def which(cmd: str) -> Optional[str]:
    """Find the full path of an executable (cross-platform).
    
    Uses shutil.which() which works on all platforms.
    
    Args:
        cmd: Command name to find
        
    Returns:
        Full path to executable, or None if not found.
    """
    return shutil.which(cmd)


def which_all(cmd: str) -> list:
    """Find all occurrences of a command in PATH.
    
    On Windows, PATH may contain duplicates; this returns them all.
    """
    result = []
    for p in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(p, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            result.append(full)
    return result


# ============================================================
# Process Management
# ============================================================

def daemon_pid_file() -> Path:
    """Get the daemon PID file path (platform-aware)."""
    if IS_WINDOWS:
        # On Windows, use APPDATA
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        base = Path(appdata) / "h-agent"
    else:
        base = Path.home() / ".h-agent"
    base.mkdir(parents=True, exist_ok=True)
    return base / "daemon.pid"


def start_daemon_subprocess(script_path: str, port: int) -> Optional[int]:
    """Start daemon as detached subprocess.
    
    Args:
        script_path: Path to the daemon server script
        port: Port to run on
        
    Returns:
        PID of the started process, or None on failure.
    """
    env = os.environ.copy()
    env["H_AGENT_PORT"] = str(port)
    
    if IS_WINDOWS:
        # Windows: use start command via cmd /c to detach
        try:
            cmd = [
                sys.executable,
                "-m", "h_agent.daemon.server"
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=env
            )
            return proc.pid
        except Exception:
            return None
    else:
        # Unix: use start_new_session to detach
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "h_agent.daemon.server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env
            )
            return proc.pid
        except Exception:
            return None


def stop_process(pid: int, timeout: float = 2.0) -> bool:
    """Stop a process gracefully.
    
    Args:
        pid: Process ID
        timeout: Seconds to wait before SIGKILL
        
    Returns:
        True if process was stopped, False otherwise.
    """
    try:
        if IS_WINDOWS:
            # Windows: use taskkill
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=timeout + 2
            )
            return True
        else:
            # Unix: try SIGTERM first, then SIGKILL
            try:
                os.kill(pid, signal.SIGTERM)
            except PermissionError:
                # May need sudo - process exists but can't kill
                return False
            except ProcessLookupError:
                return True  # Already dead
            
            # Wait for graceful shutdown
            import time
            start = time.time()
            while time.time() - start < timeout:
                try:
                    os.kill(pid, 0)  # Check if still alive
                    time.sleep(0.1)
                except ProcessLookupError:
                    return True
            
            # Force kill
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            
            return True
    except Exception:
        return False


def is_process_alive(pid: int) -> bool:
    """Check if a process is running.
    
    Args:
        pid: Process ID
        
    Returns:
        True if process exists and is running.
    """
    if pid <= 0:
        return False
    try:
        if IS_WINDOWS:
            # On Windows, os.kill doesn't work for checking existence
            # Use tasklist instead
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False


# ============================================================
# Path Utilities
# ============================================================

def get_config_dir() -> Path:
    """Get the config directory (platform-aware).
    
    - Linux/macOS: ~/.h-agent
    - Windows: %APPDATA%/h-agent
    """
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "h-agent"
    return Path.home() / ".h-agent"


def get_workspace_default() -> Path:
    """Get the default workspace directory (platform-aware).
    
    - Linux/macOS: {project}/.agent_workspace
    - Windows: {project}/.agent_workspace
    """
    # Use current working directory's .agent_workspace
    return Path.cwd() / ".agent_workspace"


def normalize_path(path: str) -> str:
    """Normalize a path for the current platform.
    
    Converts forward slashes to backslashes on Windows.
    """
    if IS_WINDOWS:
        return path.replace("/", "\\")
    return path


def expand_env_vars(path: str) -> str:
    """Expand environment variables in a path string.
    
    Works on both Unix (%VAR%) and Unix ($VAR) style.
    """
    if IS_WINDOWS:
        import os.path
        # Expand %VAR% style
        path = os.path.expandvars(path)
    # Expand $VAR and ${VAR} style
    return os.path.expanduser(os.path.expandvars(path))


# ============================================================
# Git Compatibility
# ============================================================

def git_command() -> str:
    """Get the git command (platform-aware).
    
    On Windows, prefer 'git.exe' via shutil.which.
    """
    git = which("git")
    if git:
        return git
    return "git"  # Fallback


# ============================================================
# Platform Info
# ============================================================

def platform_info() -> dict:
    """Get platform information dictionary."""
    return {
        "platform": PLATFORM,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "is_linux": IS_LINUX,
        "is_unix": IS_UNIX,
        "shell": get_shell(),
        "config_dir": str(get_config_dir()),
        "python": sys.executable,
    }


# ============================================================
# Module init
# ============================================================

if __name__ == "__main__":
    import json
    print(json.dumps(platform_info(), indent=2))
