#!/usr/bin/env python3
"""
h_agent/team/protocol.py - Agent Team Communication Protocol

定义 agent 间通信的协议和数据格式。
支持:
- 同步 RPC 风格调用
- 异步消息队列风格
- 广播/多播
"""

import json
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from pathlib import Path


# ============================================================
# Protocol Types
# ============================================================

class MessageType(Enum):
    TASK = "task"            # 分发任务
    RESULT = "result"        # 返回结果
    QUERY = "query"          # 查询请求
    RESPONSE = "response"    # 查询响应
    BROADCAST = "broadcast"  # 广播
    HEARTBEAT = "heartbeat"  # 心跳
    ERROR = "error"          # 错误通知
    APPROVAL = "approval"    # 需要审批
    SIGNAL = "signal"        # 信号量/同步


@dataclass
class TaskSpec:
    """
    任务规格说明 - 团队通信的标准任务格式。
    
    设计参考:
    - 每个任务有唯一 ID
    - 支持父子任务关系（任务树）
    - 支持优先级和截止时间
    - 任务状态跟踪
    """
    task_id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    parent_id: Optional[str] = None       # 父任务 ID（支持任务树）
    title: str = ""
    description: str = ""
    assigned_to: Optional[str] = None     # agent 名称
    role: Optional[str] = None            # 或指定角色
    priority: int = 0                     # 优先级（越高越优先）
    deadline: Optional[str] = None        # ISO 时间戳
    subtasks: List["TaskSpec"] = field(default_factory=list)
    status: str = "pending"               # pending/running/done/failed/blocked
    result: Any = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = field(default_factory= lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["subtasks"] = [s.to_dict() if isinstance(s, TaskSpec) else s for s in self.subtasks]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSpec":
        if "subtasks" in d:
            d["subtasks"] = [cls.from_dict(s) if isinstance(s, dict) else s for s in d["subtasks"]]
        return cls(**d)


@dataclass
class ProtocolMessage:
    """
    标准协议消息格式。
    所有 agent 间通信都使用这个格式。
    """
    id: str = field(default_factory=lambda: f"pm-{uuid.uuid4().hex[:8]}")
    type: MessageType = MessageType.TASK
    sender: str = "unknown"
    receivers: List[str] = field(default_factory=list)  # 空=广播
    session_id: Optional[str] = None
    task: Optional[TaskSpec] = None
    payload: Any = None
    ref_id: Optional[str] = None    # 关联消息 ID
    correlation_id: Optional[str] = None  # 用于关联请求/响应
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    ttl: int = 3600                  # 生存时间（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "ProtocolMessage":
        if "type" in d and isinstance(d["type"], str):
            d["type"] = MessageType(d["type"])
        if "task" in d and d["task"]:
            d["task"] = TaskSpec.from_dict(d["task"]) if isinstance(d["task"], dict) else d["task"]
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "ProtocolMessage":
        return cls.from_dict(json.loads(s))

    def is_expired(self) -> bool:
        """检查消息是否过期。"""
        try:
            msg_time = time.mktime(time.strptime(self.timestamp, "%Y-%m-%dT%H:%M:%S"))
            return (time.time() - msg_time) > self.ttl
        except (ValueError, OSError):
            return False


# ============================================================
# Message Bus (In-Memory + File persistence)
# ============================================================

PROTOCOL_DIR = Path.home() / ".h-agent" / "protocol"
PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)


