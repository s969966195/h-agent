#!/usr/bin/env python3
"""
h_agent/team/agent.py - Full-Featured Team Agent

每个 Team Agent 拥有与单 Agent 相同的能力：
- IDENTITY/SOUL/USER.md 配置文件
- 独立的 SessionStore（会话历史）
- ContextGuard（溢出保护）
- RAG（代码检索）
- Skills（技能系统）
- Tool Calling（工具调用）
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator, Iterator
from dataclasses import dataclass, field

from h_agent.core.client import get_client
from h_agent.core.config import MODEL
from h_agent.features.sessions import (
    SessionStore,
    ContextGuard,
    TOOLS as CORE_TOOLS,
    TOOL_HANDLERS as CORE_HANDLERS,
    execute_tool_call,
)
from h_agent.memory.long_term import LongTermMemory
from h_agent.features.rag import CodebaseRAG

AGENTS_DIR = Path.home() / ".h-agent" / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class AgentProfile:
    """Agent 配置文件夹。"""
    name: str
    dir_path: Path
    
    @property
    def identity_path(self) -> Path:
        return self.dir_path / "IDENTITY.md"
    
    @property
    def soul_path(self) -> Path:
        return self.dir_path / "SOUL.md"
    
    @property
    def user_path(self) -> Path:
        return self.dir_path / "USER.md"
    
    @property
    def memory_path(self) -> Path:
        return self.dir_path / "memory.json"
    
    @property
    def config_path(self) -> Path:
        return self.dir_path / "config.json"
    
    def exists(self) -> bool:
        return self.dir_path.exists() and self.dir_path.is_dir()
    
    def create_default(self) -> None:
        """创建默认配置文件夹。"""
        self.dir_path.mkdir(parents=True, exist_ok=True)
        
        if not self.identity_path.exists():
            self.identity_path.write_text(f"""# {self.name} - IDENTITY

## 名字
{self.name}

## 角色
（在这里描述角色的基本信息）

## 性格特点
（描述这个 Agent 的性格：严谨/活泼/专业等）

## 专业领域
（描述这个 Agent 擅长的领域）
""")
        
        if not self.soul_path.exists():
            self.soul_path.write_text("""# SOUL - 行为准则

## 工作原则
1. （描述首要工作原则）
2. （描述次要工作原则）
3. （描述决策方式）

## 协作方式
（描述如何与其他 Agent 协作）

## 质量标准
（描述对工作质量的期望）
""")
        
        if not self.user_path.exists():
            self.user_path.write_text("""# USER - 用户信息

## 用户偏好
（在这里记录用户的偏好，会自动同步）

## 项目上下文
（记录当前项目的背景信息）

