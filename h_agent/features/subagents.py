#!/usr/bin/env python3
"""
h_agent/features/subagents.py - Subagent for Task Isolation

Break big tasks down; each subtask gets a clean context.

The delegate tool allows the main agent to spawn a subagent with:
- Independent message history
- Focused task context
- Isolated execution

When the subagent completes, only the result is returned to the main agent.
"""

import os
import json
import glob as glob_module
import subprocess
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass
from h_agent.core.client import get_client

client = get_client()
MODEL = os.getenv("MODEL_ID", "gpt-4o")

WORK_DIR = os.getcwd()

# ============================================================
# Subagent System
# ============================================================

@dataclass
class SubagentResult:
    """Result from a subagent execution."""
    success: bool
    content: str
    steps: int
    error: Optional[str] = None


def run_subagent(
    task: str,
    context: str = "",
    tools: List[dict] = None,
    max_steps: int = 20,
) -> SubagentResult:
    """
    Run a subagent with an isolated context.
    
    Args:
        task: The task for the subagent to complete
        context: Additional context (file paths, previous findings, etc.)
        tools: Tools available to subagent (default: bash, read, write, edit, glob)
        max_steps: Maximum number of tool calls before stopping
    
    Returns:
        SubagentResult with success status and content
    """
    # Default tools for subagent
    if tools is None:
        tools = TOOLS[:5]  # bash, read, write, edit, glob (no TodoWrite, no delegate)
    
    # Subagent system prompt
    subagent_system = f"""You are a focused assistant helping with a specific task.

Working directory: {WORK_DIR}

Your task: {task}

Additional context: {context if context else "None provided"}

Instructions:
1. Complete the task efficiently
2. Use tools as needed
3. When done, provide a clear summary of what you found or did
4. Keep your response focused and relevant to the task

Do not ask for clarification. Make reasonable assumptions and proceed."""

    # Initialize subagent messages
    messages = [{"role": "user", "content": task}]
    
    step_count = 0
    
    while step_count < max_steps:
        step_count += 1
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": subagent_system}] + messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=4000,
            )
        except Exception as e:
            return SubagentResult(
                success=False,
                content="",
                steps=step_count,
                error=f"API error: {e}"
            )
        
        message = response.choices[0].message
        
        # No tool calls = subagent is done
        if not message.tool_calls:
            content = message.content or "Task completed."
            return SubagentResult(
                success=True,
                content=content,
                steps=step_count,
            )
        
        # Execute tool calls
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": message.tool_calls,
        })
        
        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, is_subagent=True)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
    
    # Max steps reached
    return SubagentResult(
        success=False,
        content="Subagent reached maximum steps without completing.",
        steps=step_count,
        error="max_steps_exceeded"
    )


# ============================================================
# Tools (same as s02/s03 but without delegate for subagents)
# ============================================================

def tool_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo rm", "mkfs", "dd if="]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(command, shell=True, cwd=WORK_DIR,
                               capture_output=True, text=True, timeout=120)
        output = (result.stdout + result.stderr).strip()
        return output[:30000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except Exception as e:
        return f"Error: {e}"


def tool_read(path: str, offset: int = 1, limit: int = 2000) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        start = max(0, offset - 1)
        end = start + limit if limit > 0 else len(lines)
        return ''.join(lines[start:end]) or "(empty file)"
    except UnicodeDecodeError:
        return "Error: Binary file"
    except Exception as e:
        return f"Error: {e}"


def tool_write(path: str, content: str) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_text not in content:
            return "Error: Text not found"
        count = content.count(old_text)
        if count > 1:
            return f"Error: Found {count} occurrences, must be unique"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content.replace(old_text, new_text))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def tool_glob(pattern: str, path: str = ".") -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        matches = glob_module.glob(os.path.join(path, pattern), recursive=True)
        rel_matches = [os.path.relpath(m, path) for m in matches]
        return '\n'.join(sorted(rel_matches)) if rel_matches else "No files found"
    except Exception as e:
        return f"Error: {e}"


def tool_delegate(task: str, context: str = "") -> str:
    """
    Delegate a subtask to a subagent.
    
    This is the main agent's delegate tool.
    Subagents don't have this tool to prevent infinite nesting.
    """
    print(f"\033[35m🤖 Spawning subagent: {task[:50]}...\033[0m")
    
    result = run_subagent(task=task, context=context)
    
    if result.success:
        print(f"\033[35m✅ Subagent completed in {result.steps} steps\033[0m")
    else:
        print(f"\033[35m❌ Subagent failed: {result.error}\033[0m")
    
    return json.dumps({
        "success": result.success,
        "result": result.content,
        "steps": result.steps,
        "error": result.error
    })


# Tool definitions for main agent
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 2000}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write content to a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Make a precise edit to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
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
                "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."}},
                "required": ["pattern"]
            }
        }
    },
    # Delegate tool - only for main agent
    {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": "Delegate a subtask to a focused subagent. Use for complex analysis, file exploration, or parallel work. The subagent has its own clean context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task for the subagent"},
                    "context": {"type": "string", "description": "Additional context (file paths, previous findings)"}
                },
                "required": ["task"]
            }
        }
    }
]

# Handlers for main agent
TOOL_HANDLERS: Dict[str, Callable] = {
    "bash": tool_bash,
    "read": tool_read,
    "write": tool_write,
    "edit": tool_edit,
    "glob": tool_glob,
    "delegate": tool_delegate,
}

# Handlers for subagent (no delegate)
SUBAGENT_TOOL_HANDLERS: Dict[str, Callable] = {
    "bash": tool_bash,
    "read": tool_read,
    "write": tool_write,
    "edit": tool_edit,
    "glob": tool_glob,
}


def execute_tool_call(tool_call, is_subagent: bool = False) -> str:
    """Execute a tool call."""
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)
    
    handlers = SUBAGENT_TOOL_HANDLERS if is_subagent else TOOL_HANDLERS
    handler = handlers.get(function_name)
    
    if not handler:
        return f"Error: Unknown tool '{function_name}'"
    
    return handler(**arguments)


def get_system_prompt() -> str:
    return f"""You are a coding agent at {WORK_DIR}.

Use the available tools to solve tasks efficiently.

IMPORTANT: For complex or exploratory tasks, use the 'delegate' tool to spawn a subagent. The subagent will work with a clean context and return only the result.

Examples of good delegate tasks:
- "Analyze the structure of this codebase"
- "Find all uses of deprecated functions"
- "Review this file for potential bugs"

Act, don't explain too much."""


def agent_loop(messages: list):
    """DEPRECATED: Use h_agent.core.loop.run_agent_loop instead."""
    from h_agent.core.loop import run_agent_loop
    run_agent_loop(
        messages=messages,
        client=client,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        system_prompt=get_system_prompt(),
        max_tokens=8000,
        print_results=True,
    )


def main():
    print(f"\033[36mOpenAI Agent Harness - s04 (Subagent)\033[0m")
    print(f"Model: {MODEL}")
    print(f"Tools: {', '.join(TOOL_HANDLERS.keys())}")
    print(f"Working directory: {WORK_DIR}")
    print("\nFeatures:")
    print("  - delegate: Spawn subagents for focused tasks")
    print("  - Subagents have isolated context")
    print("\nType 'q' to quit\n")
    
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