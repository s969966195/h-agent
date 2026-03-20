#!/usr/bin/env python3
"""
h_agent/planner/scheduler.py - Task Scheduler

任务调度器:
- 管理任务队列
- 按依赖关系调度执行
- 支持并发数控制
- 失败重试
- 进度回调
"""

import json
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

from h_agent.planner.decomposer import Task, TaskStatus


# ============================================================
# Scheduler Config
# ============================================================

@dataclass
class SchedulerConfig:
    max_workers: int = 3          # 最大并发任务数
    task_timeout: float = 300     # 单任务超时（秒）
    retry_delay: float = 5        # 重试间隔（秒）
    poll_interval: float = 1.0    # 队列轮询间隔
    save_interval: float = 30.0   # 状态保存间隔


# ============================================================
# Scheduler Events
# ============================================================

class SchedulerEvent(Enum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"
    TASK_SKIPPED = "task_skipped"
    QUEUE_EMPTY = "queue_empty"
    ALL_DONE = "all_done"


# ============================================================
# Task Scheduler
# ============================================================

class TaskScheduler:
    """
    并发任务调度器。

    功能:
    - 维护待执行任务队列
    - 按依赖顺序调度
    - 控制并发数
    - 失败自动重试
    - 进度回调通知
    - 持久化状态
    """

    STATE_FILE = Path.home() / ".h-agent" / "planner" / "scheduler_state.json"

    def __init__(
        self,
        config: SchedulerConfig = None,
        executor_factory: Callable[[], ThreadPoolExecutor] = None,
    ):
        self.config = config or SchedulerConfig()
        self._executor_factory = executor_factory or (lambda: ThreadPoolExecutor(max_workers=self.config.max_workers))

        # 任务存储
        self._tasks: Dict[str, Task] = {}
        self._pending: List[str] = []     # 待执行队列（按优先级排序）
        self._running: Set[str] = set()   # 正在执行
        self._done: Set[str] = set()      # 已完成
        self._failed: Set[str] = set()     # 永久失败

        # 线程安全
        self._lock = threading.RLock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running_flag = False

        # 回调
        self._callbacks: Dict[SchedulerEvent, List[Callable]] = {
            e: [] for e in SchedulerEvent
        }

        # 任务处理器
        self._handlers: Dict[str, Callable[[Task], Any]] = {}

        # 统计
        self._started_at: Optional[str] = None
        self._completed_at: Optional[str] = None
        self._last_save = time.time()

        self._load_state()

    # ---- Task Registration ----

    def register_handler(self, task_id: str, handler: Callable[[Task], Any]):
        """注册任务处理器。"""
        self._handlers[task_id] = handler

    def register_role_handler(self, role: str, handler: Callable[[Task], Any]):
        """按角色注册通用处理器（role_hint 匹配时使用）。"""
        self._handlers[f"role:{role}"] = handler

    def add_task(self, task: Task) -> str:
        """添加一个任务到调度器。"""
        with self._lock:
            self._tasks[task.task_id] = task
            self._pending.append(task.task_id)
            self._maybe_save()
        return task.task_id

    def add_tasks(self, tasks: List[Task]):
        """批量添加任务。"""
        with self._lock:
            for task in tasks:
                self._tasks[task.task_id] = task
            # 按优先级排序
            pending_ids = [t.task_id for t in tasks] + self._pending
            self._pending = pending_ids
            self._maybe_save()

    # ---- Callbacks ----

    def on(self, event: SchedulerEvent, callback: Callable):
        """注册事件回调。"""
        self._callbacks[event].append(callback)

    def _emit(self, event: SchedulerEvent, data: dict):
        """触发事件回调。"""
        for cb in self._callbacks[event]:
            try:
                cb(event, data)
            except Exception:
                pass

    # ---- Execution ----

    def start(self, async_mode: bool = False):
        """
        启动调度器。
        
        Args:
            async_mode: True = asyncio 模式, False = 线程池模式
        """
        self._running_flag = True
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

        if async_mode:
            self._run_async()
        else:
            self._run_threaded()

    def _run_threaded(self):
        """线程池模式运行。"""
        self._executor = self._executor_factory()

        while self._running_flag:
            ready = self._get_ready_tasks()

            if not ready and not self._running:
                if not self._pending:
                    self._completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                    self._emit(SchedulerEvent.ALL_DONE, self._get_stats())
                    break
                time.sleep(self.config.poll_interval)
                continue

            # 提交就绪任务
            for task_id in ready[:self.config.max_workers - len(self._running)]:
                self._submit_task(task_id)

            time.sleep(self.config.poll_interval)

    async def _run_async(self):
        """asyncio 模式运行。"""
        loop = asyncio.get_event_loop()

        while self._running_flag:
            ready = self._get_ready_tasks()

            if not ready and not self._running:
                if not self._pending:
                    self._completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                    self._emit(SchedulerEvent.ALL_DONE, self._get_stats())
                    break
                await asyncio.sleep(self.config.poll_interval)
                continue

            # 并发提交
            for task_id in ready[:self.config.max_workers - len(self._running)]:
                loop.create_task(self._run_task_async(task_id))

            await asyncio.sleep(self.config.poll_interval)

    def _get_ready_tasks(self) -> List[str]:
        """获取满足执行条件（依赖已完成）的任务。"""
        completed = self._done | {t.task_id for t in self._tasks.values() if t.status == TaskStatus.DONE}
        with self._lock:
            ready = []
            for task_id in self._pending:
                task = self._tasks.get(task_id)
                if not task or task.status != TaskStatus.PENDING:
                    continue
                if task.is_ready(completed):
                    ready.append(task_id)
            return ready

    def _submit_task(self, task_id: str):
        """提交任务到线程池。"""
        with self._lock:
            if task_id in self._running:
                return
            task = self._tasks.get(task_id)
            if not task:
                return

            task.start()
            self._running.add(task_id)
            self._pending.remove(task_id)

        self._emit(SchedulerEvent.TASK_STARTED, {"task": task.to_dict()})

        future: Future = self._executor.submit(self._execute_task, task_id)
        future.add_done_callback(lambda f: self._on_task_done(task_id, f))

    async def _run_task_async(self, task_id: str):
        """异步运行单个任务。"""
        with self._lock:
            if task_id in self._running:
                return
            task = self._tasks.get(task_id)
            if not task:
                return
            task.start()
            self._running.add(task_id)
            if task_id in self._pending:
                self._pending.remove(task_id)

        self._emit(SchedulerEvent.TASK_STARTED, {"task": task.to_dict()})

        try:
            result = await asyncio.wait_for(
                self._execute_task_async(task_id),
                timeout=self.config.task_timeout
            )
            self._complete_task(task_id, result)
        except asyncio.TimeoutError:
            self._fail_task(task_id, f"Task timed out after {self.config.task_timeout}s")
        except Exception as e:
            self._fail_task(task_id, str(e))

    def _execute_task(self, task_id: str) -> Any:
        """在线程中执行任务。"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        handler = self._get_handler(task)
        if not handler:
            return None

        try:
            return handler(task)
        except Exception as e:
            raise e

    async def _execute_task_async(self, task_id: str) -> Any:
        """在 asyncio 中执行任务。"""
        task = self._tasks.get(task_id)
        if not task:
            return None

        handler = self._get_handler(task)
        if not handler:
            return None

        result = handler(task)

        # 如果 handler 返回协程
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _get_handler(self, task: Task) -> Optional[Callable]:
        """获取任务处理器。"""
        # 优先用 task_id 精确匹配
        if task.task_id in self._handlers:
            return self._handlers[task.task_id]
        # 然后用 role_hint 匹配
        if task.role_hint and f"role:{task.role_hint}" in self._handlers:
            return self._handlers[f"role:{task.role_hint}"]
        # 最后用通用处理器
        if "default" in self._handlers:
            return self._handlers["default"]
        return None

    def _on_task_done(self, task_id: str, future: Future):
        """线程池任务完成回调。"""
        with self._lock:
            if task_id not in self._running:
                return

        try:
            result = future.result()
            self._complete_task(task_id, result)
        except Exception as e:
            self._fail_task(task_id, str(e))

    def _complete_task(self, task_id: str, result: Any):
        """标记任务完成。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            task.complete(result)
            self._running.discard(task_id)
            self._done.add(task_id)
            self._maybe_save()

        self._emit(SchedulerEvent.TASK_COMPLETED, {
            "task": task.to_dict(),
            "result": result,
        })

        # 触发被阻塞的任务
        self._unblock_dependents(task_id)

    def _fail_task(self, task_id: str, error: str):
        """标记任务失败。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            if task.retry():
                self._running.discard(task_id)
                self._pending.append(task_id)
                self._emit(SchedulerEvent.TASK_RETRY, {"task": task.to_dict(), "error": error})
                time.sleep(self.config.retry_delay)
            else:
                task.fail(error)
                self._running.discard(task_id)
                self._failed.add(task_id)
                self._emit(SchedulerEvent.TASK_FAILED, {"task": task.to_dict(), "error": error})

                # 标记依赖此任务的其他任务为 blocked
                self._block_dependents(task_id)

        self._maybe_save()

    def _unblock_dependents(self, completed_id: str):
        """当任务完成时，解除依赖它的任务的阻塞。"""
        for task in self._tasks.values():
            if completed_id in task.depends_on:
                # 检查是否还有其他未完成的依赖
                still_blocked = any(
                    dep not in self._done
                    for dep in task.depends_on
                )
                if not still_blocked and task.status == TaskStatus.BLOCKED:
                    task.status = TaskStatus.PENDING
                    if task.task_id not in self._pending:
                        self._pending.append(task.task_id)

    def _block_dependents(self, failed_id: str):
        """当任务永久失败时，阻塞依赖它的任务。"""
        for task in self._tasks.values():
            if failed_id in task.depends_on and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.BLOCKED

    # ---- Control ----

    def stop(self):
        """停止调度器。"""
        self._running_flag = False
        if self._executor:
            self._executor.shutdown(wait=False)

    def wait(self, timeout: float = None) -> bool:
        """等待所有任务完成。"""
        deadline = time.time() + (timeout or 999999)
        while time.time() < deadline:
            with self._lock:
                if not self._running and not self._pending:
                    return True
            time.sleep(0.5)
        return False

    # ---- Status ----

    def get_status(self) -> Dict:
        """获取调度器状态。"""
        with self._lock:
            return {
                "total": len(self._tasks),
                "pending": len(self._pending),
                "running": len(self._running),
                "done": len(self._done),
                "failed": len(self._failed),
                "started_at": self._started_at,
                "completed_at": self._completed_at,
            }

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus = None) -> List[Task]:
        """列出任务，可按状态过滤。"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: (-t.priority, t.created_at))

    def _get_stats(self) -> Dict:
        return self.get_status()

    # ---- Persistence ----

    def _maybe_save(self):
        """定期保存状态。"""
        now = time.time()
        if now - self._last_save < self.config.save_interval:
            return
        self._save_state()
        self._last_save = now

    def _save_state(self):
        """持久化调度器状态。"""
        with self._lock:
            state = {
                "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
                "pending": self._pending,
                "done": list(self._done),
                "failed": list(self._failed),
                "started_at": self._started_at,
                "completed_at": self._completed_at,
            }
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_state(self):
        """从磁盘恢复状态。"""
        if not self.STATE_FILE.exists():
            return
        try:
            state = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
            self._tasks = {k: Task.from_dict(v) for k, v in state.get("tasks", {}).items()}
            self._pending = state.get("pending", [])
            self._done = set(state.get("done", []))
            self._failed = set(state.get("failed", []))
            self._started_at = state.get("started_at")
            self._completed_at = state.get("completed_at")
        except (json.JSONDecodeError, OSError):
            pass
