#!/usr/bin/env python3
"""
h_agent/core/tools.py - Multiple Tools with Dispatch Map

Adding a tool means adding one handler.
The loop stays the same; tools register into a dispatch map.

Tools implemented:
- bash: Execute shell commands
- read: Read file contents
- write: Write content to file
- edit: Make precise edits to files
- glob: Find files by pattern
"""

import os
import sys
import json
import glob as glob_module
import subprocess
import threading
import time
from typing import Callable, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- Performance config ----
TOOL_TIMEOUT = int(os.environ.get("H_AGENT_TOOL_TIMEOUT", "120"))
PROGRESS_CHUNK_SIZE = int(os.environ.get("H_AGENT_PROGRESS_CHUNK", str(1024 * 1024)))  # 1MB

# ---- Tool classification ----
READ_ONLY_TOOLS = {
    "read", "glob", "git_status", "git_log", "git_branch",
    "docker_ps", "docker_images", "shell_which", "shell_env",
    "file_exists", "file_info", "file_glob",
}


def _stream_progress(cmd: str, process: subprocess.Popen, label: str = "") -> None:
    """Stream large command output with progress indicator (runs in background thread)."""
    label_str = f"[{label}] " if label else ""
    total = 0
    chunk_num = 0
    try:
        while True:
            chunk = process.stdout.read(PROGRESS_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            chunk_num += 1
            sys.stderr.write(f"\r{label_str}Progress: {total / (1024*1024):.1f} MB streamed...\r")
            sys.stderr.flush()
    except Exception:
        pass
    finally:
        sys.stderr.write(f"\r{label_str}Done: {total / (1024*1024):.1f} MB total          \n")
        sys.stderr.flush()


def _run_command_with_timeout(cmd: str, timeout: int = TOOL_TIMEOUT, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a command with explicit timeout and progress streaming for large outputs."""
    env = os.environ.copy()
    env["TERM"] = "dumb"

    # Detect large output commands
    large_output_cmds = {"ls", "find", "grep", "cat", "diff", "git log", "git diff"}
    is_large = any(cmd.strip().startswith(c) for c in large_output_cmds)

    if is_large:
        # Use threading to stream output for large commands
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd or os.getcwd(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True,
        )
        thread = threading.Thread(target=_stream_progress, args=(cmd, proc, cmd[:40]))
        thread.daemon = True
        thread.start()

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            thread.join(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            thread.join(timeout=1)
            raise TimeoutError(f"Command timed out after {timeout}s")
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    else:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd or os.getcwd(),
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        return result


# ---- OpenAI client ----
from h_agent.core.client import get_client

client = get_client()
MODEL = os.getenv("MODEL_ID", "gpt-4o")

SYSTEM = f"""You are a coding agent at {os.getcwd()}.
Use the available tools to solve tasks efficiently.
Act, don't explain too much."""


# ============================================================
# Tool Definitions (OpenAI format)
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command. Use for file operations, git, etc. Has timeout protection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default from config, max 300)", "default": TOOL_TIMEOUT}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read the contents of a file. Returns the text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to read"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)", "default": 1},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read", "default": 2000}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write to the file"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Make a precise edit to a file by replacing exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to edit"},
                    "old_text": {"type": "string", "description": "Exact text to find and replace"},
                    "new_text": {"type": "string", "description": "Text to replace with"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"},
                    "path": {"type": "string", "description": "Base directory to search from", "default": "."}
                },
                "required": ["pattern"]
            }
        }
    }
]

# ---- Lazy loading flags ----
_EXTENDED_TOOLS_LOADED = False
_PLUGINS_LOADED = False


def _ensure_extended_tools_loaded():
    """Lazily load extended tools from h_agent.tools package."""
    global _EXTENDED_TOOLS_LOADED
    if _EXTENDED_TOOLS_LOADED:
        return
    _EXTENDED_TOOLS_LOADED = True
    try:
        from h_agent.tools import ALL_TOOLS as _EXTENDED_TOOLS
        _existing_names = {t["function"]["name"] for t in TOOLS}
        for tool in _EXTENDED_TOOLS:
            if tool["function"]["name"] not in _existing_names:
                TOOLS.append(tool)
    except ImportError:
        pass


def _ensure_plugins_loaded():
    """Lazily load plugin tools and handlers."""
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    try:
        from h_agent.plugins import load_all_plugins, get_enabled_tools, get_enabled_handlers
        load_all_plugins()
        _plugin_tools = get_enabled_tools()
        _existing_names = {t["function"]["name"] for t in TOOLS}
        for tool in _plugin_tools:
            if tool["function"]["name"] not in _existing_names:
                TOOLS.append(tool)
    except Exception:
        pass


# ============================================================
# Tool Handlers
# ============================================================