## 重要上下文
（记录重要的对话上下文）
""")
        
        if not self.config_path.exists():
            self.config_path.write_text(json.dumps({
                "name": self.name,
                "role": "coordinator",
                "enabled": True,
                "tools": [],
                "skills": [],
            }, indent=2, ensure_ascii=False))

class AgentLoader:
    """加载 Agent 配置。"""
    
    @staticmethod
    def get_profile(name: str) -> AgentProfile:
        """获取 Agent 配置。"""
        return AgentProfile(name=name, dir_path=AGENTS_DIR / name)
    
    @staticmethod
    def load_profile(name: str) -> Optional[AgentProfile]:
        """加载 Agent 配置（如果存在）。"""
        profile = AgentProfile(name=name, dir_path=AGENTS_DIR / name)
        if profile.exists():
            return profile
        return None
    
    @staticmethod
    def list_profiles() -> List[str]:
        """列出所有 Agent 配置。"""
        if not AGENTS_DIR.exists():
            return []
        return [d.name for d in AGENTS_DIR.iterdir() if d.is_dir()]
    
    @staticmethod
    def build_system_prompt(profile: AgentProfile, extra_context: str = "") -> str:
        """从 IDENTITY/SOUL/USER.md 构建完整 system prompt。"""
        parts = []
        
        identity = ""
        if profile.identity_path.exists():
            identity = profile.identity_path.read_text(encoding="utf-8")
        parts.append(f"=== IDENTITY ===\n{identity}")
        
        soul = ""
        if profile.soul_path.exists():
            soul = profile.soul_path.read_text(encoding="utf-8")
        parts.append(f"=== SOUL (行为准则) ===\n{soul}")
        
        user_info = ""
        if profile.user_path.exists():
            user_info = profile.user_path.read_text(encoding="utf-8")
        parts.append(f"=== USER INFO ===\n{user_info}")
        
        if extra_context:
            parts.append(f"=== CURRENT CONTEXT ===\n{extra_context}")
        
        return "\n\n".join(parts)
    
    @staticmethod
    def load_config(profile: AgentProfile) -> Dict[str, Any]:
        """加载 Agent 配置。"""
        if profile.config_path.exists():
            return json.loads(profile.config_path.read_text(encoding="utf-8"))
        return {"name": profile.name, "role": "coordinator", "enabled": True, "tools": [], "skills": []}
    
    @staticmethod
    def save_config(profile: AgentProfile, config: Dict[str, Any]) -> None:
        """保存 Agent 配置。"""
        profile.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


class AgentSessionManager:
    """管理 Agent 的会话和上下文。"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.session_store = SessionStore(agent_name)
        self.context_guard = ContextGuard()
        self.long_term_memory = LongTermMemory()
        
        self._ensure_session()
    
    def _ensure_session(self) -> None:
        """确保有当前会话。"""
        if not self.session_store.current_session_id:
            self.session_store.create_session()
    
    def load_history(self) -> List[dict]:
        """加载会话历史。"""
        return self.session_store.load_session()
    
    def save_interaction(self, user_msg: str, assistant_msg: str, tool_calls: List[dict] = None) -> None:
        """保存一轮交互。"""
        self.session_store.save_turn("user", user_msg)
        self.session_store.save_turn("assistant", assistant_msg)
        if tool_calls:
            for tc in tool_calls:
                self.session_store.save_turn("tool", str(tc), session_id=self.session_store.current_session_id)
    
    def get_context(self, messages: List[dict]) -> List[dict]:
        """获取受保护的上下文（溢出处理）。"""
        messages, compact_level = self.context_guard.guard_api_call(messages)
        return messages, compact_level
    
    def remember(self, content: str, memory_type: str = "fact", importance: int = 7) -> None:
        """存入长期记忆。"""
        self.long_term_memory.add(content=content, memory_type=memory_type, importance=importance)
    
    def recall(self, query: str, limit: int = 5) -> List[dict]:
        """从长期记忆检索。"""
        return self.long_term_memory.search(query, limit=limit)
    
    def get_or_create_session_id(self) -> str:
        """获取或创建会话 ID。"""
        self._ensure_session()
        return self.session_store.current_session_id


def execute_tool_call_with_handlers(tool_call, tool_handlers: Dict[str, callable]) -> str:
    """执行工具调用。"""
    args = json.loads(tool_call.function.arguments)
    name = tool_call.function.name
    if name in tool_handlers:
        return tool_handlers[name](**args)
    return f"Error: Unknown tool '{name}'"


