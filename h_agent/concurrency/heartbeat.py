"""
h_agent/concurrency/heartbeat.py - Heartbeat integration with CommandQueue lanes.

Replaces the raw threading.Lock in the original heartbeat with a lane-aware
lock using the heartbeat lane. This allows heartbeat tasks to be properly
serialized and tracked alongside cron and main lane tasks.
"""

import os
import time
import threading
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from h_agent.concurrency.lanes import CommandQueue, LANE_HEARTBEAT, LaneQueue
from h_agent.scheduler.store import (
    get_heartbeat_state,
    save_heartbeat_state,
    list_cron_jobs,
    update_cron_job,
    save_execution,
    ExecutionRecord,
    is_heartbeat_running,
    generate_job_id,
)
from h_agent.scheduler.cron import CronExpression, get_next_run_time


DEFAULT_INTERVAL = 60  # seconds


class HeartbeatMonitor:
    """Heartbeat monitor that uses CommandQueue lanes for concurrency control."""

    def __init__(
        self,
        command_queue: Optional[CommandQueue] = None,
        interval: int = DEFAULT_INTERVAL,
    ):
        self._cmd_queue = command_queue or CommandQueue()
        self._lane = self._cmd_queue.get_or_create_lane(LANE_HEARTBEAT, max_concurrency=1)
        self.interval = interval
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check = 0.0
        self._task_count = 0
        self._executions = 0

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "interval": self.interval,
            "last_check": self._last_check,
            "task_count": self._task_count,
            "executions": self._executions,
            "pid": os.getpid() if self.running else None,
            "lane_stats": self._lane.stats(),
        }

    def _check_tasks(self) -> List[Dict[str, Any]]:
        """Check and execute due cron jobs."""
        results = []
        now = time.time()
        jobs = list_cron_jobs()
        self._task_count = len(jobs)

        for job in jobs:
            if not job.enabled:
                continue

            try:
                cron = CronExpression(job.expression)
                if cron.matches():
                    result = self._execute_job(job)
                    results.append(result)
                    self._executions += 1

                    next_run = get_next_run_time(job.expression)
                    update_cron_job(job.id, {
                        "last_run": now,
                        "next_run": next_run.timestamp() if next_run else None,
                    })
            except ValueError:
                continue

        self._last_check = now
        return results

    def _execute_job(self, job) -> Dict[str, Any]:
        """Execute a single cron job via the heartbeat lane."""
        record = ExecutionRecord(
            id=generate_job_id(),
            task_id=job.id,
            task_type="cron",
            started_at=time.time(),
        )

        try:
            result = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            record.completed_at = time.time()
            record.success = result.returncode == 0
            record.output = result.stdout[:4096]
            record.error = result.stderr[:4096]
            record.exit_code = result.returncode
        except subprocess.TimeoutExpired:
            record.completed_at = time.time()
            record.success = False
            record.error = "Execution timed out (5 minute limit)"
            record.exit_code = -1
        except Exception as e:
            record.completed_at = time.time()
            record.success = False
            record.error = str(e)
            record.exit_code = -1

        save_execution(record)
        return {
            "job_id": job.id,
            "job_name": job.name,
            "success": record.success,
            "output": record.output[:200] if record.output else "",
            "error": record.error[:200] if record.error else "",
        }

    def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        def signal_handler(signum, frame):
            self._stop_event.set()

        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except (ValueError, OSError):
            pass

        save_heartbeat_state({
            "running": True,
            "pid": os.getpid(),
            "started_at": time.time(),
            "interval": self.interval,
        })

        while not self._stop_event.is_set():
            try:
                results = self._check_tasks()
                if results:
                    for r in results:
                        status = "✓" if r["success"] else "✗"
                        print(f"[Heartbeat] {status} {r['job_name']}")

                save_heartbeat_state({
                    "running": True,
                    "pid": os.getpid(),
                    "started_at": get_heartbeat_state().get("started_at", time.time()),
                    "last_check": self._last_check,
                    "interval": self.interval,
                    "executions": self._executions,
                })
            except Exception as e:
                print(f"[Heartbeat] Error in check loop: {e}")

            self._stop_event.wait(self.interval)

        save_heartbeat_state({"running": False, "stopped_at": time.time()})

    def start(self, blocking: bool = False) -> bool:
        """Start the heartbeat monitor."""
        if self.running:
            print("[Heartbeat] Already running")
            return False

        self.running = True
        self._stop_event.clear()

        if blocking:
            self._heartbeat_loop()
        else:
            self._thread = threading.Thread(
                target=self._heartbeat_loop,
                name="heartbeat",
                daemon=True,
            )
            self._thread.start()
        return True

    def stop(self) -> bool:
        """Stop the heartbeat monitor."""
        if not self.running:
            return False

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self.running = False
        return True

    def run_once(self) -> List[Dict[str, Any]]:
        """Run a single heartbeat check (for manual triggers)."""
        return self._check_tasks()
