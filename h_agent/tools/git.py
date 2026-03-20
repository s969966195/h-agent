#!/usr/bin/env python3
"""
h_agent/tools/git.py - Git operation tools

Tools:
- git_status: Show working tree status
- git_commit: Commit changes with message
- git_push: Push to remote
- git_pull: Pull from remote
- git_log: Show commit log
- git_branch: List/create/delete branches

Cross-platform: works with git on Windows (via CMD/PowerShell).
"""

import subprocess
import shutil
from typing import Callable, Dict, List, Any

from h_agent.platform_utils import IS_WINDOWS

# ============================================================
# Tool Definitions (OpenAI function calling format)
# ============================================================

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show the working tree status of a git repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository path (defaults to current directory)",
                        "default": "."
                    },
                    "short": {
                        "type": "boolean",
                        "description": "Use short format",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Commit staged changes with a message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "path": {"type": "string", "description": "Repository path", "default": "."},
                    "allow_empty": {"type": "boolean", "description": "Allow empty commit", "default": False}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push commits to remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name", "default": "origin"},
                    "branch": {"type": "string", "description": "Branch name", "default": ""},
                    "path": {"type": "string", "description": "Repository path", "default": "."},
                    "force": {"type": "boolean", "description": "Force push", "default": False}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_pull",
            "description": "Pull changes from remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name", "default": "origin"},
                    "branch": {"type": "string", "description": "Branch name", "default": ""},
                    "path": {"type": "string", "description": "Repository path", "default": "."},
                    "rebase": {"type": "boolean", "description": "Use rebase instead of merge", "default": False}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show commit logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository path", "default": "."},
                    "n": {"type": "integer", "description": "Number of commits to show", "default": 10},
                    "oneline": {"type": "boolean", "description": "One line per commit", "default": True},
                    "stat": {"type": "boolean", "description": "Show file change statistics", "default": False}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "List, create, or delete branches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list", "create", "delete", "rename", "current"],
                        "description": "Branch operation",
                        "default": "list"
                    },
                    "name": {"type": "string", "description": "Branch name (for create/delete/rename)"},
                    "source": {"type": "string", "description": "Source branch (for create/rename)"},
                    "path": {"type": "string", "description": "Repository path", "default": "."}
                }
            }
        }
    }
]


# ============================================================
# Tool Handlers
# ============================================================

def _run_git(args: List[str], cwd: str = ".") -> str:
    """Run a git command and return output (cross-platform)."""
    # Check git is available
    git_path = shutil.which("git")
    if not git_path:
        return "Error: git not found. Is Git installed?"
    
    try:
        # Use shell=True on Windows for better compatibility
        # Also on Unix for consistency with git's own shell integration
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=IS_WINDOWS
        )
        output = result.stdout + result.stderr
        if not output:
            return "(no output)"
        return output.strip()
    except subprocess.TimeoutExpired:
        return "Error: Git command timed out (60s)"
    except FileNotFoundError:
        return "Error: git not found. Is Git installed?"
    except Exception as e:
        return f"Error: {e}"


def tool_git_status(path: str = ".", short: bool = False) -> str:
    """Show git status."""
    args = ["status"]
    if short:
        args.append("--short")
    return _run_git(args, cwd=path)


def tool_git_commit(message: str, path: str = ".", allow_empty: bool = False) -> str:
    """Commit staged changes."""
    args = ["commit", "-m", message]
    if allow_empty:
        args.append("--allow-empty")
    return _run_git(args, cwd=path)


def tool_git_push(
    remote: str = "origin",
    branch: str = "",
    path: str = ".",
    force: bool = False
) -> str:
    """Push to remote."""
    args = ["push"]
    if force:
        args.append("--force")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git(args, cwd=path)


def tool_git_pull(
    remote: str = "origin",
    branch: str = "",
    path: str = ".",
    rebase: bool = False
) -> str:
    """Pull from remote."""
    args = ["pull"]
    if rebase:
        args.append("--rebase")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git(args, cwd=path)


def tool_git_log(
    path: str = ".",
    n: int = 10,
    oneline: bool = True,
    stat: bool = False
) -> str:
    """Show commit log."""
    args = ["log", f"-{n}"]
    if oneline:
        args.append("--oneline")
    if stat:
        args.append("--stat")
    return _run_git(args, cwd=path)


def tool_git_branch(
    operation: str = "list",
    name: str = "",
    source: str = "",
    path: str = "."
) -> str:
    """Manage branches."""
    args = ["branch"]
    
    if operation == "list":
        args.append("-a")
        return _run_git(args, cwd=path)
    
    elif operation == "current":
        return _run_git(["branch", "--show-current"], cwd=path)
    
    elif operation == "create":
        if not name:
            return "Error: branch name required for create operation"
        args.append(name)
        if source:
            args.append(source)
        return _run_git(args, cwd=path)
    
    elif operation == "delete":
        if not name:
            return "Error: branch name required for delete operation"
        args.extend(["-d", name])
        return _run_git(args, cwd=path)
    
    elif operation == "rename":
        if not name or not source:
            return "Error: both source and name required for rename operation"
        args.extend([source, name])
        return _run_git(args, cwd=path)
    
    else:
        return f"Error: Unknown operation '{operation}'"


# ============================================================
# Handler Dispatch Map
# ============================================================

TOOL_HANDLERS: Dict[str, Callable] = {
    "git_status": tool_git_status,
    "git_commit": tool_git_commit,
    "git_push": tool_git_push,
    "git_pull": tool_git_pull,
    "git_log": tool_git_log,
    "git_branch": tool_git_branch,
}
