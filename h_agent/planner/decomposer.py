#!/usr/bin/env python3
"""
h_agent/planner/decomposer.py - Task Decomposition Engine

核心功能:
1. 理解复杂任务描述
2. 自动分解为可执行的子任务
3. 识别任务依赖关系
4. 生成执行计划（任务树）
"""

import json
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Callable
from pathlib import Path

PLANNER_DIR = Path.home() / ".h-agent" / "planner"
PLANNER_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Task Status
# ============================================================

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


# ============================================================
# Task Node
# ============================================================

@dataclass
class Task:
    """
    任务节点 - 任务树的基本单元。

    支持:
    - 父子依赖关系
    - 状态跟踪
    - 执行结果存储
    - 标签和优先级
    - 重试计数
    """
    task_id: str = field(default_factory=lambda: f"t-{uuid.uuid4().hex[:8]}")
    parent_id: Optional[str] = None

    # 任务内容
    title: str = ""
    description: str = ""
    instructions: str = ""        # 给 agent 的具体指令
    expected_output: str = ""      # 期望输出

    # 元数据
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0             # 0=正常, 1=高, 2=紧急
    tags: List[str] = field(default_factory=list)

    # 分配
    assigned_to: Optional[str] = None  # agent 名称
    role_hint: Optional[str] = None    # 建议分配的角色

    # 执行
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2

    # 时间
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    estimated_duration_minutes: int = 10

    # 依赖
    depends_on: List[str] = field(default_factory=list)  # 依赖的任务 ID 列表
    blocked_by: List[str] = field(default_factory=list)  # 阻塞此任务的其他任务

    # 子任务
    children: List["Task"] = field(default_factory=list)

    # ---- Status transitions ----

    def start(self) -> bool:
        if self.status not in (TaskStatus.PENDING, TaskStatus.BLOCKED):
            return False
        self.status = TaskStatus.RUNNING
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return True

    def complete(self, result: Any = None):
        self.status = TaskStatus.DONE
        self.result = result
        self.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def fail(self, error: str):
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def retry(self) -> bool:
        """尝试重试。"""
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            self.status = TaskStatus.PENDING
            self.error = None
            return True
        return False

    def skip(self):
        self.status = TaskStatus.SKIPPED
        self.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ---- Dependency ----

    def is_ready(self, completed_ids: Set[str]) -> bool:
        """检查任务是否满足执行条件（依赖已全部完成）。"""
        if self.status != TaskStatus.PENDING:
            return False
        return all(dep_id in completed_ids for dep_id in self.depends_on)

    # ---- Serialization ----

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["children"] = [c.to_dict() if isinstance(c, Task) else c for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        if "status" in d and isinstance(d["status"], str):
            d["status"] = TaskStatus(d["status"])
        if "children" in d:
            d["children"] = [cls.from_dict(c) if isinstance(c, dict) else c for c in d["children"]]
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ============================================================
# Task Decomposer
# ============================================================

class TaskDecomposer:
    """
    任务分解引擎。

    使用 LLM 或规则引擎将复杂任务分解为可执行的子任务树。
    支持两种模式:
    - LLM 模式: 使用模型理解并分解
    - 规则模式: 基于预定义规则分解（离线可用）
    """

    def __init__(self, llm_client=None, model: str = "gpt-4o"):
        self.llm_client = llm_client
        self.model = model

    # ---- LLM-based decomposition ----

    SYSTEM_PROMPT = """You are a task decomposition assistant. Given a complex task, break it down into smaller, actionable subtasks.

Rules:
1. Each subtask should be independently executable
2. Order subtasks by dependency (things that must come first go first)
3. Each subtask needs clear instructions and expected output
4. Prefer 4-8 subtasks for a complex task (not too granular, not too coarse)
5. Tag each subtask with a relevant role hint: planner/coder/reviewer/devops/researcher

Output format: JSON array of subtasks with fields:
- title: short descriptive name
- description: what this subtask involves
- instructions: exact instructions for the agent
- expected_output: what success looks like
- role_hint: recommended agent role
- priority: 0=normal, 1=high, 2=urgent
- depends_on: array of indices this depends on (e.g. [0, 1] means depends on first two)
- tags: relevant tags
- estimated_duration_minutes: rough time estimate

Be concrete. No generic "implement feature X" — break it down to specific files/functions/tests.
"""

    def decompose(self, task_description: str, max_depth: int = 2) -> List[Task]:
        """
        将复杂任务分解为子任务列表。

        Args:
            task_description: 任务描述
            max_depth: 最大分解深度

        Returns:
            顶级任务列表（每个可包含子任务）
        """
        if self.llm_client:
            return self._decompose_llm(task_description, max_depth)
        else:
            return self._decompose_rules(task_description)

    def _decompose_llm(self, description: str, max_depth: int) -> List[Task]:
        """使用 LLM 进行任务分解。"""
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Decompose this task:\n\n{description}"},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            content = response.choices[0].message.content or "[]"

            # 提取 JSON（可能在 markdown 代码块中）
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            subtasks_data = json.loads(content)
            return self._build_task_tree(subtasks_data)

        except Exception as e:
            # LLM 失败，回退到规则分解
            return self._decompose_rules(description)

    def _build_task_tree(self, subtasks_data: List[dict]) -> List[Task]:
        """从 LLM 输出构建任务树。"""
        tasks = []
        task_map: Dict[int, Task] = {}

        for i, spec in enumerate(subtasks_data):
            # 转换依赖索引
            dep_ids = []
            for dep_idx in spec.get("depends_on", []):
                if dep_idx < i and dep_idx in task_map:
                    dep_ids.append(task_map[dep_idx].task_id)

            task = Task(
                title=spec.get("title", f"Task {i}"),
                description=spec.get("description", ""),
                instructions=spec.get("instructions", spec.get("description", "")),
                expected_output=spec.get("expected_output", ""),
                role_hint=spec.get("role_hint"),
                priority=spec.get("priority", 0),
                tags=spec.get("tags", []),
                depends_on=dep_ids,
                estimated_duration_minutes=spec.get("estimated_duration_minutes", 10),
            )
            tasks.append(task)
            task_map[i] = task

        # 构建父子关系
        self._link_parents(tasks, subtasks_data)

        return tasks

    def _link_parents(self, tasks: List[Task], specs: List[dict]):
        """根据依赖关系建立父子树。"""
        # 顶级任务：没有被其他任务依赖
        all_ids = {t.task_id for t in tasks}
        dependent_ids = set()
        for task in tasks:
            for dep in task.depends_on:
                dependent_ids.add(dep)

        for task in tasks:
            if task.task_id not in dependent_ids:
                continue  # 是顶级任务

    # ---- Rule-based decomposition (offline-capable) ----

    def _decompose_rules(self, description: str) -> List[Task]:
        """
        基于规则的简单任务分解（离线可用）。
        识别关键词并生成通用子任务模板。
        """
        desc_lower = description.lower()
        tasks: List[Task] = []

        # 代码相关关键词
        if any(k in desc_lower for k in ["implement", "实现", "write", "编写", "create", "创建"]):
            tasks.append(Task(
                title="Research & Design",
                description="Research approach and design solution",
                instructions="Research the best approach for the task. Check existing code patterns. Produce a short design note.",
                expected_output="Design document or approach description",
                role_hint="researcher",
                priority=1,
                estimated_duration_minutes=15,
            ))
            tasks.append(Task(
                title="Implement Core Feature",
                description="Write the main implementation",
                instructions="Implement the feature following the design. Write clean, maintainable code with basic error handling.",
                expected_output="Working code implementation",
                role_hint="coder",
                priority=2,
                depends_on=[tasks[0].task_id] if tasks else [],
                estimated_duration_minutes=30,
            ))

        if any(k in desc_lower for k in ["test", "测试", "spec"]):
            tasks.append(Task(
                title="Write Tests",
                description="Create test coverage",
                instructions="Write unit tests or integration tests for the implementation.",
                expected_output="Test suite with passing tests",
                role_hint="coder",
                priority=1,
                estimated_duration_minutes=20,
            ))

        if any(k in desc_lower for k in ["review", "审查", "refactor", "重构"]):
            tasks.append(Task(
                title="Review & Refine",
                description="Review code quality and suggest improvements",
                instructions="Review the implementation for bugs, performance issues, and code quality. Suggest concrete fixes.",
                expected_output="Review report with specific recommendations",
                role_hint="reviewer",
                priority=1,
                estimated_duration_minutes=15,
            ))

        if any(k in desc_lower for k in ["deploy", "部署", "release", "发布"]):
            tasks.append(Task(
                title="Deploy",
                description="Deploy to target environment",
                instructions="Prepare deployment artifacts, run deployment steps, verify the deployment.",
                expected_output="Successfully deployed application",
                role_hint="devops",
                priority=2,
                estimated_duration_minutes=20,
            ))

        # 如果没有匹配到任何关键词，生成通用任务
        if not tasks:
            tasks.append(Task(
                title="Understand Task",
                description=f"Understand and plan: {description[:100]}",
                instructions=f"Understand the task: {description}. Identify the key steps needed.",
                expected_output="Clear understanding of what needs to be done",
                role_hint="planner",
                priority=2,
                estimated_duration_minutes=10,
            ))
            tasks.append(Task(
                title="Execute",
                description=f"Execute: {description[:100]}",
                instructions=f"Execute the task: {description}. Use appropriate tools.",
                expected_output="Task completion",
                role_hint="coder",
                priority=2,
                depends_on=[tasks[0].task_id] if tasks else [],
                estimated_duration_minutes=30,
            ))

        return tasks

    # ---- Task Tree Operations ----

    def flatten_tree(self, tasks: List[Task]) -> List[Task]:
        """将任务树扁平化为线性列表（按执行顺序）。"""
        result = []
        seen = set()

        def visit(task: Task):
            if task.task_id in seen:
                return
            seen.add(task.task_id)
            result.append(task)
            for child in task.children:
                visit(child)

        for task in tasks:
            visit(task)
        return result

    def get_execution_order(self, tasks: List[Task]) -> List[Task]:
        """
        计算拓扑排序后的执行顺序。
        确保依赖任务在后续任务之前执行。
        """
        all_tasks = self.flatten_tree(tasks)
        task_map = {t.task_id: t for t in all_tasks}

        # 计算入度
        in_degree: Dict[str, int] = {t.task_id: len(t.depends_on) for t in all_tasks}

        # BFS 拓扑排序
        ready = [t for t in all_tasks if in_degree[t.task_id] == 0]
        result = []

        while ready:
            task = ready.pop(0)
            result.append(task)
            # 找到所有依赖此任务的任务
            for t in all_tasks:
                if task.task_id in t.depends_on:
                    in_degree[t.task_id] -= 1
                    if in_degree[t.task_id] == 0:
                        ready.append(t)

        return result


# ============================================================
# Convenience API
# ============================================================

def quick_plan(description: str) -> List[Task]:
    """快速计划 — 一行调用分解任务。"""
    decomposer = TaskDecomposer()
    return decomposer.decompose(description)