class FullAgentHandler:
    """
    完整的 Agent Handler。
    
    具备：
    - IDENTITY/SOUL/USER.md 配置
    - SessionStore 会话历史
    - ContextGuard 溢出保护
    - LongTermMemory 长期记忆
    - Tool Calling 工具调用
    - RAG 代码检索
    """
    
    def __init__(
        self,
        agent_name: str,
        profile: Optional[AgentProfile] = None,
        extra_tools: List[dict] = None,
        extra_handlers: Dict[str, callable] = None,
        workspace_dir: str = None,
    ):
        self.agent_name = agent_name
        self.profile = profile or AgentLoader.get_profile(agent_name)
        self.session_mgr = AgentSessionManager(agent_name)
        
        self.tools = list(CORE_TOOLS)
        if extra_tools:
            self.tools.extend(extra_tools)
        
        self.tool_handlers = dict(CORE_HANDLERS)
        if extra_handlers:
            self.tool_handlers.update(extra_handlers)
        
        self.workspace_dir = Path(workspace_dir) if workspace_dir else None
        self.client = get_client()
    
    def build_messages(self, task_content: str) -> List[dict]:
        """构建发送给 LLM 的消息列表。"""
        messages = self.session_mgr.load_history()
        
        context, compact_level = self.session_mgr.get_context(messages)
        
        extra_context = ""
        if compact_level > 0:
            extra_context += f"\n[注意：上下文已被压缩，级别 {compact_level}]"
        
        system_prompt = AgentLoader.build_system_prompt(self.profile, extra_context)
        
        result_messages = [{"role": "system", "content": system_prompt}]
        result_messages.extend(context)
        result_messages.append({"role": "user", "content": str(task_content)})
        
        return result_messages
    
    def run(self, task_content: str, max_turns: int = 20) -> dict:
        """
        运行 Agent 处理任务。
        
        Returns:
            dict with keys: success, content, turns, error
        """
        try:
            messages = self.build_messages(task_content)
            
            for turn in range(max_turns):
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    max_tokens=4096,
                )
                
                assistant_msg = response.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content,
                    "tool_calls": getattr(assistant_msg, "tool_calls", None),
                })
                
                if not assistant_msg.tool_calls:
                    self.session_mgr.save_interaction(task_content, assistant_msg.content or "")
                    return {
                        "success": True,
                        "content": assistant_msg.content or "",
                        "turns": turn + 1,
                        "error": None,
                    }
                
                tool_results = []
                for tc in assistant_msg.tool_calls:
                    result = execute_tool_call_with_handlers(tc, self.tool_handlers)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                    tool_results.append({"name": tc.function.name, "result": result})
                
                self.session_mgr.save_interaction(
                    task_content,
                    str(assistant_msg.tool_calls),
                    tool_results,
                )
            
            return {
                "success": False,
                "content": None,
                "turns": max_turns,
                "error": f"Max turns ({max_turns}) exceeded",
            }
            
        except Exception as e:
            return {
                "success": False,
                "content": None,
                "turns": 0,
                "error": str(e),
            }
    
    def chat(self, message: str) -> str:
        """简化的对话接口。"""
        result = self.run(message, max_turns=10)
        if result["success"]:
            return result["content"]
        return f"Error: {result['error']}"
    
    def run_streaming(self, task_content: str, session_id: str = None, max_turns: int = 20) -> Generator[dict, None, None]:
        """
        运行 Agent 并以 SSE 事件流式输出。
        
        Yields:
            dict with keys: event (str), data (dict)
            - event: "token" | "tool_start" | "tool_end" | "error" | "end"
            - data: event-specific payload
        """
        # Set session if provided
        if session_id:
            self.session_mgr.session_store.current_session_id = session_id
        
        try:
            messages = self.build_messages(task_content)
            
            for turn in range(max_turns):
                # Stream the response
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    max_tokens=4096,
                    stream=True,
                )
                
                # Collect assistant message content and tool calls
                assistant_content = ""
                tool_calls = []
                
                for chunk in response:
                    delta = chunk.choices[0].delta
                    
                    # Stream content tokens
                    if delta.content:
                        assistant_content += delta.content
                        yield {
                            "event": "token",
                            "data": {"token": delta.content}
                        }
                    
                    # Collect tool calls
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            if len(tool_calls) <= tc.index:
                                tool_calls.append({
                                    "id": "",
                                    "function": {"name": "", "arguments": ""}
                                })
                            if tc.id:
                                tool_calls[tc.index]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls[tc.index]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
                
                # Process tool calls if any
                if tool_calls:
                    # Save the assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                        "tool_calls": [
                            {"id": tc["id"], "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                            for tc in tool_calls
                        ],
                    })
                    
                    tool_results = []
                    for tc in tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        
                        # Emit tool_start
                        try:
                            args_dict = json.loads(func_args)
                        except:
                            args_dict = {}
                        
                        yield {
                            "event": "tool_start",
                            "data": {"name": func_name, "args": str(args_dict)[:200]}
                        }
                        
                        # Execute tool
                        result = execute_tool_call_with_handlers(
                            type('obj', (object,), {"function": type('obj', (object,), {"name": func_name, "arguments": func_args})()})(),
                            self.tool_handlers
                        )
                        
                        # Truncate long results
                        if len(result) > 50000:
                            result = result[:25000] + "\n...[truncated]\n" + result[-25000:]
                        
                        # Emit tool_end
                        yield {
                            "event": "tool_end",
                            "data": {"name": func_name, "result": result[:500]}
                        }
                        
                        tool_results.append({"name": func_name, "result": result})
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                    
                    # Save interaction with tool calls
                    self.session_mgr.save_interaction(
                        task_content,
                        str([{"name": tc["function"]["name"]} for tc in tool_calls]),
                        tool_results,
                    )
                else:
                    # No tool calls - normal response
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })
                    self.session_mgr.save_interaction(task_content, assistant_content)
                    yield {"event": "end", "data": {"done": True}}
                    return
            
            # Max turns exceeded
            yield {"event": "error", "data": {"error": f"Max turns ({max_turns}) exceeded"}}
            yield {"event": "end", "data": {"done": True}}
            
        except Exception as e:
            yield {"event": "error", "data": {"error": str(e)}}
            yield {"event": "end", "data": {"done": True}}


