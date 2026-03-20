#!/usr/bin/env python3
"""
h_agent/scheduler - Scheduler module for h-agent.

Provides heartbeat and cron capabilities for periodic task execution.

Example usage:
    # Add a cron job
    from h_agent.scheduler import add_cron_job, list_cron_jobs
    
    add_cron_job("*/5 * * * *", "echo 'Running every 5 minutes'", "Test Task")
    jobs = list_cron_jobs()
    
    # Start heartbeat
    from h_agent.scheduler import start_heartbeat, heartbeat_status
    
    start_heartbeat()
    print(heartbeat_status())
"""

from h_agent.scheduler.store import (
    CronJob,
    HeartbeatTask,
    ExecutionRecord,
    list_cron_jobs,
    get_cron_job,
    save_cron_job,
    delete_cron_job,
    update_cron_job,
    generate_job_id,
    list_executions,
    save_execution,
    clear_executions,
    get_heartbeat_state,
    save_heartbeat_state,
    is_heartbeat_running,
    start_heartbeat as _start_heartbeat_state,
    stop_heartbeat as _stop_heartbeat_state,
)

from h_agent.scheduler.cron import (
    CronExpression,
    parse_cron,
    validate_cron,
    get_next_run_time,
    format_next_run,
)

from h_agent.scheduler.heartbeat import (
    HeartbeatMonitor,
    get_heartbeat_info,
    start_heartbeat_daemon,
    stop_heartbeat_daemon,
    DEFAULT_INTERVAL,
)


# ============================================================
# Convenience Functions
# ============================================================

def add_cron_job(
    expression: str,
    command: str,
    name: str,
    enabled: bool = True,
) -> CronJob:
    """Add a new cron job.
    
    Args:
        expression: Cron expression (e.g., "*/5 * * * *")
        command: Command to execute
        name: Human-readable name for the job
        enabled: Whether the job is enabled
    
    Returns:
        The created CronJob
    """
    # Validate expression
    is_valid, error = validate_cron(expression)
    if not is_valid:
        raise ValueError(f"Invalid cron expression: {error}")
    
    # Calculate next run
    next_run = get_next_run_time(expression)
    
    job = CronJob(
        id=generate_job_id(),
        expression=expression,
        command=command,
        name=name,
        enabled=enabled,
        status="active" if enabled else "disabled",
        created_at=0,  # Will be set by save_cron_job
        next_run=next_run.timestamp() if next_run else None,
    )
    
    save_cron_job(job)
    return job


def enable_cron_job(job_id: str) -> bool:
    """Enable a cron job."""
    job = update_cron_job(job_id, {"enabled": True, "status": "active"})
    return job is not None


def disable_cron_job(job_id: str) -> bool:
    """Disable a cron job."""
    job = update_cron_job(job_id, {"enabled": False, "status": "disabled"})
    return job is not None


def heartbeat_status() -> dict:
    """Get heartbeat status."""
    info = get_heartbeat_info()
    return {
        "running": info.get("currently_running", False),
        "pid": info.get("state", {}).get("pid"),
        "started_at": info.get("state", {}).get("started_at"),
        "interval": info.get("state", {}).get("interval", DEFAULT_INTERVAL),
        "last_check": info.get("state", {}).get("last_check"),
        "executions": info.get("state", {}).get("executions", 0),
    }


def start_heartbeat(interval: int = DEFAULT_INTERVAL) -> bool:
    """Start the heartbeat daemon."""
    return start_heartbeat_daemon(interval)


def stop_heartbeat() -> bool:
    """Stop the heartbeat daemon."""
    return stop_heartbeat_daemon()


# ============================================================
# Module Info
# ============================================================

__all__ = [
    # Store
    "CronJob",
    "HeartbeatTask",
    "ExecutionRecord",
    "list_cron_jobs",
    "get_cron_job",
    "save_cron_job",
    "delete_cron_job",
    "update_cron_job",
    "generate_job_id",
    "list_executions",
    "clear_executions",
    "get_heartbeat_state",
    "is_heartbeat_running",
    # Cron
    "CronExpression",
    "parse_cron",
    "validate_cron",
    "get_next_run_time",
    "format_next_run",
    # Heartbeat
    "HeartbeatMonitor",
    "get_heartbeat_info",
    "start_heartbeat",
    "stop_heartbeat",
    "heartbeat_status",
    # Convenience
    "add_cron_job",
    "enable_cron_job",
    "disable_cron_job",
    "DEFAULT_INTERVAL",
]
