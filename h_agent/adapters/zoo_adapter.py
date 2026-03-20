#!/usr/bin/env python3
"""
h_agent/adapters/zoo_adapter.py - Agent-Zoo Adapter

Integrates h-agent with the agent-zoo multi-agent system.
Allows calling zoo animals (xueqiu, liuliu, xiaohuang, etc.) as team members.

Usage:
    from h_agent.adapters.zoo_adapter import ZooAdapter, get_zoo_animal
    
    # Direct call
    adapter = ZooAdapter(animal="xueqiu")
    response = adapter.chat("Hello xueqiu!")
    
    # Team integration
    from h_agent.team.team import AgentTeam
    team = AgentTeam()
    team.register("xueqiu", AgentRole.RESEARCHER, get_zoo_animal("xueqiu"))
"""

import json
import subprocess
import os
import threading
from typing import Iterator, Optional, Any, Dict, List, Callable, AsyncGenerator
from dataclasses import dataclass, field, asdict

from h_agent.adapters.base import (
    BaseAgentAdapter,
    AgentResponse,
    ToolCall,
    AdapterStatus,
)


# ============================================================
# Zoo Animal Definitions
# ============================================================

ZOO_ANIMALS: Dict[str, Dict[str, Any]] = {
    "xueqiu": {
        "name": "xueqiu",
        "species": "Snowball Monkey",
        "color": "#FF6B6B",
        "description": "Research specialist - great for searching, analysis, and exploration",
        "tools": ["web_search", "read", "glob", "grep"],
        "default_model": "glm-4",
    },
    "liuliu": {
        "name": "liuliu",
        "species": "Streamlined Otter",
        "color": "#4ECDC4",
        "description": "Code architect - excellent for system design and refactoring",
        "tools": ["read", "write", "edit", "bash"],
        "default_model": "glm-4",
    },
    "xiaohuang": {
        "name": "xiaohuang",
        "species": "Golden Retriever",
        "color": "#FFE66D",
        "description": "QA tester - perfect for testing, debugging and finding edge cases",
        "tools": ["bash", "read", "glob", "grep"],
        "default_model": "glm-4",
    },
    "heibai": {
        "name": "heibai",
        "species": "Panda",
        "color": "#2D3436",
        "description": "Documentation expert - excels at writing docs and comments",
        "tools": ["read", "write", "edit"],
        "default_model": "glm-4",
    },
    "xiaozhu": {
        "name": "xiaozhu",
        "species": "Teal Pig",
        "color": "#A29BFE",
        "description": "DevOps engineer - containerization, CI/CD, deployment",
        "tools": ["bash", "docker", "read", "write"],
        "default_model": "glm-4",
    },
}


# ============================================================
# Zoo Configuration
# ============================================================

@dataclass
class ZooConfig:
    """Configuration for zoo animals."""
    zoo_path: str = "zoo"  # CLI path for zoo command
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 300
    animals: Dict[str, Dict[str, Any]] = field(default_factory=lambda: ZOO_ANIMALS)
    
    @classmethod
    def from_env(cls) -> "ZooConfig":
        """Load config from environment variables."""
        return cls(
            zoo_path=os.getenv("ZOO_PATH", "zoo"),
            api_base_url=os.getenv("ZOO_API_BASE_URL"),
            api_key=os.getenv("ZOO_API_KEY"),
            timeout=int(os.getenv("ZOO_TIMEOUT", "300")),
        )


@dataclass 
class AnimalInfo:
    """Information about a zoo animal."""
    name: str
    species: str
    color: str
    description: str
    tools: List[str]
    default_model: str
    available: bool = True


# ============================================================
# Zoo Adapter
# ============================================================