def create_full_handler(
    agent_name: str,
    profile: AgentProfile = None,
    extra_tools: List[dict] = None,
    extra_handlers: Dict[str, callable] = None,
) -> callable:
    """工厂函数：创建完整的 Agent Handler。"""
    
    handler = FullAgentHandler(
        agent_name=agent_name,
        profile=profile,
        extra_tools=extra_tools,
        extra_handlers=extra_handlers,
    )
    
    def handle_message(msg) -> dict:
        from h_agent.team.team import TaskResult, AgentRole
        from h_agent.core.config import MODEL
        
        try:
            result = handler.run(str(msg.content), max_turns=20)
            
            return TaskResult(
                agent_name=agent_name,
                role=AgentRole.COORDINATOR,
                success=result["success"],
                content=result["content"],
                error=result["error"],
                duration_ms=0,
            )
        except Exception as e:
            return TaskResult(
                agent_name=agent_name,
                role=AgentRole.COORDINATOR,
                success=False,
                content=None,
                error=str(e),
                duration_ms=0,
            )
    
    return handle_message


def init_agent_profile(name: str, role: str = "coordinator", description: str = "") -> AgentProfile:
    """
    初始化 Agent 配置。
    
    创建 ~/.h-agent/agents/{name}/ 目录及 IDENTITY/SOUL/USER.md 文件。
    """
    profile = AgentProfile(name=name, dir_path=AGENTS_DIR / name)
    profile.create_default()
    
    config = AgentLoader.load_config(profile)
    config["role"] = role
    config["description"] = description or f"{name} Agent"
    AgentLoader.save_config(profile, config)
    
    return profile


def list_team_agents() -> List[dict]:
    """列出所有已配置的 Agent。"""
    agents = []
    for name in AgentLoader.list_profiles():
        profile = AgentLoader.get_profile(name)
        config = AgentLoader.load_config(profile)
        agents.append({
            "name": name,
            "role": config.get("role", "unknown"),
            "description": config.get("description", ""),
            "enabled": config.get("enabled", True),
        })
    return agents
