#!/usr/bin/env python3
"""
h_agent/planner/progress.py - Progress Tracker

任务进度跟踪:
- 实时进度百分比
- 时间估算（ETA）
- 里程碑检测
- 格式化输出
- 报告生成
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

from h_agent.planner.decomposer import Task, TaskStatus


PROGRESS_DIR = Path.home() / ".h-agent" / "planner"
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Milestone:
    """里程碑 - 一组任务的完成标记。"""
    name: str
    task_ids: List[str]
    description: str = ""
    reached: bool = False
    reached_at: Optional[str] = None


class ProgressTracker:
    """
    进度跟踪器。

    功能:
    - 跟踪整体进度百分比
    - 计算 ETA
    - 定义和检测里程碑
    - 生成格式化报告
    """

    REPORT_FILE = PROGRESS_DIR / "progress_report.json"

    def __init__(self, scheduler=None):
        self.scheduler = scheduler
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.milestones: Dict[str, Milestone] = {}
        self._events: List[Dict] = []

    # ---- Progress Calculation ----

    def get_progress(self) -> float:
        """计算整体进度（0.0 ~ 1.0）。"""
        if not self.scheduler:
            return 0.0

        total = len(self.scheduler._tasks)
        if total == 0:
            return 0.0

        done = len(self.scheduler._done)
        return min(done / total, 1.0)

    def get_progress_pct(self) -> str:
        """返回格式化的百分比字符串。"""
        return f"{self.get_progress() * 100:.1f}%"

    def get_eta_seconds(self) -> Optional[float]:
        """计算预计剩余时间（秒）。基于已完成任务的平均速度。"""
        if not self.scheduler:
            return None

        done_count = len(self.scheduler._done)
        if done_count == 0:
            return None

        elapsed = time.time() - self.start_time
        rate = done_count / elapsed  # tasks per second
        remaining = len(self.scheduler._tasks) - done_count

        if rate == 0:
            return None
        return remaining / rate

    def get_eta_str(self) -> str:
        """返回人类可读的 ETA 字符串。"""
        eta = self.get_eta_seconds()
        if eta is None:
            return "calculating..."

        if eta < 60:
            return f"{eta:.0f}s"
        elif eta < 3600:
            return f"{eta/60:.0f}m"
        else:
            h = int(eta / 3600)
            m = int((eta % 3600) / 60)
            return f"{h}h {m}m"

    # ---- Milestones ----

    def add_milestone(self, name: str, task_ids: List[str], description: str = ""):
        """定义一个里程碑。"""
        self.milestones[name] = Milestone(
            name=name,
            task_ids=task_ids,
            description=description,
        )

    def add_milestone_by_tags(self, name: str, tags: List[str], description: str = ""):
        """通过标签定义里程碑（所有带这些标签的任务完成即达成）。"""
        if not self.scheduler:
            return
        task_ids = [
            t.task_id for t in self.scheduler._tasks.values()
            if any(tag in t.tags for tag in tags)
        ]
        self.add_milestone(name, task_ids, description)

    def check_milestones(self) -> List[Milestone]:
        """检查里程碑达成情况。"""
        if not self.scheduler:
            return []

        completed_ids = self.scheduler._done | {
            t.task_id for t in self.scheduler._tasks.values()
            if t.status == TaskStatus.DONE
        }

        newly_reached = []
        for ms in self.milestones.values():
            if ms.reached:
                continue
            if all(tid in completed_ids for tid in ms.task_ids):
                ms.reached = True
                ms.reached_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                newly_reached.append(ms)
                self._record_event("milestone_reached", {"name": ms.name})

        return newly_reached

    def get_milestone_summary(self) -> List[Dict]:
        """获取里程碑汇总。"""
        completed_ids = self.scheduler._done if self.scheduler else set()
        return [
            {
                "name": ms.name,
                "description": ms.description,
                "reached": ms.reached,
                "reached_at": ms.reached_at,
                "progress": f"{sum(1 for tid in ms.task_ids if tid in completed_ids)}/{len(ms.task_ids)}",
            }
            for ms in self.milestones.values()
        ]

    # ---- Status Reports ----

    def get_task_table(self) -> List[Dict]:
        """生成任务状态表格数据。"""
        if not self.scheduler:
            return []

        rows = []
        for task in self.scheduler.list_tasks():
            rows.append({
                "id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority,
                "role": task.role_hint or "",
                "duration_ms": (
                    (time.time() - time.mktime(time.strptime(task.started_at, "%Y-%m-%dT%H:%M:%S")))
                    if task.started_at else 0
                ),
                "result": str(task.result)[:100] if task.result else "",
                "error": task.error[:50] if task.error else "",
            })
        return rows

    def get_summary(self) -> Dict:
        """生成整体摘要。"""
        progress = self.get_progress()
        stats = self.scheduler.get_status() if self.scheduler else {}

        return {
            "progress": f"{progress*100:.1f}%",
            "progress_float": round(progress, 3),
            "eta": self.get_eta_str(),
            "stats": stats,
            "milestones": self.get_milestone_summary(),
            "elapsed_seconds": int(time.time() - self.start_time),
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S") if self.end_time else None,
        }

    def print_progress_bar(self, width: int = 40) -> str:
        """生成 ASCII 进度条。"""
        progress = self.get_progress()
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {self.get_progress_pct()}  ETA: {self.get_eta_str()}"

    def generate_report(self) -> str:
        """生成文本格式报告。"""
        summary = self.get_summary()
        lines = [
            "=" * 60,
            "TASK PROGRESS REPORT",
            "=" * 60,
            f"Progress:  {summary['progress']}",
            f"ETA:       {summary['eta']}",
            f"Elapsed:   {summary['elapsed_seconds']}s",
            "",
        ]

        stats = summary.get("stats", {})
        lines += [
            f"Tasks:     total={stats.get('total', 0)}  "
            f"done={stats.get('done', 0)}  "
            f"running={stats.get('running', 0)}  "
            f"failed={stats.get('failed', 0)}",
            "",
        ]

        # Milestones
        ms_list = summary.get("milestones", [])
        if ms_list:
            lines.append("Milestones:")
            for ms in ms_list:
                status = "✅" if ms["reached"] else "⬜"
                lines.append(f"  {status} {ms['name']} — {ms['progress']}")
                if ms["reached_at"]:
                    lines.append(f"         reached at {ms['reached_at']}")
            lines.append("")

        # Tasks
        task_table = self.get_task_table()
        if task_table:
            lines.append("Tasks:")
            for row in task_table:
                icon = {
                    "done": "✅",
                    "running": "🔄",
                    "pending": "⏳",
                    "failed": "❌",
                    "blocked": "🚫",
                    "skipped": "⏭",
                }.get(row["status"], "?")
                lines.append(
                    f"  {icon} [{row['id']}] {row['title']} "
                    f"(role={row['role'] or '—'}, priority={row['priority']})"
                )
                if row["error"]:
                    lines.append(f"       ERROR: {row['error']}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def save_report(self):
        """保存报告到文件。"""
        try:
            report = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                **self.get_summary(),
                "task_table": self.get_task_table(),
            }
            self.REPORT_FILE.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    # ---- Event Recording ----

    def _record_event(self, event_type: str, data: Dict):
        self._events.append({
            "type": event_type,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **data,
        })

    def get_events(self) -> List[Dict]:
        return list(self._events)
