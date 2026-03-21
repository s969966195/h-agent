#!/usr/bin/env python3
"""
h_agent/team/team.py - Agent Team Core

团队协作机制:
1. 注册多个 agent 角色（planner/coder/reviewer/devops）
2. 任务广播给相关 agent
3. 收集汇总各 agent 结果
4. 支持同步/异步两种分发模式
"""

import json
import uuid
import time
import asyncio
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path

TEAM_DIR = Path.home() / ".h-agent" / "team"
TEAM_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Agent Roles
# ============================================================

class AgentRole(Enum):
    PLANNER = "planner"       # 任务规划、分解
    CODER = "coder"           # 编码实现
    REVIEWER = "reviewer"     # 代码审查
    DEVOPS = "devops"         # 部署运维
    RESEARCHER = "researcher" # 调研分析
    COORDINATOR = "coordinator"  # 任务协调（主控）


# ============================================================
# Team Message Protocol
# ============================================================

@dataclass
class TeamMessage:
    """Agent 间通信消息。"""
    msg_id: str
    sender: str           # agent name
    receiver: str         # agent name or "*" for broadcast
    role: AgentRole       # sender's role
    type: str             # "task" | "result" | "query" | "response" | "broadcast"
    content: Any          # 消息内容
    ref_msg_id: Optional[str] = None  # 回复的消息 ID
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TeamMessage":
        d["role"] = AgentRole(d["role"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "TeamMessage":
        return cls.from_dict(json.loads(s))


@dataclass
class TaskResult:
    """单个 agent 的任务结果。"""
    agent_name: str
    role: AgentRole
    success: bool
    content: Any
    error: Optional[str] = None
    duration_ms: int = 0
    ref_task_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        return d


# ============================================================
# Agent Member
# ============================================================

@dataclass
class AgentMember:
    """团队成员 agent。"""
    name: str
    role: AgentRole
    description: str = ""
    system_prompt: str = ""
    enabled: bool = True
    tools: List[Dict] = field(default_factory=list)
    # Per-agent session ID for memory isolation
    session_id: Optional[str] = None
    # Adapter reference for cached instances (used by adapter-based members)
    _adapter_instance: Any = field(default=None, repr=False)
    # 通信回调
    _handle_message: Optional[Callable[["TeamMessage"], "TaskResult"]] = field(default=None, repr=False)
    # 原始 prompt（用于从状态恢复时重建 handler）
    _prompt: str = field(default="", repr=False)

    def handle_message(self, msg: TeamMessage) -> TaskResult:
        """处理收到的消息。"""
        if self._handle_message:
            return self._handle_message(msg)
        return TaskResult(
            agent_name=self.name,
            role=self.role,
            success=False,
            content=None,
            error=(
                f"Agent '{self.name}' has no active handler. "
                f"Run 'h-agent team init' to re-initialize agents with live handlers."
            ),
        )

    def set_handler(self, handler: Callable[[TeamMessage], TaskResult]):
        self._handle_message = handler

    def set_adapter_instance(self, adapter: Any):
        """Set the cached adapter instance for this member."""
        self._adapter_instance = adapter

    def get_adapter_instance(self) -> Any:
        """Get the cached adapter instance for this member."""
        return self._adapter_instance


# ============================================================
# Team Message Bus (IPC via files)
# ============================================================

class MessageBus:
    """
    基于文件的 IPC 消息总线。
    支持单机多 agent 进程通过文件系统通信。
    """
    INBOX_DIR = TEAM_DIR / "inbox"
    OUTBOX_DIR = TEAM_DIR / "outbox"
    ARCHIVE_DIR = TEAM_DIR / "archive"

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.inbox_dir = self.INBOX_DIR / agent_name
        self.outbox_dir = self.OUTBOX_DIR / agent_name
        for d in [self.inbox_dir, self.outbox_dir, self.ARCHIVE_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def post(self, msg: TeamMessage) -> str:
        """发送消息到接收者的 inbox。"""
        path = self.outbox_dir / f"{msg.msg_id}.json"
        path.write_text(msg.to_json(), encoding="utf-8")

        # 也写入接收者的 inbox（如果是同机器）
        if msg.receiver != "*":
            recv_inbox = self.INBOX_DIR / msg.receiver / f"{msg.msg_id}.json"
            recv_inbox.parent.mkdir(parents=True, exist_ok=True)
            recv_inbox.write_text(msg.to_json(), encoding="utf-8")

        return msg.msg_id

    def receive_all(self) -> List[TeamMessage]:
        """接收所有待处理消息。"""
        messages = []
        for path in sorted(self.inbox_dir.glob("*.json")):
            try:
                msg = TeamMessage.from_json(path.read_text(encoding="utf-8"))
                messages.append(msg)
                # 归档
                archive_path = self.ARCHIVE_DIR / self.agent_name / path.name
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                path.rename(archive_path)
            except Exception:
                pass
        return messages

    def poll(self, timeout: float = 0.1) -> List[TeamMessage]:
        """等待新消息（轮询方式）。"""
        return self.receive_all()

    def clear_inbox(self):
        """清空收件箱。"""
        for p in self.inbox_dir.glob("*.json"):
            p.unlink()


# ============================================================
# LLM Handler Factory (for state reload)
# ============================================================

def _create_llm_handler_from_prompt(role_name: str, role_prompt: str):
    """
    Create an LLM-based handler for a team agent from a stored prompt.
    Used to recreate handlers when loading team state.
    """
    from h_agent.core.client import get_client

    def handler(msg):
        try:
            # Import here to avoid circular imports at module load time
            from h_agent.core.config import MODEL
            from h_agent.team.team import TaskResult, AgentRole

            client = get_client()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": role_prompt},
                    {"role": "user", "content": str(msg.content)},
                ],
                max_tokens=2048,
            )
            content = response.choices[0].message.content
            return TaskResult(
                agent_name=role_name,
                role=AgentRole.COORDINATOR,
                success=True,
                content=content,
            )
        except Exception as e:
            from h_agent.team.team import TaskResult, AgentRole
            return TaskResult(
                agent_name=role_name,
                role=AgentRole.COORDINATOR,
                success=False,
                content=None,
                error=str(e),
            )
    return handler


# ============================================================
# Default Agent Prompts (fallback for old state files)
# ============================================================

DEFAULT_PROMPTS = {
    "planner": "你是一个资深任务规划师。你的职责是：\n1. 理解用户需求，分析任务复杂度\n2. 将大任务分解为可执行的小任务\n3. 评估每个子任务的工期和依赖\n4. 制定合理的执行计划\n\n当收到任务时，先思考再回答，给出清晰的任务分解和执行顺序。",
    "coder": "你是一个资深 Python 程序员。你的职责是：\n1. 根据需求编写高质量代码\n2. 遵循最佳实践，写出可维护的代码\n3. 编写清晰的注释和文档字符串\n4. 考虑边界情况和错误处理\n\n收到任务后，先分析需求，再给出完整实现代码。",
    "reviewer": "你是一个经验丰富的代码审查员。你的职责是：\n1. 审查代码的正确性、安全性和性能\n2. 提出改进建议\n3. 发现潜在的 bug 和漏洞\n4. 确保代码符合团队规范\n\n收到代码后，给出具体、中肯的审查意见。",
    "devops": "你是一个资深的 DevOps 工程师。你的职责是：\n1. 编写部署脚本和 CI/CD 配置\n2. 优化构建和部署流程\n3. 配置监控和日志系统\n4. 编写运维文档\n\n收到任务后，给出具体的实施方案。",
}


# ============================================================
# Agent Team Manager
# ============================================================

class AgentTeam:
    """
    多 agent 协作管理器。

    使用方式:
        team = AgentTeam("my-project")
        team.register("planner", AgentRole.PLANNER, planner_handler)
        team.register("coder", AgentRole.CODER, coder_handler)

        # 广播任务
        results = team.broadcast(Task(type="implement", description="..."))

        # 指定分发
        result = team.delegate("coder", Task(type="implement", ...))
    """

    STATE_FILE = TEAM_DIR / "team_state.json"

    def __init__(self, team_id: str = "default", coordinator: str = "coordinator"):
        self.team_id = team_id
        self.members: Dict[str, AgentMember] = {}
        self.coordinator = AgentRole(coordinator) if isinstance(coordinator, str) else coordinator
        self.pending_tasks: Dict[str, Dict] = {}
        self.history: List[Dict] = []
        # Per-agent adapter cache for session continuity
        self._adapter_cache: Dict[str, Any] = {}
        # Per-agent session IDs for memory isolation
        self._agent_sessions: Dict[str, str] = {}
        self._load_state()

    # ---- Member Management ----

    def _load_skill_tools(self) -> List[Dict]:
        """
        自动加载所有已启用 skill 的工具。
        
        Skills 的工具以 `skill_<skill_name>_<tool_name>` 格式注册，
        这样 agent 可以通过工具名称自动发现和调用 skill。
        
        Returns:
            List of skill tool definitions (OpenAI function format)
        """
        try:
            from h_agent.skills import get_enabled_tools
            raw_tools = get_enabled_tools()
            
            # Prefix each tool with skill_<name>_ to avoid naming conflicts
            prefixed_tools = []
            for tool in raw_tools:
                if "function" in tool:
                    func = tool["function"]
                    original_name = func["name"]
                    # skill_<name>_<func_name> format
                    func["name"] = f"skill_{original_name}"
                elif "name" in tool:
                    original_name = tool["name"]
                    tool["name"] = f"skill_{original_name}"
                prefixed_tools.append(tool)
            return prefixed_tools
        except Exception:
            return []

    def register(
        self,
        name: str,
        role: AgentRole,
        handler: Callable[[TeamMessage], TaskResult],
        description: str = "",
        system_prompt: str = "",
        tools: List[Dict] = None,
    ) -> AgentMember:
        """注册一个 agent 成员，自动加载 skill 工具。"""
        # Auto-load skill tools and merge with provided tools
        skill_tools = self._load_skill_tools()
        
        # Deduplicate: skip skill tools if a tool with same name already exists
        provided_names = {t.get("function", {}).get("name") or t.get("name") for t in (tools or [])}
        skill_tools = [t for t in skill_tools 
                      if (t.get("function", {}).get("name") or t.get("name")) not in provided_names]
        
        all_tools = (tools or []) + skill_tools
        
        member = AgentMember(
            name=name,
            role=role,
            description=description,
            system_prompt=system_prompt,
            tools=all_tools,
            _prompt=system_prompt,
        )
        member.set_handler(handler)
        self.members[name] = member
        self._save_state()
        return member

    def register_adapter(
        self,
        name: str,
        role: AgentRole,
        adapter_name: str,
        adapter_kwargs: Dict[str, Any] = None,
        description: str = "",
        tools: List[Dict] = None,
    ) -> AgentMember:
        """
        注册一个外部 adapter 作为团队成员。

        每个 adapter 有独立的会话实例，保证多 agent 模式下记忆隔离。
        
        Args:
            name: 成员名称
            role: 成员角色
            adapter_name: adapter 名称 (如 "opencode", "zoo:xueqiu", "claude")
            adapter_kwargs: 传给 adapter 的额外参数
            description: 成员描述
            tools: 成员可用的工具列表
        
        Example:
            team.register_adapter("xueqiu", AgentRole.RESEARCHER, "zoo", {"animal": "xueqiu"})
            team.register_adapter("coder", AgentRole.CODER, "opencode", {"agent": "code"})
        """
        from h_agent.adapters import get_adapter
        
        adapter_kwargs = adapter_kwargs or {}
        
        # Get or create cached adapter instance for this agent
        cache_key = f"{adapter_name}:{name}"
        if cache_key not in self._adapter_cache:
            self._adapter_cache[cache_key] = get_adapter(adapter_name, **adapter_kwargs)
        adapter = self._adapter_cache[cache_key]

        # Assign a stable session ID for this agent if not already assigned
        if name not in self._agent_sessions:
            self._agent_sessions[name] = f"team-{self.team_id}-{name}-{uuid.uuid4().hex[:6]}"
        session_id = self._agent_sessions[name]

        # Try to attach the session to the adapter if it supports it
        if hasattr(adapter, 'attach_session') and hasattr(adapter, 'session_id'):
            adapter.attach_session(session_id)

        def adapter_handler(msg: TeamMessage) -> TaskResult:
            try:
                # Re-use the cached adapter instance for session continuity
                response = adapter.chat(str(msg.content))
                
                # Sync session ID back from adapter (in case it was updated)
                if hasattr(adapter, 'session_id') and adapter.session_id:
                    self._agent_sessions[name] = adapter.session_id
                
                return TaskResult(
                    agent_name=name,
                    role=role,
                    success=not response.has_error(),
                    content=response.content,
                    error=response.error,
                    metadata={**response.metadata, "session_id": self._agent_sessions.get(name)},
                )
            except Exception as e:
                return TaskResult(
                    agent_name=name,
                    role=role,
                    success=False,
                    content=None,
                    error=str(e),
                )
        
        member = self.register(
            name=name,
            role=role,
            handler=adapter_handler,
            description=description,
            tools=tools or [],
        )
        
        # Store session ID and adapter reference on the member
        member.session_id = session_id
        member._adapter_instance = adapter
        
        return member

    def register_zoo_animal(
        self,
        animal: str,
        role: AgentRole = None,
        description: str = "",
    ) -> AgentMember:
        """
        快速注册一个 zoo animal 作为团队成员。
        
        Args:
            animal: zoo 动物名称 (xueqiu, liuliu, xiaohuang, heibai, xiaozhu)
            role: 成员角色，默认根据动物类型自动选择
            description: 成员描述
        
        Example:
            team.register_zoo_animal("xueqiu")  # 注册为 RESEARCHER
            team.register_zoo_animal("liuliu", AgentRole.CODER)  # 自定义角色
        """
        from h_agent.adapters.zoo_adapter import ZOO_ANIMALS, create_zoo_adapter
        
        if animal not in ZOO_ANIMALS:
            raise ValueError(f"Unknown animal '{animal}'. Available: {list(ZOO_ANIMALS.keys())}")
        
        # 根据动物自动选择角色
        if role is None:
            role_map = {
                "xueqiu": AgentRole.RESEARCHER,
                "liuliu": AgentRole.CODER,
                "xiaohuang": AgentRole.REVIEWER,
                "heibai": AgentRole.PLANNER,
                "xiaozhu": AgentRole.DEVOPS,
            }
            role = role_map.get(animal, AgentRole.RESEARCHER)
        
        animal_info = ZOO_ANIMALS[animal]
        desc = description or animal_info["description"]
        
        return self.register_adapter(
            name=animal,
            role=role,
            adapter_name="zoo",
            adapter_kwargs={"animal": animal},
            description=desc,
            tools=[{"name": t} for t in animal_info["tools"]],
        )

    def unregister(self, name: str) -> bool:
        """注销 agent。"""
        if name in self.members:
            del self.members[name]
            self._save_state()
            return True
        return False

    def list_members(self) -> List[Dict]:
        """列出所有成员。"""
        return [
            {
                "name": m.name,
                "role": m.role.value,
                "description": m.description,
                "enabled": m.enabled,
            }
            for m in self.members.values()
        ]

    def get_member(self, name: str) -> Optional[AgentMember]:
        return self.members.get(name)

    def get_agent_session(self, name: str) -> Optional[str]:
        """Get the session ID for a specific agent."""
        return self._agent_sessions.get(name)

    def get_all_agent_sessions(self) -> Dict[str, str]:
        """Get all agent session IDs."""
        return dict(self._agent_sessions)

    def set_agent_session(self, name: str, session_id: str) -> bool:
        """Set a session ID for an agent and sync to adapter."""
        member = self.members.get(name)
        if not member:
            return False
        self._agent_sessions[name] = session_id
        # Sync to adapter if cached
        cache_key = None
        for ck in self._adapter_cache:
            if ck.endswith(f":{name}"):
                cache_key = ck
                break
        if cache_key:
            adapter = self._adapter_cache[cache_key]
            if hasattr(adapter, 'attach_session'):
                adapter.attach_session(session_id)
        member.session_id = session_id
        return True

    def enable(self, name: str) -> bool:
        m = self.members.get(name)
        if m:
            m.enabled = True
            self._save_state()
            return True
        return False

    def disable(self, name: str) -> bool:
        m = self.members.get(name)
        if m:
            m.enabled = False
            self._save_state()
            return True
        return False

    # ---- Task Distribution ----

    def delegate(
        self,
        agent_name: str,
        task_type: str,
        task_content: Any,
        timeout: float = 120,
        ref_task_id: Optional[str] = None,
    ) -> TaskResult:
        """
        向单个 agent 分发任务（同步调用）。
        
        Args:
            agent_name: 目标 agent 名称
            task_type: 任务类型（"task"/"query"）
            task_content: 任务内容
            timeout: 超时秒数
            ref_task_id: 关联的上级任务 ID
        
        Returns:
            TaskResult
        """
        member = self.members.get(agent_name)
        if not member:
            return TaskResult(
                agent_name=agent_name,
                role=AgentRole.CODER,
                success=False,
                content=None,
                error=f"Agent '{agent_name}' not found",
            )

        if not member.enabled:
            return TaskResult(
                agent_name=agent_name,
                role=member.role,
                success=False,
                content=None,
                error=f"Agent '{agent_name}' is disabled",
            )

        # 构建消息
        msg = TeamMessage(
            msg_id=f"msg-{uuid.uuid4().hex[:8]}",
            sender="coordinator",
            receiver=agent_name,
            role=self.coordinator,
            type=task_type,
            content=task_content,
            ref_msg_id=ref_task_id,
        )

        # 记录任务
        task_id = msg.msg_id
        self.pending_tasks[task_id] = {
            "type": task_type,
            "content": task_content,
            "assignee": agent_name,
            "status": "running",
            "start": time.time(),
        }

        start = time.time()
        try:
            result = member.handle_message(msg)
            duration_ms = int((time.time() - start) * 1000)
            result.duration_ms = duration_ms
            result.ref_task_id = ref_task_id
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            result = TaskResult(
                agent_name=agent_name,
                role=member.role,
                success=False,
                content=None,
                error=str(e),
                duration_ms=duration_ms,
                ref_task_id=ref_task_id,
            )

        # 更新任务状态
        self.pending_tasks[task_id]["status"] = "done" if result.success else "failed"
        self.pending_tasks[task_id]["result"] = result.to_dict()
        self.history.append(result.to_dict())
        self._save_state()

        return result

    def broadcast(
        self,
        task_type: str,
        task_content: Any,
        target_roles: List[AgentRole] = None,
        timeout: float = 120,
        ref_task_id: Optional[str] = None,
    ) -> List[TaskResult]:
        """
        广播任务给多个 agent（并行执行）。
        
        Args:
            task_type: 任务类型
            task_content: 任务内容
            target_roles: 只发给特定角色的 agent（None = 所有）
            timeout: 单个 agent 超时
            ref_task_id: 关联的上级任务 ID
        
        Returns:
            所有 agent 的结果列表
        """
        # 确定目标 agent
        targets = []
        for name, member in self.members.items():
            if not member.enabled:
                continue
            if target_roles and member.role not in target_roles:
                continue
            targets.append(name)

        if not targets:
            return []

        # 并行分发
        import concurrent.futures
        results = []

        def dispatch(name):
            return self.delegate(name, task_type, task_content, timeout, ref_task_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures = {executor.submit(dispatch, name): name for name in targets}
            for future in concurrent.futures.as_completed(futures, timeout=timeout + 5):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    name = futures[future]
                    results.append(TaskResult(
                        agent_name=name,
                        role=AgentRole.CODER,
                        success=False,
                        content=None,
                        error=str(e),
                    ))

        return results

    def query(
        self,
        agent_name: str,
        query: str,
        timeout: float = 60,
    ) -> TaskResult:
        """向单个 agent 发送查询请求。"""
        return self.delegate(agent_name, "query", query, timeout)

    def talk_to(
        self,
        agent_name: str,
        message: str,
        timeout: float = 120,
    ) -> TaskResult:
        """
        直接与特定 agent 对话（发送聊天消息）。
        
        与 query 的区别：query 是请求信息，talk_to 是进行对话交互。
        消息会作为对话内容发送给目标 agent，类似人类用户与 agent 聊天。
        
        Args:
            agent_name: 目标 agent 名称
            message: 对话消息内容
            timeout: 超时秒数
        
        Returns:
            TaskResult，其中 content 是 agent 的回复
        """
        member = self.members.get(agent_name)
        if not member:
            return TaskResult(
                agent_name=agent_name,
                role=AgentRole.CODER,
                success=False,
                content=None,
                error=f"Agent '{agent_name}' not found. Available: {list(self.members.keys())}",
            )

        if not member.enabled:
            return TaskResult(
                agent_name=agent_name,
                role=member.role,
                success=False,
                content=None,
                error=f"Agent '{agent_name}' is disabled",
            )

        # 构建对话消息
        msg = TeamMessage(
            msg_id=f"msg-{uuid.uuid4().hex[:8]}",
            sender="user",
            receiver=agent_name,
            role=self.coordinator,
            type="dialog",
            content=message,
        )

        task_id = msg.msg_id
        self.pending_tasks[task_id] = {
            "type": "dialog",
            "content": message,
            "assignee": agent_name,
            "status": "running",
            "start": time.time(),
        }

        start = time.time()
        try:
            result = member.handle_message(msg)
            duration_ms = int((time.time() - start) * 1000)
            result.duration_ms = duration_ms
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            result = TaskResult(
                agent_name=agent_name,
                role=member.role,
                success=False,
                content=None,
                error=str(e),
                duration_ms=duration_ms,
            )

        self.pending_tasks[task_id]["status"] = "done" if result.success else "failed"
        self.pending_tasks[task_id]["result"] = result.to_dict()
        self.history.append(result.to_dict())
        self._save_state()

        return result

    # ---- Progress Tracking ----

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        return self.pending_tasks.get(task_id)

    def list_pending_tasks(self) -> List[Dict]:
        return [
            {**v, "task_id": k}
            for k, v in self.pending_tasks.items()
        ]

    def list_history(self, limit: int = 50) -> List[Dict]:
        return self.history[-limit:]

    def aggregate_results(self, results: List[TaskResult]) -> Dict:
        """
        汇总多个 agent 的结果。
        
        Returns:
            聚合报告，包含成功/失败统计、各 agent 输出摘要
        """
        total = len(results)
        succeeded = sum(1 for r in results if r.success)
        failed = total - succeeded

        by_role: Dict[str, List[TaskResult]] = {}
        for r in results:
            by_role.setdefault(r.role.value, []).append(r)

        summary = {}
        for role, role_results in by_role.items():
            summary[role] = {
                "count": len(role_results),
                "success": sum(1 for r in role_results if r.success),
                "failed": sum(1 for r in role_results if not r.success),
                "total_duration_ms": sum(r.duration_ms for r in role_results),
            }

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "by_role": summary,
            "results": [r.to_dict() for r in results],
        }

    # ---- Persistence ----

    def _save_state(self):
        """持久化团队状态。"""
        state = {
            "team_id": self.team_id,
            "members": [
                {
                    "name": m.name,
                    "role": m.role.value,
                    "description": m.description,
                    "enabled": m.enabled,
                    "session_id": self._agent_sessions.get(m.name),
                    "system_prompt": getattr(m, "_prompt", ""),
                }
                for m in self.members.values()
            ],
            "pending_tasks": self.pending_tasks,
            "history": self.history[-100:],  # 只保留最近 100 条
            "agent_sessions": self._agent_sessions,
        }
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self):
        """加载团队状态。"""
        if self.STATE_FILE.exists():
            try:
                state = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
                self.history = state.get("history", [])
                self.pending_tasks = state.get("pending_tasks", {})
                # Restore agent sessions for memory isolation
                loaded_sessions = state.get("agent_sessions", {})
                for name, session_id in loaded_sessions.items():
                    self._agent_sessions[name] = session_id
                    # Sync to member if registered
                    if name in self.members:
                        self.members[name].session_id = session_id
                # Restore registered members from state
                # Try to recreate live handlers from stored prompts or defaults
                for m_data in state.get("members", []):
                    name = m_data["name"]
                    if name not in self.members:
                        role = AgentRole(m_data.get("role", "coder"))
                        # Use stored prompt, or fall back to DEFAULT_PROMPTS for known agents
                        system_prompt = m_data.get("system_prompt", "") or DEFAULT_PROMPTS.get(name, "")
                        member = AgentMember(
                            name=name,
                            role=role,
                            description=m_data.get("description", ""),
                            enabled=m_data.get("enabled", True),
                            session_id=loaded_sessions.get(name),
                            _prompt=system_prompt,
                        )
                         # Try to recreate handler from stored/default prompt
                        if system_prompt:
                            try:
                                from h_agent.team.agent import AgentLoader, create_full_handler
                                profile = AgentLoader.load_profile(name)
                                if profile:
                                    handler = create_full_handler(name, profile, team_instance=self)
                                else:
                                    from h_agent.team.agent import init_agent_profile
                                    profile = init_agent_profile(name, role=role.value, description=m_data.get("description", ""))
                                    if profile.soul_path.exists():
                                        profile.soul_path.write_text(system_prompt)
                                    handler = create_full_handler(name, profile, team_instance=self)
                                member.set_handler(handler)
                            except Exception:
                                pass
                        self.members[name] = member
            except (json.JSONDecodeError, OSError):
                pass


# ============================================================
# Default Team Factory
# ============================================================

def create_default_team(
    planner_handler: Callable = None,
    coder_handler: Callable = None,
    reviewer_handler: Callable = None,
) -> AgentTeam:
    """
    创建默认配置的团队。
    
    包含三个标准角色:
    - planner: 任务规划分解
    - coder: 编码实现
    - reviewer: 代码审查
    """
    team = AgentTeam()

    if planner_handler:
        team.register(
            "planner",
            AgentRole.PLANNER,
            planner_handler,
            description="任务规划器，负责分解复杂任务为子任务",
        )

    if coder_handler:
        team.register(
            "coder",
            AgentRole.CODER,
            coder_handler,
            description="主程，负责代码实现",
        )

    if reviewer_handler:
        team.register(
            "reviewer",
            AgentRole.REVIEWER,
            reviewer_handler,
            description="代码审查员，负责质量把关",
        )

    return team