class ZooAdapter(BaseAgentAdapter):
    """
    Adapter for agent-zoo CLI.
    
    Calls zoo animals via `zoo run <animal> <prompt>`.
    
    Features:
    - All zoo animals supported
    - Configurable via YAML or env
    - Team integration helper
    """

    def __init__(
        self,
        animal: str = "xueqiu",
        cwd: Optional[str] = None,
        timeout: int = 300,
        model: Optional[str] = None,
        zoo_path: str = "zoo",
        config: Optional[ZooConfig] = None,
    ):
        super().__init__(cwd=cwd, timeout=timeout)
        self.animal = animal
        self.model = model
        self.zoo_path = zoo_path
        self.config = config or ZooConfig.from_env()
        self._session_id: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"zoo:{self.animal}"

    def _build_args(self, message: str) -> List[str]:
        """Build the zoo run command arguments."""
        args = [
            self.zoo_path,
            "run",
            self.animal,
            "--format", "json",
        ]
        if self.model:
            args.extend(["--model", self.model])
        if self.config.api_base_url:
            args.extend(["--api-base", self.config.api_base_url])
        args.append("--")
        args.append(message)
        return args

    def _parse_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse JSON output from zoo."""
        output = output.strip()
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    def _output_to_response(self, output: str, stderr: str = "") -> AgentResponse:
        """Convert zoo output to AgentResponse."""
        data = self._parse_output(output)
        
        if data is None:
            # Try to extract text from raw output
            if output:
                return AgentResponse(content=output.strip())
            if stderr:
                return AgentResponse(error=stderr[:500])
            return AgentResponse(error="Empty response from zoo")
        
        # Parse structured response
        content = data.get("content", "") or data.get("text", "") or ""
        tool_calls = []
        
        for tc in data.get("tool_calls", []):
            if isinstance(tc, dict):
                tool_calls.append(ToolCall(
                    name=tc.get("name", tc.get("tool", "unknown")),
                    arguments=tc.get("arguments", tc.get("args", {})),
                    result=tc.get("result", tc.get("output", "")),
                ))
        
        metadata = {
            "animal": self.animal,
            "session_id": data.get("session_id", self._session_id),
        }
        if "tokens" in data:
            metadata["tokens"] = data["tokens"]
        if "cost" in data:
            metadata["cost"] = data["cost"]
        
        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            metadata=metadata,
        )

    def chat(self, message: str, **kwargs) -> AgentResponse:
        """
        Send a message and get a complete response from a zoo animal.
        """
        args = self._build_args(message)
        
        self._set_status(AdapterStatus.RUNNING)
        
        try:
            env = {**os.environ, "TERM": "dumb"}
            if self.config.api_key:
                env["ZOO_API_KEY"] = self.config.api_key
            
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=True,
                env=env,
            )
            self._process = proc
            
            stdout, stderr = proc.communicate(timeout=self.timeout)
            
            # Update session ID if present
            data = self._parse_output(stdout)
            if data and "session_id" in data:
                self._session_id = data["session_id"]
            
        except subprocess.TimeoutExpired:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=f"Timeout after {self.timeout}s")
        except Exception as e:
            self._set_status(AdapterStatus.ERROR)
            return AgentResponse(error=str(e))
        finally:
            self._set_status(AdapterStatus.IDLE)
        
        return self._output_to_response(stdout, stderr)

    def stream_chat(self, message: str, **kwargs) -> Iterator[str]:
        """
        Stream response tokens incrementally.
        """
        args = self._build_args(message)
        
        self._set_status(AdapterStatus.RUNNING)
        
        try:
            env = {**os.environ, "TERM": "dumb"}
            if self.config.api_key:
                env["ZOO_API_KEY"] = self.config.api_key
            
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                text=True,
                env=env,
            )
            self._process = proc
            
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                data = self._parse_output(line)
                if data:
                    text = data.get("content", "") or data.get("text", "")
                    if text:
                        yield text
                    if data.get("type") == "done" or data.get("is_complete"):
                        break
            
            proc.wait(timeout=self.timeout)
            
        except subprocess.TimeoutExpired:
            yield f"[Timeout after {self.timeout}s]"
        except Exception as e:
            yield f"[Error: {e}]"
        finally:
            self._set_status(AdapterStatus.IDLE)

    def stop(self):
        """Terminate the running zoo process."""
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


# ============================================================
# Zoo Animal Factory (for Team Integration)
# ============================================================

def get_zoo_animal(
    animal: str,
    timeout: int = 300,
) -> Callable[["TeamMessage"], "TaskResult"]:
    """
    Get a handler function for a zoo animal (for team integration).
    
    Usage:
        from h_agent.team.team import AgentTeam, AgentRole
        
        team = AgentTeam()
        team.register("xueqiu", AgentRole.RESEARCHER, get_zoo_animal("xueqiu"))
        
        result = team.delegate("xueqiu", "task", "Search for...")
    """
    from h_agent.team.team import TaskResult
    from h_agent.team.protocol import AgentRole
    
    def handler(msg) -> TaskResult:
        adapter = ZooAdapter(animal=animal, timeout=timeout)
        response = adapter.chat(str(msg.content))
        
        return TaskResult(
            agent_name=f"zoo:{animal}",
            role=AgentRole.RESEARCHER,
            success=not response.has_error(),
            content=response.content,
            error=response.error,
        )
    
    return handler


def list_zoo_animals() -> List[AnimalInfo]:
    """List all available zoo animals with their info."""
    return [
        AnimalInfo(
            name=name,
            species=info["species"],
            color=info["color"],
            description=info["description"],
            tools=info["tools"],
            default_model=info["default_model"],
        )
        for name, info in ZOO_ANIMALS.items()
    ]


# ============================================================
# Zoo CLI Helpers
# ============================================================

def run_zoo_command(args: List[str], timeout: int = 60) -> Dict[str, Any]:
    """Run a zoo CLI command and return parsed JSON output."""
    try:
        proc = subprocess.run(
            ["zoo"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "TERM": "dumb"},
        )
        if proc.returncode == 0:
            return {"success": True, "data": json.loads(proc.stdout) if proc.stdout else None}
        return {"success": False, "error": proc.stderr or "Command failed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_zoo_status() -> Dict[str, Any]:
    """Get zoo system status."""
    result = run_zoo_command(["status"])
    if result["success"]:
        return result["data"]
    
    # Fallback: return configured animals
    return {
        "status": "configured",
        "animals": list(ZOO_ANIMALS.keys()),
    }


# ============================================================
# Adapter Registry Support
# ============================================================

def create_zoo_adapter(animal: str = "xueqiu", **kwargs) -> ZooAdapter:
    """Factory function for zoo adapter (used by adapter registry)."""
    return ZooAdapter(animal=animal, **kwargs)
