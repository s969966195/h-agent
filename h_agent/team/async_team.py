#!/usr/bin/env python3
"""
h_agent/team/async_team.py - s09 Async Agent Teams Implementation

Persistent teammate threads with JSONL inbox-based communication.
Following learn-claude-code s09 pattern.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from h_agent.core.client import get_client
from h_agent.core.config import MODEL

TEAM_DIR = Path(os.path.expanduser("~/.h-agent/team"))


class AsyncMessageBus:
    """File-based async message bus using JSONL inboxes.
    
    Messages are stored as JSONL (one JSON object per line).
    read_inbox() drains the inbox (clears after read).
    """
    
    def __init__(self, inbox_dir: Path = None):
        self.inbox_dir = inbox_dir or (TEAM_DIR / "inbox_async")
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", **extra: Any) -> str:
        """Append message to recipient's inbox file."""
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        msg.update(extra)
        
        inbox_path = self.inbox_dir / f"{to}.jsonl"
        
        with self._lock:
            with open(inbox_path, "a") as f:
                f.write(json.dumps(msg) + "\n")
        
        return f"Sent {msg_type} to {to}"
    
    def read_inbox(self, name: str) -> List[Dict]:
        """Drain and return all messages from inbox. Returns [] if empty."""
        inbox_path = self.inbox_dir / f"{name}.jsonl"
        
        if not inbox_path.exists():
            return []
        
        with self._lock:
            content = inbox_path.read_text()
            inbox_path.write_text("")
        
        if not content.strip():
            return []
        
        messages = []
        for line in content.strip().split("\n"):
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        
        return messages
    
    def broadcast(self, sender: str, recipients: List[str], content: str,
                  msg_type: str = "broadcast") -> str:
        """Broadcast message to all recipients except sender."""
        count = 0
        for name in recipients:
            if name != sender:
                self.send(sender, name, content, msg_type)
                count += 1
        return f"Broadcast to {count} teammates"


class TeammateManager:
    """Manages team lifecycle and teammate threads.
    
    Spawns persistent daemon threads for each teammate.
    Tracks status: working -> idle -> shutdown.
    """
    
    def __init__(self, team_id: str = "default", inbox_dir: Path = None):
        self.team_id = team_id
        self.inbox_dir = inbox_dir or (TEAM_DIR / "inbox_async")
        self.threads: Dict[str, threading.Thread] = {}
        self.statuses: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._shutdown_requested: Dict[str, bool] = {}
    
    def spawn(self, name: str, role: str, prompt: str,
              agent_handler: Any) -> str:
        """Spawn a persistent teammate thread."""
        if name in self.threads and self.statuses.get(name) == "working":
            return f"Error: '{name}' is already running"
        
        self._shutdown_requested[name] = False
        self.statuses[name] = "working"
        
        thread = threading.Thread(
            target=_teammate_loop,
            args=(name, role, prompt, agent_handler, self),
            daemon=True,
        )
        self.threads[name] = thread
        thread.start()
        
        return f"Spawned '{name}' (role: {role})"
    
    def shutdown(self, name: str) -> str:
        """Signal a teammate to gracefully shutdown."""
        self._shutdown_requested[name] = True
        self.statuses[name] = "shutdown"
        return f"Shutdown requested for '{name}'"
    
    def get_status(self, name: str) -> Optional[str]:
        """Get current status: 'working', 'idle', or 'shutdown'."""
        return self.statuses.get(name)
    
    def list_members(self) -> List[Dict]:
        """Return team roster with name, role, status."""
        return [
            {"name": name, "status": status}
            for name, status in self.statuses.items()
        ]
    
    def _set_status(self, name: str, status: str):
        """Internal: set teammate status."""
        with self._lock:
            self.statuses[name] = status


def _execute_team_tool(tool_name: str, args: Dict, sender: str,
                      bus: AsyncMessageBus) -> str:
    """Execute a tool call within teammate context."""
    if tool_name == "bash":
        import subprocess
        try:
            r = subprocess.run(
                args["command"], shell=True,
                capture_output=True, text=True, timeout=120
            )
            return (r.stdout + r.stderr).strip()[:50000] or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Timeout (120s)"
        except Exception as e:
            return f"Error: {e}"
    
    elif tool_name == "read":
        try:
            path = Path(args["file_path"])
            text = path.read_text()
            limit = args.get("limit", 50000)
            return text[:limit] if len(text) > limit else text
        except Exception as e:
            return f"Error: {e}"
    
    elif tool_name == "write":
        try:
            path = Path(args["file_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"])
            return f"Wrote {len(args['content'])} bytes"
        except Exception as e:
            return f"Error: {e}"
    
    elif tool_name == "edit":
        try:
            path = Path(args["file_path"])
            content = path.read_text()
            if args["old_text"] not in content:
                return f"Error: Text not found in {args['file_path']}"
            content = content.replace(args["old_text"], args["new_text"], 1)
            path.write_text(content)
            return f"Edited {args['file_path']}"
        except Exception as e:
            return f"Error: {e}"
    
    elif tool_name == "send_message":
        return bus.send(sender, args["to"], args["content"], args.get("msg_type", "message"))
    
    elif tool_name == "read_inbox":
        return json.dumps(bus.read_inbox(sender), indent=2)
    
    return f"Unknown tool: {tool_name}"


TEAMMATE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"}
                },
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
                    "file_path": {"type": "string", "description": "Path to file"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write content to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace exact text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["file_path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to a teammate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient teammate name"},
                    "content": {"type": "string", "description": "Message content"},
                    "msg_type": {"type": "string", "enum": ["message", "task", "broadcast"]}
                },
                "required": ["to", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_inbox",
            "description": "Read and drain your inbox.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]


def _teammate_loop(name: str, role: str, prompt: str,
                   agent_handler: Any, manager: TeammateManager,
                   max_iterations: int = 50):
    """Per-teammate thread loop.
    
    States: WORKING -> IDLE (poll inbox) -> WORKING
    Handles shutdown gracefully.
    """
    client = get_client()
    messages = [{"role": "user", "content": prompt}]
    sys_prompt = f"You are '{name}', role: {role}. Use send_message to communicate. Complete your task."
    
    idle_poll_interval = 5
    
    for iteration in range(max_iterations):
        if manager._shutdown_requested.get(name, False):
            manager._set_status(name, "shutdown")
            return
        
        bus = AsyncMessageBus()
        
        inbox = bus.read_inbox(name)
        for msg in inbox:
            messages.append({
                "role": "user",
                "content": json.dumps(msg)
            })
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": sys_prompt}] + messages,
                tools=TEAMMATE_TOOLS,
                max_tokens=8000,
            )
        except Exception as e:
            messages.append({
                "role": "user",
                "content": f"Error: {e}"
            })
            continue
        
        if not response.choices[0].message.tool_calls:
            manager._set_status(name, "idle")
            time.sleep(idle_poll_interval)
            continue
        
        manager._set_status(name, "working")
        
        messages.append({
            "role": "assistant",
            "content": response.choices[0].message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in response.choices[0].message.tool_calls
            ]
        })
        
        for tc in response.choices[0].message.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _execute_team_tool(tc.function.name, args, name, bus)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })
    
    manager._set_status(name, "shutdown")
