#!/usr/bin/env python3
"""
h_agent/features/skills.py - On-Demand Skill Loading

Load knowledge when you need it, not upfront.

Skills are markdown files in the skills/ directory.
They can be loaded on-demand via the load_skill tool.
Loaded skills are injected into the context as tool results.
"""

import os
import json
import glob as glob_module
import subprocess
from typing import Callable, Dict, Any, List, Optional
from pathlib import Path
from h_agent.core.client import get_client

client = get_client()
MODEL = os.getenv("MODEL_ID", "gpt-4o")

WORK_DIR = os.getcwd()
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


# ============================================================
# Skill Loading System
# ============================================================

def list_available_skills() -> List[str]:
    """List all available skill files."""
    if not SKILLS_DIR.exists():
        return []
    return [f.stem for f in SKILLS_DIR.glob("*.md")]


def load_skill_content(skill_name: str) -> Optional[str]:
    """Load a skill's content from file."""
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    if not skill_path.exists():
        return None
    return skill_path.read_text(encoding='utf-8')


def get_skill_info(skill_name: str) -> Dict[str, Any]:
    """Get metadata about a skill."""
    content = load_skill_content(skill_name)
    if not content:
        return {"error": f"Skill '{skill_name}' not found"}
    
    # Extract description from first paragraph after title
    lines = content.split('\n')
    description = ""
    in_desc = False
    for line in lines:
        if line.startswith('# '):
            in_desc = True
            continue
        if in_desc and line.strip():
            description = line.strip()
            break
    
    return {
        "name": skill_name,
        "description": description,
        "available": True,
        "path": str(SKILLS_DIR / f"{skill_name}.md"),
    }


# ============================================================
# Tool Handlers
# ============================================================

def tool_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo rm", "mkfs"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        result = subprocess.run(command, shell=True, cwd=WORK_DIR,
                               capture_output=True, text=True, timeout=120)
        return (result.stdout + result.stderr).strip()[:30000] or "(no output)"
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
        return ''.join(lines[max(0, offset-1):offset-1+limit]) or "(empty)"
    except Exception as e:
        return f"Error: {e}"


def tool_write(path: str, content: str) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Wrote {len(content)} chars"
    except Exception as e:
        return f"Error: {e}"


def tool_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        if not os.path.exists(path):
            return "Error: File not found"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_text not in content:
            return "Error: Text not found"
        if content.count(old_text) > 1:
            return "Error: Multiple matches"
        with open(path, 'w') as f:
            f.write(content.replace(old_text, new_text))
        return "Edited successfully"
    except Exception as e:
        return f"Error: {e}"


def tool_glob(pattern: str, path: str = ".") -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(WORK_DIR, path)
        matches = glob_module.glob(os.path.join(path, pattern), recursive=True)
        return '\n'.join(os.path.relpath(m, path) for m in matches) or "No files"
    except Exception as e:
        return f"Error: {e}"


def tool_load_skill(skill_name: str) -> str:
    """Load a skill's content into context."""
    content = load_skill_content(skill_name)
    if not content:
        available = list_available_skills()
        return f"Skill '{skill_name}' not found. Available: {available}"
    
    print(f"\033[32m📚 Loaded skill: {skill_name}\033[0m")
    return f"=== SKILL: {skill_name} ===\n\n{content}"


def tool_list_skills() -> str:
    """List all available skills."""
    skills = list_available_skills()
    if not skills:
        return "No skills available. Add .md files to skills/ directory."
    
    result = "Available Skills:\n"
    for skill in skills:
        info = get_skill_info(skill)
        result += f"  - {skill}: {info.get('description', 'No description')}\n"
    return result


# ============================================================
# Tool Definitions
# ============================================================

TOOLS = [
    {"type": "function", "function": {
        "name": "bash", "description": "Run a shell command.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "read", "description": "Read file contents.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["path"]}
    }},
    {"type": "function", "function": {
        "name": "write", "description": "Write to file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "edit", "description": "Edit file precisely.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}
    }},
    {"type": "function", "function": {
        "name": "glob", "description": "Find files by pattern.",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}
    }},
    {"type": "function", "function": {
        "name": "load_skill", "description": "Load a skill file for specialized knowledge. Skills contain domain-specific instructions.",
        "parameters": {"type": "object", "properties": {"skill_name": {"type": "string", "description": "Name of the skill to load"}}, "required": ["skill_name"]}
    }},
    {"type": "function", "function": {
        "name": "list_skills", "description": "List all available skills.",
        "parameters": {"type": "object", "properties": {}}
    }},
]

TOOL_HANDLERS = {
    "bash": tool_bash,
    "read": tool_read,
    "write": tool_write,
    "edit": tool_edit,
    "glob": tool_glob,
    "load_skill": tool_load_skill,
    "list_skills": tool_list_skills,
}


def execute_tool_call(tool_call) -> str:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"Error: Unknown tool '{name}'"
    return handler(**args)


# ============================================================
# Agent Loop
# ============================================================

def get_system_prompt() -> str:
    skills = list_available_skills()
    skills_hint = f"Available skills: {skills}" if skills else "No skills loaded yet."
    
    return f"""You are a coding agent at {WORK_DIR}.

{skills_hint}

Use 'load_skill' to load specialized knowledge when needed.
Use 'list_skills' to see all available skills.

Act efficiently."""


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
    print(f"\033[36mOpenAI Agent Harness - s05 (Skill Loading)\033[0m")
    print(f"Model: {MODEL}")
    print(f"Skills dir: {SKILLS_DIR}")
    print(f"Available skills: {list_available_skills()}")
    print("\nType 'q' to quit\n")
    
    history = []
    while True:
        try:
            query = input("\033[36m>> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        if history[-1].get("content"):
            print(f"\n{history[-1]['content']}\n")


if __name__ == "__main__":
    main()