#!/usr/bin/env python3
"""
h_agent/scheduler/heartbeat.py - Heartbeat mechanism for h-agent.

Heartbeat periodically checks if any periodic tasks need to run,
such as checking emails, calendar events, or other scheduled checks.

The heartbeat runs as a background thread that wakes up at regular
intervals to perform checks.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, asdict

# Add parent to path for imports when running directly
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from h_agent.scheduler.store import (
    get_heartbeat_state,
    save_heartbeat_state,
    list_cron_jobs,
    update_cron_job,
    save_execution,
    ExecutionRecord,
    is_heartbeat_running,
)
from h_agent.scheduler.cron import CronExpression, get_next_run_time


# ============================================================
# Heartbeat Configuration
# ============================================================

DEFAULT_INTERVAL = 60  # seconds between heartbeat checks


# ============================================================
# Heartbeat Monitor
# ============================================================

class HeartbeatMonitor:
    """Monitor that periodically checks and executes scheduled tasks."""
    
    def __init__(self, interval: int = DEFAULT_INTERVAL):
        """Initialize the heartbeat monitor.
        
        Args:
            interval: Seconds between heartbeat checks (default: 60)
        """
        self.interval = interval
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check = 0.0
        self._task_count = 0
        self._executions = 0
        
    @property
    def status(self) -> Dict[str, Any]:
        """Get current heartbeat status."""
        return {
            "running": self.running,
            "interval": self.interval,
            "last_check": self._last_check,
            "task_count": self._task_count,
            "executions": self._executions,
            "pid": os.getpid() if self.running else None,
        }
    
    def _check_tasks(self) -> List[Dict[str, Any]]:
        """Check for tasks that need to run and execute them.
        
        Returns a list of task results.
        """
        results = []
        now = time.time()
        
        # Get all cron jobs
        jobs = list_cron_jobs()
        self._task_count = len(jobs)
        
        for job in jobs:
            if not job.enabled:
                continue
            
            # Check if job should run
            should_run = False
            
            if job.next_run is None or job.next_run <= now:
                # Job is due - check if current time matches cron expression
                try:
                    cron = CronExpression(job.expression)
                    if cron.matches():
                        should_run = True
                except ValueError:
                    # Invalid expression, skip
                    continue
            
            if should_run:
                # Execute the job
                result = self._execute_job(job)
                results.append(result)
                self._executions += 1
                
                # Update job's next run time
                next_run = get_next_run_time(job.expression)
                update_cron_job(job.id, {
                    "last_run": now,
                    "next_run": next_run.timestamp() if next_run else None,
                })
        
        self._last_check = now
        return results
    
    def _execute_job(self, job) -> Dict[str, Any]:
        """Execute a single cron job."""
        from h_agent.scheduler.store import generate_job_id
        
        record = ExecutionRecord(
            id=generate_job_id(),
            task_id=job.id,
            task_type="cron",
            started_at=time.time(),
        )
        
        try:
            # Execute the command
            result = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            record.completed_at = time.time()
            record.success = result.returncode == 0
            record.output = result.stdout[:4096]  # Limit output size
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
        
        # Save the execution record
        save_execution(record)
        
        return {
            "job_id": job.id,
            "job_name": job.name,
            "success": record.success,
            "output": record.output[:200] if record.output else "",
            "error": record.error[:200] if record.error else "",
        }
    
    def _heartbeat_loop(self) -> None:
        """Main heartbeat loop running in background thread."""
        # Install signal handlers for this thread
        def signal_handler(signum, frame):
            self._stop_event.set()
        
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except (ValueError, OSError):
            # Signal handlers can only be set in main thread on some platforms
            pass
        
        # Save initial state
        save_heartbeat_state({
            "running": True,
            "pid": os.getpid(),
            "started_at": time.time(),
            "interval": self.interval,
        })
        
        while not self._stop_event.is_set():
            try:
                # Check and execute due tasks
                results = self._check_tasks()
                
                # Log any task executions
                if results:
                    for r in results:
                        status = "✓" if r["success"] else "✗"
                        print(f"[Heartbeat] {status} {r['job_name']}")
                
                # Update state
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
            
            # Wait for next interval or stop signal
            self._stop_event.wait(self.interval)
        
        # Clean exit
        save_heartbeat_state({
            "running": False,
            "stopped_at": time.time(),
        })
    
    def start(self, blocking: bool = False) -> bool:
        """Start the heartbeat monitor.
        
        Args:
            blocking: If True, run in current thread (blocking).
                     If False, run in background thread.
        
        Returns:
            True if started successfully.
        """
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
            print("[Heartbeat] Not running")
            return False
        
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        
        self.running = False
        return True
    
    def run_once(self) -> List[Dict[str, Any]]:
        """Run a single heartbeat check (for testing/manual triggers)."""
        return self._check_tasks()


# ============================================================
# CLI Helper Functions
# ============================================================

def get_heartbeat_info() -> Dict[str, Any]:
    """Get information about the heartbeat system."""
    state = get_heartbeat_state()
    monitor = HeartbeatMonitor()
    
    return {
        "configured": True,
        "currently_running": is_heartbeat_running(),
        "state": state,
        "monitor_status": monitor.status if state.get("running") else None,
    }


def start_heartbeat_daemon(interval: int = DEFAULT_INTERVAL) -> bool:
    """Start the heartbeat as a daemon (background process)."""
    if is_heartbeat_running():
        print("Heartbeat is already running")
        return False
    
    # Fork to background
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process - give child time to start
            time.sleep(0.5)
            if is_heartbeat_running():
                print(f"Heartbeat started (PID: {pid})")
                return True
            else:
                print("Heartbeat failed to start")
                return False
        
        # Child process - become daemon
        os.setsid()  # Detach from terminal
        
        # Redirect standard file descriptors
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)  # stdin
        os.dup2(devnull, 1)  # stdout
        os.dup2(devnull, 2)  # stderr
        os.close(devnull)
        
        # Start the heartbeat loop
        monitor = HeartbeatMonitor(interval)
        monitor.start(blocking=True)
        
    except Exception as e:
        print(f"Failed to start heartbeat: {e}")
        return False


def stop_heartbeat_daemon() -> bool:
    """Stop the heartbeat daemon."""
    state = get_heartbeat_state()
    pid = state.get("pid", 0)
    
    if pid <= 0:
        print("Heartbeat is not running (no PID found)")
        return False
    
    try:
        os.kill(pid, signal.SIGTERM)
        
        # Wait for process to stop
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except ProcessLookupError:
                print("Heartbeat stopped")
                return True
        
        # Force kill if still alive
        try:
            os.kill(pid, signal.SIGKILL)
            print("Heartbeat killed")
            return True
        except ProcessLookupError:
            return True
        except PermissionError:
            print("Permission denied to kill heartbeat process")
            return False
            
    except ProcessLookupError:
        print("Heartbeat process not found")
        return True
    except Exception as e:
        print(f"Failed to stop heartbeat: {e}")
        return False
