#!/usr/bin/env python3
"""
h_agent/features/sessions.py - Sessions & Context Protection (OpenAI Version)

会话是 JSONL 文件。写入时追加，读取时重放。过大时进行摘要压缩。

核心组件:
  SessionStore -- JSONL 持久化
  ContextGuard -- 三阶段溢出重试

用户输入 -> load_session() -> guard_api_call() -> save_turn() -> 打印响应
"""

import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field, asdict

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "sk-dummy"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
MODEL = os.getenv("MODEL_ID", "gpt-4o")

WORKSPACE_DIR = Path.cwd() / ".agent_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

CONTEXT_SAFE_LIMIT = 180000  # tokens
MAX_TOOL_OUTPUT = 50000

# ============================================================
# Session Store - JSONL 持久化
# ============================================================

@dataclass
class SessionMeta:
    session_id: str
    agent_id: str
    created_at: str
    updated_at: str
    message_count: int = 0
    token_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


class SessionStore:
    """管理 agent 会话的 JSONL 持久化存储。"""
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.base_dir = WORKSPACE_DIR / "sessions" / agent_id
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "index.json"
        self._index: Dict[str, dict] = self._load_index()
        self.current_session_id: Optional[str] = None
    
    def _load_index(self) -> Dict[str, dict]:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}
    
    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def _session_path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.jsonl"
    
    def create_session(self) -> str:
        """创建新会话，返回 session_id。"""
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        self._index[session_id] = SessionMeta(
            session_id=session_id,
            agent_id=self.agent_id,
            created_at=now,
            updated_at=now,
        ).to_dict()
        self._save_index()
        
        # 创建空的 JSONL 文件
        self._session_path(session_id).touch()
        
        self.current_session_id = session_id
        return session_id
    
    def load_session(self, session_id: str = None) -> List[dict]:
        """加载会话，返回 messages 列表。"""
        if session_id is None:
            session_id = self.current_session_id
        
        if not session_id or session_id not in self._index:
            return []
        
        messages = []
        session_file = self._session_path(session_id)
        
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        
        return messages
    
    def save_turn(self, role: str, content: Any, session_id: str = None) -> None:
        """保存一轮对话到 JSONL。"""
        if session_id is None:
            session_id = self.current_session_id
        
        if not session_id:
            session_id = self.create_session()
        
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        
        # 追加到 JSONL
        session_file = self._session_path(session_id)
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn, ensure_ascii=False) + "\n")
        
        # 更新索引
        if session_id in self._index:
            meta = self._index[session_id]
            meta["message_count"] = meta.get("message_count", 0) + 1
            meta["updated_at"] = datetime.now().isoformat()
            self._save_index()
    
    def get_recent_sessions(self, limit: int = 10) -> List[dict]:
        """获取最近的会话列表。"""
        sessions = sorted(
            self._index.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
        return sessions[:limit]
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话。"""
        if session_id not in self._index:
            return False
        
        session_file = self._session_path(session_id)
        if session_file.exists():
            session_file.unlink()
        
        del self._index[session_id]
        self._save_index()
        return True


# ============================================================
# Context Guard - 溢出保护
# ============================================================

class ContextGuard:
    """
    三阶段上下文溢出处理:
    1. 正常调用
    2. 截断工具结果
    3. 压缩历史 (50%)
    """
    
    def __init__(self, safe_limit: int = CONTEXT_SAFE_LIMIT):
        self.safe_limit = safe_limit
    
    def estimate_tokens(self, messages: List[dict]) -> int:
        """估算 token 数量（粗略：1 token ≈ 4 字符）。"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += len(str(block))
                    else:
                        total += len(str(block))
        return total // 4
    
    def should_compact(self, messages: List[dict]) -> bool:
        """检查是否需要压缩。"""
        return self.estimate_tokens(messages) > self.safe_limit
    
    def truncate_tool_results(self, messages: List[dict], max_len: int = MAX_TOOL_OUTPUT) -> List[dict]:
        """截断工具结果（第一阶段压缩）。"""
        result = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > max_len:
                    half = max_len // 2
                    msg = {
                        **msg,
                        "content": content[:half] + f"\n... [truncated {len(content) - max_len} chars]\n" + content[-half:]
                    }
            result.append(msg)
        return result
    
    def compact_messages(self, messages: List[dict]) -> List[dict]:
        """压缩历史消息（第二阶段压缩）。"""
        if len(messages) <= 4:
            return messages
        
        # 保留系统消息和最近的消息
        system_msgs = [m for m in messages if m.get("role") == "system"]
        recent_msgs = messages[-4:]  # 保留最近的 4 条
        
        # 对中间的消息生成摘要
        middle_msgs = messages[:-4]
        if middle_msgs:
            summary = self._generate_summary(middle_msgs)
            if summary:
                summary_msg = {
                    "role": "system",
                    "content": f"[Previous context summary]\n{summary}"
                }
                return system_msgs + [summary_msg] + recent_msgs
        
        return system_msgs + recent_msgs
    
    def _generate_summary(self, messages: List[dict]) -> Optional[str]:
        """Generate LLM-powered summary of messages (replaces naive user-message extraction)."""
        try:
            from h_agent.memory.summarizer import SmartSummarizer
            summarizer = SmartSummarizer()
            return summarizer.summarize(messages)
        except Exception:
            # Fallback: extract user messages only
            user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
            if user_msgs:
                return "User asked: " + "; ".join(user_msgs[-3:])
            return None
    
    def guard_api_call(self, messages: List[dict]) -> tuple:
        """
        保护 API 调用，返回 (处理后的消息, 压缩级别)。
        
        压缩级别:
          0 - 无压缩
          1 - 截断工具结果
          2 - 压缩历史
        """
        if not self.should_compact(messages):
            return messages, 0
        
        # 第一阶段：截断工具结果
        messages = self.truncate_tool_results(messages)
        if not self.should_compact(messages):
            return messages, 1
        
        # 第二阶段：压缩历史
        messages = self.compact_messages(messages)
        return messages, 2


# ============================================================
# Tools
# ============================================================

import subprocess

def tool_bash(command: str) -> str:
    try:
        r = subprocess.run(command, shell=True, cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=60)
        output = (r.stdout + r.stderr).strip()
        return output[:MAX_TOOL_OUTPUT] if output else "(no output)"
    except Exception as e:
        return f"Error: {e}"

def tool_read(file_path: str) -> str:
    try:
        path = WORKSPACE_DIR / file_path
        if not path.exists():
            return f"Error: File not found"
        return path.read_text()[:MAX_TOOL_OUTPUT]
    except Exception as e:
        return f"Error: {e}"

def tool_write(file_path: str, content: str) -> str:
    try:
        path = WORKSPACE_DIR / file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Wrote {len(content)} chars"
    except Exception as e:
        return f"Error: {e}"

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "Run shell command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read", "description": "Read file",
        "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
    {"type": "function", "function": {"name": "write", "description": "Write file",
        "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}}},
]

TOOL_HANDLERS = {"bash": tool_bash, "read": tool_read, "write": tool_write}


def execute_tool_call(tool_call) -> str:
    args = json.loads(tool_call.function.arguments)
    return TOOL_HANDLERS[tool_call.function.name](**args)


# ============================================================
# Agent Loop with Sessions
# ============================================================

class SessionAwareAgent:
    """带会话持久化的 Agent。"""
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.session_store = SessionStore(agent_id)
        self.context_guard = ContextGuard()
    
    def get_system_prompt(self) -> str:
        return f"You are a helpful AI assistant at {WORKSPACE_DIR}. Use tools to help the user."
    
    def run(self, user_input: str, session_id: str = None) -> str:
        """运行一轮对话。"""
        # 加载或创建会话
        if session_id:
            self.session_store.current_session_id = session_id
        elif not self.session_store.current_session_id:
            self.session_store.create_session()
        
        # 加载历史消息
        messages = self.session_store.load_session()
        
        # 添加用户消息
        messages.append({"role": "user", "content": user_input})
        
        # 保护上下文
        messages, compact_level = self.context_guard.guard_api_call(messages)
        if compact_level > 0:
            print(f"\033[33m[Context compacted: level {compact_level}]\033[0m")
        
        # 添加系统提示
        messages = [{"role": "system", "content": self.get_system_prompt()}] + messages
        
        # Agent 循环
        while True:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )
            
            message = response.choices[0].message
            messages.append({"role": "assistant", "content": message.content, "tool_calls": message.tool_calls})
            
            if not message.tool_calls:
                # 保存并返回
                self.session_store.save_turn("user", user_input)
                self.session_store.save_turn("assistant", message.content)
                return message.content or ""
            
            # 执行工具
            for tool_call in message.tool_calls:
                result = execute_tool_call(tool_call)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    
    def list_sessions(self) -> List[dict]:
        """列出会话。"""
        return self.session_store.get_recent_sessions()
    
    def switch_session(self, session_id: str) -> bool:
        """切换会话。"""
        if session_id in self.session_store._index:
            self.session_store.current_session_id = session_id
            return True
        return False
    
    def new_session(self) -> str:
        """创建新会话。"""
        return self.session_store.create_session()


def main():
    print(f"\033[36mOpenAI Agent Harness - c03 (Sessions)\033[0m")
    print(f"Model: {MODEL}")
    print(f"Workspace: {WORKSPACE_DIR}")
    print("\nCommands: 'sessions' to list, 'new' for new session, 'switch <id>' to switch")
    print("Type 'quit' to exit\n")
    
    agent = SessionAwareAgent()
    
    while True:
        try:
            user_input = input("\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not user_input:
            continue
        
        if user_input.lower() == "quit":
            break
        
        if user_input.lower() == "sessions":
            sessions = agent.list_sessions()
            for s in sessions:
                print(f"  {s['session_id']}: {s['message_count']} msgs, updated {s['updated_at'][:19]}")
            continue
        
        if user_input.lower() == "new":
            session_id = agent.new_session()
            print(f"Created session: {session_id}")
            continue
        
        if user_input.lower().startswith("switch "):
            session_id = user_input[7:].strip()
            if agent.switch_session(session_id):
                print(f"Switched to: {session_id}")
            else:
                print(f"Session not found: {session_id}")
            continue
        
        # 正常对话
        response = agent.run(user_input)
        print(f"\n{response}\n")


if __name__ == "__main__":
    main()
