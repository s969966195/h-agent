#!/usr/bin/env python3
"""
h_agent/scheduler/store.py - Task storage for scheduler.

Provides persistent storage for cron jobs and heartbeat tasks
using JSON files.
"""

import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from h_agent.platform_utils import get_config_dir


# ============================================================
# Paths
# ============================================================

def _get_scheduler_dir() -> Path:
    """Get the scheduler data directory."""
    return get_config_dir() / "scheduler"


def _get_cron_jobs_file() -> Path:
    """Get the cron jobs storage file."""
    d = _get_scheduler_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "cron_jobs.json"


def _get_heartbeat_state_file() -> Path:
    """Get the heartbeat state file."""
    d = _get_scheduler_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "heartbeat_state.json"


def _get_executions_file() -> Path:
    """Get the task executions log file."""
    d = _get_scheduler_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "executions.json"


# ============================================================
# Task Status
# ============================================================

class TaskStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    FAILED = "failed"


# ============================================================
# Task Models
# ============================================================

@dataclass
class CronJob:
    """A cron job definition."""
    id: str
    expression: str  # cron expression
    command: str      # command to execute
    name: str          # human-readable name
    enabled: bool = True
    status: str = "active"
    created_at: float = 0
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CronJob":
        return cls(**d)


@dataclass
class HeartbeatTask:
    """A heartbeat task definition."""
    id: str
    name: str
    command: str
    interval: int  # seconds
    enabled: bool = True
    status: str = "active"
    last_run: Optional[float] = None
    next_run: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HeartbeatTask":
        return cls(**d)


@dataclass
class ExecutionRecord:
    """Record of a task execution."""
    id: str
    task_id: str
    task_type: str  # "cron" or "heartbeat"
    started_at: float
    completed_at: Optional[float] = None
    success: bool = False
    output: str = ""
    error: str = ""
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionRecord":
        return cls(**d)


# ============================================================
# Storage Operations
# ============================================================

def _load_json(path: Path) -> Dict[str, Any]:
    """Load JSON from file, returns empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    """Save data to JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file first, then rename for atomicity
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


# ============================================================
# Cron Job Storage
# ============================================================

def list_cron_jobs() -> List[CronJob]:
    """List all cron jobs."""
    data = _load_json(_get_cron_jobs_file())
    jobs = data.get("jobs", [])
    return [CronJob.from_dict(j) for j in jobs]


def get_cron_job(job_id: str) -> Optional[CronJob]:
    """Get a cron job by ID."""
    jobs = list_cron_jobs()
    for job in jobs:
        if job.id == job_id:
            return job
    return None


def save_cron_job(job: CronJob) -> None:
    """Save a cron job (add or update)."""
    jobs = list_cron_jobs()
    job.created_at = job.created_at or time.time()
    
    # Check if job exists
    for i, j in enumerate(jobs):
        if j.id == job.id:
            jobs[i] = job
            break
    else:
        jobs.append(job)
    
    data = {"jobs": [j.to_dict() for j in jobs]}
    _save_json(_get_cron_jobs_file(), data)


def delete_cron_job(job_id: str) -> bool:
    """Delete a cron job by ID."""
    jobs = list_cron_jobs()
    original_count = len(jobs)
    jobs = [j for j in jobs if j.id != job_id]
    
    if len(jobs) == original_count:
        return False
    
    data = {"jobs": [j.to_dict() for j in jobs]}
    _save_json(_get_cron_jobs_file(), data)
    return True


def update_cron_job(job_id: str, updates: Dict[str, Any]) -> Optional[CronJob]:
    """Update specific fields of a cron job."""
    job = get_cron_job(job_id)
    if not job:
        return None
    
    for key, value in updates.items():
        if hasattr(job, key):
            setattr(job, key, value)
    
    save_cron_job(job)
    return job


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return str(uuid.uuid4())[:8]


# ============================================================
# Heartbeat State Storage
# ============================================================

def get_heartbeat_state() -> Dict[str, Any]:
    """Get the heartbeat state."""
    return _load_json(_get_heartbeat_state_file())


def save_heartbeat_state(state: Dict[str, Any]) -> None:
    """Save the heartbeat state."""
    _save_json(_get_heartbeat_state_file(), state)


def is_heartbeat_running() -> bool:
    """Check if heartbeat is currently running."""
    state = get_heartbeat_state()
    pid = state.get("pid", 0)
    if pid <= 0:
        return False
    
    # Check if process is alive
    import os
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def start_heartbeat(interval: int = 60) -> Dict[str, Any]:
    """Mark heartbeat as started."""
    import os
    state = {
        "running": True,
        "pid": os.getpid(),
        "started_at": time.time(),
        "interval": interval,
    }
    save_heartbeat_state(state)
    return state


def stop_heartbeat() -> None:
    """Mark heartbeat as stopped."""
    state = get_heartbeat_state()
    state["running"] = False
    state["stopped_at"] = time.time()
    save_heartbeat_state(state)


# ============================================================
# Execution Records
# ============================================================

def list_executions(task_id: Optional[str] = None, limit: int = 50) -> List[ExecutionRecord]:
    """List execution records, optionally filtered by task_id."""
    data = _load_json(_get_executions_file())
    records = [ExecutionRecord.from_dict(r) for r in data.get("records", [])]
    
    if task_id:
        records = [r for r in records if r.task_id == task_id]
    
    # Sort by started_at descending, limit
    records.sort(key=lambda r: r.started_at, reverse=True)
    return records[:limit]


def save_execution(record: ExecutionRecord) -> None:
    """Save an execution record."""
    data = _load_json(_get_executions_file())
    records = data.get("records", [])
    
    # Add new record
    records.append(record.to_dict())
    
    # Keep only last 500 records
    if len(records) > 500:
        records = records[-500:]
    
    data["records"] = records
    _save_json(_get_executions_file(), data)


def clear_executions(task_id: Optional[str] = None) -> int:
    """Clear execution records, optionally only for a specific task."""
    data = _load_json(_get_executions_file())
    records = data.get("records", [])
    
    if task_id:
        original_count = len(records)
        records = [r for r in records if r.get("task_id") != task_id]
        cleared = original_count - len(records)
    else:
        cleared = len(records)
        records = []
    
    data["records"] = records
    _save_json(_get_executions_file(), data)
    return cleared