class TeamProtocol:
    """
    Agent 通信协议实现。
    支持同步 RPC 和异步消息两种模式。
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.inbox: List[ProtocolMessage] = []
        self.outbox: List[ProtocolMessage] = []
        self.pending_replies: Dict[str, ProtocolMessage] = {}  # correlation_id -> original request
        self._inbox_file = PROTOCOL_DIR / f"inbox_{agent_name}.jsonl"
        self._outbox_file = PROTOCOL_DIR / f"outbox_{agent_name}.jsonl"

    # ---- Message Construction ----

    def new_task(
        self,
        title: str,
        description: str = "",
        assigned_to: str = None,
        role: str = None,
        parent_id: str = None,
        priority: int = 0,
        tags: List[str] = None,
    ) -> ProtocolMessage:
        """构造一个新任务消息。"""
        task = TaskSpec(
            title=title,
            description=description,
            assigned_to=assigned_to,
            role=role,
            parent_id=parent_id,
            priority=priority,
            tags=tags or [],
        )
        return ProtocolMessage(
            type=MessageType.TASK,
            sender=self.agent_name,
            task=task,
        )

    def new_query(
        self,
        query: str,
        target: str,
        correlation_id: str = None,
    ) -> ProtocolMessage:
        """构造一个查询消息。"""
        cid = correlation_id or f"q-{uuid.uuid4().hex[:8]}"
        return ProtocolMessage(
            type=MessageType.QUERY,
            sender=self.agent_name,
            receivers=[target],
            payload=query,
            correlation_id=cid,
        )

    def new_broadcast(
        self,
        payload: Any,
        msg_type: MessageType = MessageType.BROADCAST,
    ) -> ProtocolMessage:
        """构造一个广播消息。"""
        return ProtocolMessage(
            type=msg_type,
            sender=self.agent_name,
            receivers=[],  # 空 = 广播
            payload=payload,
        )

    # ---- Send / Receive ----

    def send(self, msg: ProtocolMessage, target: str = None) -> str:
        """
        发送消息（写入 outbox 文件）。
        target 指定时同时写入目标 inbox。
        """
        self.outbox.append(msg)
        msg_id = msg.id

        # 持久化 outbox
        try:
            with open(self._outbox_file, "a", encoding="utf-8") as f:
                f.write(msg.to_json() + "\n")
        except OSError:
            pass

        # 如果指定了目标，写入目标 inbox
        if target:
            target_inbox = PROTOCOL_DIR / f"inbox_{target}.jsonl"
            try:
                with open(target_inbox, "a", encoding="utf-8") as f:
                    f.write(msg.to_json() + "\n")
            except OSError:
                pass

        return msg_id

    def receive(self) -> List[ProtocolMessage]:
        """接收所有未读消息。"""
        self.inbox.clear()
        try:
            if self._inbox_file.exists():
                messages = []
                with open(self._inbox_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = ProtocolMessage.from_json(line)
                            if not msg.is_expired():
                                messages.append(msg)
                            else:
                                # 过期的跳过并记录
                                pass
                        except Exception:
                            pass

                # 归档已读消息
                archive_file = PROTOCOL_DIR / f"archive_{self.agent_name}.jsonl"
                with open(self._inbox_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.strip():
                    with open(archive_file, "a", encoding="utf-8") as f:
                        f.write(content)
                self._inbox_file.unlink()

                self.inbox = messages
        except OSError:
            pass

        return self.inbox

    def reply_to(self, original: ProtocolMessage, payload: Any, msg_type: MessageType = None) -> ProtocolMessage:
        """回复一个消息。"""
        reply_type = msg_type or MessageType.RESPONSE
        reply = ProtocolMessage(
            type=reply_type,
            sender=self.agent_name,
            receivers=[original.sender],
            payload=payload,
            ref_id=original.id,
            correlation_id=original.correlation_id,
        )
        return reply

    def await_reply(self, correlation_id: str, timeout: float = 30) -> Optional[ProtocolMessage]:
        """等待特定 correlation_id 的回复（同步 RPC 风格）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.receive()
            for msg in self.inbox:
                if msg.correlation_id == correlation_id and msg.sender != self.agent_name:
                    return msg
            time.sleep(0.5)
        return None

    # ---- Inbox Filtering ----

    def get_tasks(self) -> List[ProtocolMessage]:
        return [m for m in self.inbox if m.type == MessageType.TASK]

    def get_queries(self) -> List[ProtocolMessage]:
        return [m for m in self.inbox if m.type == MessageType.QUERY]

    def get_broadcasts(self) -> List[ProtocolMessage]:
        return [m for m in self.inbox if m.type == MessageType.BROADCAST]

    def clear_inbox(self):
        """清空内存中的 inbox。"""
        self.inbox.clear()


# ============================================================
# Convenience Factory
# ============================================================

def new_task_message(
    title: str,
    description: str = "",
    assigned_to: str = None,
    role: str = None,
    priority: int = 0,
) -> ProtocolMessage:
    """快速创建任务消息。"""
    msg = ProtocolMessage(type=MessageType.TASK)
    msg.task = TaskSpec(
        title=title,
        description=description,
        assigned_to=assigned_to,
        role=role,
        priority=priority,
    )
    return msg


def parse_task_tree(messages: List[ProtocolMessage]) -> Dict[str, TaskSpec]:
    """解析任务树（从消息列表中构建）。"""
    tasks: Dict[str, TaskSpec] = {}
    for msg in messages:
        if msg.task:
            tasks[msg.task.task_id] = msg.task

    # 构建父子关系
    for task in tasks.values():
        if task.parent_id and task.parent_id in tasks:
            parent = tasks[task.parent_id]
            if task not in parent.subtasks:
                parent.subtasks.append(task)

    return tasks
