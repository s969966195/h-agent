"""
h_agent/adapters/opencode_adapter.py - Opencode Agent Adapter

Integrates with opencode CLI via `opencode run --format json`.
"""

import json
import subprocess
import threading
import re
import os
import queue
from typing import Iterator, Optional, Any
from dataclasses import asdict

from h_agent.adapters.base import (
    BaseAgentAdapter,
    AgentResponse,
    ToolCall,
    AdapterStatus,
)


class OpencodeAdapter(BaseAgentAdapter):
    """
    Adapter for opencode CLI.
    
    Uses `opencode run --format json` for structured output parsing.
    
    Features:
    - Structured JSON event parsing
    - Tool call extraction
    - Streaming token output
    - Configurable agent selection
    """

    def __init__(
        self,
        cwd: Optional[str] = None,
        timeout: int = 300,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        opencode_path: str = "opencode",
    ):
        super().__init__(cwd=cwd, timeout=timeout)
        self.agent = agent
        self.model = model
        self.opencode_path = opencode_path
        self._session_id: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "opencode"

    def _build_args(self, message: str) -> list[str]:
        """Build the opencode run command arguments."""
        args = [
            self.opencode_path,
            "run",
            "--format", "json",
        ]
        if self.agent:
            args.extend(["--agent", self.agent])
        if self.model:
            args.extend(["--model", self.model])
        args.append(message)
        return args

    def _parse_event(self, line: str) -> Optional[dict]:
        """Parse a JSON line from opencode output."""
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _extract_tool_calls(self, events: list[dict]) -> list[ToolCall]:
        """Extract tool calls from parsed events."""
        tool_calls = []
        for event in events:
            if event.get("type") == "tool_use":
                part = event.get("part", {})
                tool_name = part.get("tool", "")
                state = part.get("state", {})
                tool_input = state.get("input", {})
                tool_output = state.get("output", "")
                
                # Build argument dict from input
                args = {}
                if "command" in tool_input:
                    args["command"] = tool_input["command"]
                elif "filePath" in tool_input:
                    args["filePath"] = tool_input["filePath"]
                    if "content" in tool_input:
                        args["content"] = tool_input["content"]
                    if "oldText" in tool_input:
                        args["oldText"] = tool_input["oldText"]
                        args["newText"] = tool_input.get("newText", "")
                elif "path" in tool_input:
                    args["path"] = tool_input["path"]
                    if "offset" in tool_input:
                        args["offset"] = tool_input["offset"]
                    if "limit" in tool_input:
                        args["limit"] = tool_input["limit"]
                
                tool_calls.append(ToolCall(
                    name=tool_name,
                    arguments=args,
                    result=tool_output if isinstance(tool_output, str) else str(tool_output),
                ))
        return tool_calls

    def _extract_text(self, events: list[dict]) -> str:
        """Extract text content from events."""
        parts = []
        for event in events:
            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def _extract_metadata(self, events: list[dict]) -> dict[str, Any]:
        """Extract metadata (session ID, tokens, etc.) from events."""
        meta = {}
        for event in events:
            if "sessionID" in event:
                meta["session_id"] = event["sessionID"]
                self._session_id = event["sessionID"]
            if event.get("type") == "step_finish":
                part = event.get("part", {})
                meta["reason"] = part.get("reason")
                meta["cost"] = part.get("cost")
                meta["tokens"] = part.get("tokens")
        return meta

    def chat(self, message: str, **kwargs) -> AgentResponse:
        """
        Send a message and get a complete response.
        
        Uses opencode run --format json, parses all events,
        and returns structured response.
        """
        args = self._build_args(message)
        events = []
        
        self._set_status(AdapterStatus.RUNNING)
        
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            self._process = proc
            
            # Read stdout line by line
            stdout_lines = []
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                stdout_lines.append(line)
                event = self._parse_event(line)
                if event:
                    events.append(event)
            
            # Wait for process to finish
            proc.wait(timeout=self.timeout)
            
        except subprocess.TimeoutExpired:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=f"Timeout after {self.timeout}s")
        except Exception as e:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=str(e))
        finally:
            self._set_status(AdapterStatus.IDLE)
        
        # Parse events into response
        tool_calls = self._extract_tool_calls(events)
        content = self._extract_text(events)
        metadata = self._extract_metadata(events)
        
        # Check for errors in stderr
        if proc.returncode != 0 and proc.stderr:
            stderr = proc.stderr.read()
            if stderr and not content:
                return AgentResponse(error=f"opencode error: {stderr[:500]}")
        
        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            metadata=metadata,
        )

    def stream_chat(self, message: str, **kwargs) -> Iterator[str]:
        """
        Stream response tokens incrementally.
        
        Yields text tokens as they arrive from opencode.
        """
        args = self._build_args(message)
        events = []
        
        self._set_status(AdapterStatus.RUNNING)
        
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            self._process = proc
            
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                event = self._parse_event(line)
                if event:
                    events.append(event)
                    if event.get("type") == "text":
                        text = event.get("part", {}).get("text", "")
                        if text:
                            yield text
            
            proc.wait(timeout=self.timeout)
            
        except subprocess.TimeoutExpired:
            yield f"[Timeout after {self.timeout}s]"
        except Exception as e:
            yield f"[Error: {e}]"
        finally:
            self._set_status(AdapterStatus.IDLE)

    def stop(self):
        """Terminate the running opencode process."""
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None
        self._set_status(AdapterStatus.IDLE)

    @property
    def session_id(self) -> Optional[str]:
        """Return the last session ID used."""
        return self._session_id

    def get_session_list(self) -> list[dict]:
        """List all opencode sessions."""
        try:
            result = subprocess.run(
                [self.opencode_path, "session", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "TERM": "dumb"},
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return []

    def attach_session(self, session_id: str) -> bool:
        """
        Set the session to continue.
        
        Note: This sets the session for the next chat() call via --continue flag.
        """
        self._session_id = session_id
        return True
