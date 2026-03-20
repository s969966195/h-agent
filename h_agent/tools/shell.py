#!/usr/bin/env python3
"""
h_agent/tools/shell.py - Shell command execution tools

Tools:
- shell_run: Execute a shell command with safety checks
- shell_env: Show environment variables
- shell_cd: Change working directory (for the agent session)
- shell_which: Find executable path

Cross-platform: supports bash/zsh (Unix) and PowerShell/CMD (Windows).
"""

import os
import subprocess
import json
import shutil
from typing import Callable, Dict, List, Any

from h_agent.platform_utils import IS_WINDOWS, get_shell, which, which_all

# Track current working directory for the agent session
_CURRENT_CWD = os.getcwd()

# ============================================================
# Tool Definitions
# ============================================================

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shell_run",
            "description": "Execute a shell command. Use for file operations, git, docker, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command (defaults to current)",
                        "default": ""
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 120
                    },
                    "shell": {
                        "type": "boolean",
                        "description": "Execute through shell",
                        "default": True
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_env",
            "description": "Show environment variables. Optionally filter by prefix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Filter variables by prefix (e.g., 'PATH', 'HOME')", "default": ""},
                    "json": {"type": "boolean", "description": "Output as JSON", "default": False}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_cd",
            "description": "Change the agent's working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to change to"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_which",
            "description": "Find the full path of an executable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command name to find"},
                    "all": {"type": "boolean", "description": "Show all matches (PATH may contain duplicates)", "default": False}
                },
                "required": ["command"]
            }
        }
    }
]


# ============================================================
# Tool Handlers
# ============================================================

# Dangerous commands that are blocked
_DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "sudo rm -rf",
    "mkfs",
    "dd if=/dev/zero of=/dev/sda",
    "> /dev/sd",
    ":(){:|:&};:",  # Fork bomb
    "chmod -R 777 /",
]

# Commands requiring confirmation (not blocked, but warned)
_SUSPICIOUS_PATTERNS = [
    "sudo su",
    "passwd root",
    "chmod 777",
    "chmod -R 777",
]


def tool_shell_run(
    command: str,
    cwd: str = "",
    timeout: int = 120,
    shell: bool = True
) -> str:
    """Execute a shell command with safety checks."""
    global _CURRENT_CWD
    
    # Check for dangerous commands (normalize for cross-platform check)
    lower_cmd = command.lower()
    for dangerous in _DANGEROUS_PATTERNS:
        if dangerous in lower_cmd:
            return f"Error: Dangerous command blocked: {command[:50]}..."
    
    # Windows-specific dangerous patterns
    if IS_WINDOWS:
        windows_dangerous = [
            "rm -rf",  # Not valid on Windows CMD but still check
            "del /f /s /q c:",
            "format",
            "rmdir /s /q",
            "icacls . /grant everyone",
        ]
        for dangerous in windows_dangerous:
            if dangerous in command.lower():
                return f"Error: Dangerous command blocked: {command[:50]}..."
    
    # Check for suspicious commands
    warnings = []
    for suspicious in _SUSPICIOUS_PATTERNS:
        if suspicious in lower_cmd:
            warnings.append(f"Warning: Potentially dangerous pattern '{suspicious}' detected")
    
    # Use specified cwd or current session cwd
    work_dir = cwd if cwd else _CURRENT_CWD
    
    # Resolve relative paths
    if work_dir and not os.path.isabs(work_dir):
        work_dir = os.path.join(_CURRENT_CWD, work_dir)
    
    try:
        # On Windows, use shell=True to go through cmd.exe by default
        # On Unix, also use shell=True for consistency
        result = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ}  # Pass current env
        )
        
        output_parts = []
        if warnings:
            output_parts.extend(warnings)
            output_parts.append("")
        
        if result.stdout:
            output_parts.append(result.stdout.strip())
        if result.stderr:
            output_parts.append(f"[stderr] {result.stderr.strip()}")
        
        if result.returncode != 0 and not result.stdout and not result.stderr:
            output_parts.append(f"(exit code: {result.returncode})")
        
        output = "\n".join(output_parts)
        return output[:80000] if output else "(no output)"
    
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def tool_shell_env(filter: str = "", json: bool = False) -> str:
    """Show environment variables."""
    env = os.environ
    
    if filter:
        filtered = {k: v for k, v in env.items() if k.startswith(filter.upper())}
        env = filtered
    
    if json:
        # Mask sensitive values
        safe_env = {}
        for k, v in env.items():
            if any(s in k.upper() for s in ["KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH"]):
                safe_env[k] = "***"
            else:
                safe_env[k] = v
        return json.dumps(safe_env, indent=2)
    
    lines = [f"{k}={v}" for k, v in sorted(env.items())]
    return "\n".join(lines)


def tool_shell_cd(path: str) -> str:
    """Change the agent's working directory."""
    global _CURRENT_CWD
    
    # Resolve path
    if not os.path.isabs(path):
        path = os.path.join(_CURRENT_CWD, path)
    
    path = os.path.normpath(path)
    
    if not os.path.exists(path):
        return f"Error: Directory does not exist: {path}"
    
    if not os.path.isdir(path):
        return f"Error: Not a directory: {path}"
    
    if not os.access(path, os.R_OK):
        return f"Error: Directory not readable: {path}"
    
    _CURRENT_CWD = path
    return f"Changed directory to: {path}"


def tool_shell_which(command: str, all: bool = False) -> str:
    """Find executable path (cross-platform)."""
    try:
        if all:
            paths = which_all(command)
            if not paths:
                return f"Command not found: {command}"
            # Deduplicate while preserving order
            seen = set()
            unique_paths = []
            for p in paths:
                if p not in seen:
                    seen.add(p)
                    unique_paths.append(p)
            return "\n".join(unique_paths)
        else:
            path = which(command)
            if not path:
                return f"Command not found: {command}"
            return path
    except Exception as e:
        return f"Error: {e}"


# ============================================================
# Handler Dispatch Map
# ============================================================

TOOL_HANDLERS: Dict[str, Callable] = {
    "shell_run": tool_shell_run,
    "shell_env": tool_shell_env,
    "shell_cd": tool_shell_cd,
    "shell_which": tool_shell_which,
}