def tool_bash(command: str, timeout: int = TOOL_TIMEOUT) -> str:
    """Execute a shell command with timeout and progress."""
    dangerous = ["rm -rf /", "sudo rm", "mkfs", "dd if=", "> /dev/sd"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    timeout = min(timeout, 300)  # Cap at 5 minutes
    try:
        result = _run_command_with_timeout(command, timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        max_out = int(os.environ.get("MAX_TOOL_OUTPUT", "50000"))
        return output[:max_out] if output else "(no output)"
    except TimeoutError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"


def tool_read(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read file contents with streaming for large files."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        if not os.path.exists(path):
            return f"Error: File not found: {path}"

        size = os.path.getsize(path)
        # For files > 10MB, stream with progress
        if size > 10 * 1024 * 1024:
            sys.stderr.write(f"[read] Large file detected: {size/(1024*1024):.1f} MB\n")
            sys.stderr.flush()

        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        start = max(0, offset - 1)
        end = start + limit if limit > 0 else len(lines)
        selected = lines[start:end]
        result = ''.join(selected)

        if size > 10 * 1024 * 1024:
            sys.stderr.write(f"[read] Loaded {len(selected)} lines ({len(result)} chars)\n")
            sys.stderr.flush()

        return result if result else "(empty file)"
    except Exception as e:
        return f"Error: {e}"


def tool_write(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # For large writes, show progress
        if len(content) > 5 * 1024 * 1024:
            sys.stderr.write(f"[write] Writing {len(content)/(1024*1024):.1f} MB to {path}\n")
            sys.stderr.flush()

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_edit(path: str, old_text: str, new_text: str) -> str:
    """Make a precise edit to a file."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        if not os.path.exists(path):
            return f"Error: File not found: {path}"

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        if old_text not in content:
            return f"Error: Text not found in file. The old_text must match exactly."

        count = content.count(old_text)
        if count > 1:
            return f"Error: Found {count} occurrences of old_text. It must be unique."

        new_content = content.replace(old_text, new_text)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return f"Successfully edited {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_glob(pattern: str, path: str = ".") -> str:
    """Find files matching a pattern."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        matches = glob_module.glob(os.path.join(path, pattern), recursive=True)
        rel_matches = [os.path.relpath(m, path) for m in matches]

        if not rel_matches:
            return "No files found"

        return '\n'.join(sorted(rel_matches))
    except Exception as e:
        return f"Error: {e}"


# ============================================================
# Tool Dispatch Map
# ============================================================

TOOL_HANDLERS: Dict[str, Callable] = {
    "bash": tool_bash,
    "read": tool_read,
    "write": tool_write,
    "edit": tool_edit,
    "glob": tool_glob,
}

# Extended handlers - lazy loaded
_EXTENDED_HANDLERS_LOADED = False


def _ensure_extended_handlers_loaded():
    """Lazily load extended handlers from h_agent.tools package."""
    global _EXTENDED_HANDLERS_LOADED
    if _EXTENDED_HANDLERS_LOADED:
        return
    _EXTENDED_HANDLERS_LOADED = True
    try:
        from h_agent.tools import ALL_HANDLERS as _EXTENDED_HANDLERS
        for name, handler in _EXTENDED_HANDLERS.items():
            if name not in TOOL_HANDLERS:
                TOOL_HANDLERS[name] = handler
    except ImportError:
        pass


# Plugin handlers - lazy loaded
_PLUGIN_HANDLERS_LOADED = False


def _ensure_plugin_handlers_loaded():
    """Lazily load plugin handlers."""
    global _PLUGIN_HANDLERS_LOADED
    if _PLUGIN_HANDLERS_LOADED:
        return
    _PLUGIN_HANDLERS_LOADED = True
    try:
        from h_agent.plugins import get_enabled_handlers
        _plugin_handlers = get_enabled_handlers()
        for name, handler in _plugin_handlers.items():
            if name not in TOOL_HANDLERS:
                TOOL_HANDLERS[name] = handler
    except Exception:
        pass


def _ensure_all_loaded():
    """Ensure all tools and handlers are loaded."""
    _ensure_extended_tools_loaded()
    _ensure_plugins_loaded()
    _ensure_extended_handlers_loaded()
    _ensure_plugin_handlers_loaded()


def execute_tool_call(tool_call) -> str:
    """Execute a tool call using the dispatch map."""
    _ensure_all_loaded()
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)

    handler = TOOL_HANDLERS.get(function_name)
    if not handler:
        return f"Error: Unknown tool '{function_name}'"

    return handler(**arguments)


def _execute_single_tool(tool_call):
    """Execute a single tool call, returns (tool_call_id, result)."""
    _ensure_all_loaded()
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)

    handler = TOOL_HANDLERS.get(function_name)
    if not handler:
        result = f"Error: Unknown tool '{function_name}'"
    else:
        result = handler(**arguments)

    return tool_call.id, result


def execute_tool_calls_parallel(tool_calls: list) -> list:
    """Execute multiple tool calls with parallelization for read-only tools."""
    read_only = [tc for tc in tool_calls if tc.function.name in READ_ONLY_TOOLS]
    write_ops = [tc for tc in tool_calls if tc.function.name not in READ_ONLY_TOOLS]

    results = {}

    if read_only:
        with ThreadPoolExecutor(max_workers=len(read_only)) as executor:
            futures = {executor.submit(_execute_single_tool, tc): tc for tc in read_only}
            for future in as_completed(futures):
                tool_call_id, result = future.result()
                results[tool_call_id] = result

    for tc in write_ops:
        tool_call_id, result = _execute_single_tool(tc)
        results[tool_call_id] = result

    return [results[tc.id] for tc in tool_calls]


# ============================================================
# Agent Loop
# ============================================================

def agent_loop(messages: list):
    """The core agent loop with multi-tool support."""
    from h_agent.core.loop import run_agent_loop
    run_agent_loop(
        messages=messages,
        client=client,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        execute_tool_calls_parallel=execute_tool_calls_parallel,
        max_tokens=8000,
        print_results=True,
    )


def main():
    """Interactive REPL."""
    print(f"\033[36mOpenAI Agent Harness - s02 (Multi-Tool)\033[0m")
    print(f"Model: {MODEL}")
    print(f"Tools: {', '.join(TOOL_HANDLERS.keys())}")
    print(f"Working directory: {os.getcwd()}")
    print("Type 'q' or 'exit' to quit\n")

    history = []

    while True:
        try:
            query = input("\033[36m>> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if query.strip().lower() in ("q", "exit", ""):
            print("Goodbye!")
            break

        history.append({"role": "user", "content": query})
        agent_loop(history)

        last = history[-1]
        if last["role"] == "assistant" and last.get("content"):
            print(f"\n{last['content']}\n")


if __name__ == "__main__":
    main()
