"""
h_agent/adapters/base.py - Base Adapter Interface

Defines the contract for all CLI agent adapters.
"""

import subprocess
import json
import time
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional, Any
from enum import Enum


class AdapterStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ToolCall:
    """Represents a tool call made by the agent."""
    name: str
    arguments: dict[str, Any]
    result: Optional[str] = None


@dataclass
class AgentResponse:
    """Structured response from an agent."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_error(self) -> bool:
        return self.error is not None

    def is_complete(self) -> bool:
        return not self.has_error() and not self.tool_calls


class BaseAgentAdapter(ABC):
    """
    Abstract base class for CLI agent adapters.
    
    All adapters must implement:
    - name: str - identifier for this adapter
    - chat(): send a message and get a response
    - stream_chat(): stream responses incrementally
    - stop(): terminate any running process
    """

    def __init__(self, cwd: Optional[str] = None, timeout: int = 300):
        self.cwd = cwd or subprocess.run(
            "pwd", shell=True, capture_output=True, text=True
        ).stdout.strip()
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._status = AdapterStatus.IDLE
        self._start_time: Optional[float] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the adapter name."""
        pass

    @property
    def status(self) -> AdapterStatus:
        return self._status

    @property
    def uptime(self) -> float:
        """Return seconds since adapter was started."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @abstractmethod
    def chat(self, message: str, **kwargs) -> AgentResponse:
        """
        Send a message to the agent and wait for a complete response.
        
        Args:
            message: The user message to send
            **kwargs: Adapter-specific options
            
        Returns:
            AgentResponse with content and/or tool calls
        """
        pass

    @abstractmethod
    def stream_chat(self, message: str, **kwargs) -> Iterator[str]:
        """
        Send a message and yield response tokens incrementally.
        
        Args:
            message: The user message to send
            **kwargs: Adapter-specific options
            
        Yields:
            String tokens as they arrive
        """
        pass

    @abstractmethod
    def stop(self):
        """Terminate any running process."""
        pass

    def _set_status(self, status: AdapterStatus):
        self._status = status
        if status == AdapterStatus.RUNNING and self._start_time is None:
            self._start_time = time.time()
        elif status == AdapterStatus.IDLE:
            self._start_time = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name!r}, status={self._status.value})>"
