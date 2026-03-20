"""
h_agent/adapters/claude_adapter.py - Claude Code Adapter

Integrates with Anthropic's Claude Code CLI via `claude --print`.
"""

import json
import subprocess
import os
from typing import Iterator, Optional, Any

from h_agent.adapters.base import (
    BaseAgentAdapter,
    AgentResponse,
    ToolCall,
    AdapterStatus,
)


class ClaudeAdapter(BaseAgentAdapter):
    """
    Adapter for Claude Code CLI.
    
    Uses `claude --print` for non-interactive execution.
    """

    def __init__(
        self,
        cwd: Optional[str] = None,
        timeout: int = 300,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        claude_path: str = "claude",
    ):
        super().__init__(cwd=cwd, timeout=timeout)
        self.model = model
        self.agent = agent
        self.claude_path = claude_path
        self._last_session: Optional[str] = None

    @property
    def name(self) -> str:
        return "claude"

    def _build_args(self, message: str) -> list[str]:
        """Build the claude command arguments."""
        args = [self.claude_path, "--print"]
        
        if self.model:
            args.extend(["--model", self.model])
        if self.agent:
            args.extend(["--agent", self.agent])
        
        # Enable structured output
        args.extend(["--output-format", "stream-json"])
        args.extend(["--include-partial-messages"])
        
        args.append(message)
        return args

    def chat(self, message: str, **kwargs) -> AgentResponse:
        """
        Send a message and get a complete response.
        
        Parses Claude's JSON stream output.
        """
        args = self._build_args(message)
        content_parts = []
        tool_calls = []
        error_msg = None
        
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
            
            # Read JSON lines from stdout
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Handle different message types
                msg_type = data.get("type") or data.get("message", {}).get("type", "")
                
                if msg_type == "content" or "content" in data:
                    content = data.get("content") or data.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if block.get("type") == "text":
                                content_parts.append(block.get("text", ""))
                    elif isinstance(content, str):
                        content_parts.append(content)
                
                elif msg_type == "tool_use" or msg_type == "tool_result":
                    # Claude tool call format
                    tool_data = data.get("tool", data.get("message", {}))
                    if tool_data:
                        tool_name = tool_data.get("name", "")
                        tool_input = tool_data.get("input", {})
                        tool_result = tool_data.get("result") or tool_data.get("output", "")
                        
                        tool_calls.append(ToolCall(
                            name=tool_name,
                            arguments=tool_input if isinstance(tool_input, dict) else {"raw": str(tool_input)},
                            result=str(tool_result) if tool_result else None,
                        ))
                
                elif msg_type == "error":
                    error_msg = data.get("error", str(data))
                
                elif msg_type == "result" or msg_type == "final":
                    # Final result
                    result_data = data.get("result", data.get("message", {}))
                    if isinstance(result_data, dict):
                        content = result_data.get("content", "")
                        if isinstance(content, list):
                            for block in content:
                                if block.get("type") == "text":
                                    content_parts.append(block.get("text", ""))
                        elif isinstance(content, str):
                            content_parts.append(content)
            
            proc.wait(timeout=self.timeout)
            
        except subprocess.TimeoutExpired:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=f"Timeout after {self.timeout}s")
        except Exception as e:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=str(e))
        finally:
            self._set_status(AdapterStatus.IDLE)
        
        if error_msg:
            return AgentResponse(error=error_msg)
        
        content = "\n".join(filter(None, content_parts))
        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            metadata={"model": self.model, "session": self._last_session},
        )

    def stream_chat(self, message: str, **kwargs) -> Iterator[str]:
        """
        Stream response tokens incrementally.
        """
        args = self._build_args(message)
        
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
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                msg_type = data.get("type") or data.get("message", {}).get("type", "")
                
                if msg_type == "content" or "content" in data:
                    content = data.get("content") or data.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if block.get("type") == "text":
                                yield block.get("text", "")
                    elif isinstance(content, str):
                        yield content
            
            proc.wait(timeout=self.timeout)
            
        except subprocess.TimeoutExpired:
            yield f"[Timeout after {self.timeout}s]"
        except Exception as e:
            yield f"[Error: {e}]"
        finally:
            self._set_status(AdapterStatus.IDLE)

    def stop(self):
        """Terminate the running Claude process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._set_status(AdapterStatus.IDLE)
