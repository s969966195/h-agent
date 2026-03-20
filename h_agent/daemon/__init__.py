"""
h_agent.daemon - Backend service with TCP socket IPC.

Exports:
- DaemonServer: Main daemon service
- DaemonClient: IPC client
- SessionRecovery: Auto-recovery on startup
- CrashHandler: Crash recording
- AutoStartManager: Platform auto-start (launchd/systemd)
"""

from .server import DaemonServer, run_daemon, daemon_status
from .client import DaemonClient
from .recovery import (
    SessionRecovery,
    CrashHandler,
    AutoStartManager,
    AutoStartConfig,
)

__all__ = [
    "DaemonServer",
    "DaemonClient",
    "run_daemon",
    "daemon_status",
    "SessionRecovery",
    "CrashHandler",
    "AutoStartManager",
    "AutoStartConfig",
]
