#!/usr/bin/env python3
"""
h_agent/daemon/recovery.py - Daemon Auto-Start & Session Recovery

核心功能:
1. Daemon 自动启动（launchd / systemd / Windows 服务）
2. Session 状态自动恢复
3. 历史消息加载和重建
4. 崩溃后自动重启
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from h_agent.platform_utils import IS_WINDOWS, IS_MACOS, IS_LINUX, which


# ============================================================
# Auto-Start Configuration
# ============================================================

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


@dataclass
class AutoStartConfig:
    enabled: bool = True
    launch_on_login: bool = True
    restart_on_crash: bool = True
    restart_delay_seconds: int = 5
    max_restart_attempts: int = 3
    start_timeout_seconds: int = 10


# ============================================================
# Daemon Auto-Start Manager
# ============================================================

class AutoStartManager:
    """
    跨平台 daemon 自动启动管理器。

    支持:
    - macOS: LaunchAgents plist
    - Linux: systemd user service
    - Windows: 注册表 Run key（简版）
    """

    SERVICE_NAME = "com.h-agent.daemon"
    PLIST_NAME = f"{SERVICE_NAME}.plist"

    def __init__(self, config: AutoStartConfig = None):
        self.config = config or AutoStartConfig()

    # ---- Detect Platform ----

    def _get_python_exe(self) -> str:
        return subprocess.getoutput("which python3") or "python3"

    def _get_module启动_cmd(self) -> List[str]:
        return [self._get_python_exe(), "-m", "h_agent.daemon.server"]

    # ---- macOS LaunchAgents ----

    def _get_macos_plist_content(self) -> str:
        cmd = self._get_module启动_cmd()
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cmd[0]}</string>
        <string>-m</string>
        <string>h_agent.daemon.server</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>H_AGENT_PORT</key>
        <string>19527</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/h-agent-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/h-agent-daemon.err</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""

    def _is_macos_installed(self) -> bool:
        plist = LAUNCH_AGENTS_DIR / self.PLIST_NAME
        return plist.exists()

    def install_macos(self) -> bool:
        """安装 macOS LaunchAgent。"""
        if not IS_MACOS:
            return False

        LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        plist_path = LAUNCH_AGENTS_DIR / self.PLIST_NAME

        try:
            plist_path.write_text(self._get_macos_plist_content(), encoding="utf-8")
            # 加载服务
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
                timeout=10,
            )
            return True
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False

    def uninstall_macos(self) -> bool:
        """卸载 macOS LaunchAgent。"""
        if not IS_MACOS:
            return False

        plist_path = LAUNCH_AGENTS_DIR / self.PLIST_NAME
        try:
            subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                timeout=10,
            )
            if plist_path.exists():
                plist_path.unlink()
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    # ---- Linux systemd ----

    def _get_systemd_service_content(self) -> str:
        cmd = self._get_module启动_cmd()
        python_path = self._get_python_exe()
        return f"""[Unit]
Description=h-agent Daemon Service
After=network.target

[Service]
Type=simple
ExecStart={python_path} -m h_agent.daemon.server
Environment=H_AGENT_PORT=19527
Restart=always
RestartSec={self.config.restart_delay_seconds}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""

    def install_systemd(self) -> bool:
        """安装 systemd user service。"""
        if not IS_LINUX:
            return False

        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        service_path = SYSTEMD_USER_DIR / f"{self.SERVICE_NAME}.service"

        try:
            service_path.write_text(self._get_systemd_service_content(), encoding="utf-8")
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", self.SERVICE_NAME],
                capture_output=True,
                timeout=10,
            )
            return True
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False

    def uninstall_systemd(self) -> bool:
        """卸载 systemd service。"""
        if not IS_LINUX:
            return False

        try:
            subprocess.run(
                ["systemctl", "--user", "disable", self.SERVICE_NAME],
                capture_output=True,
                timeout=10,
            )
            service_path = SYSTEMD_USER_DIR / f"{self.SERVICE_NAME}.service"
            if service_path.exists():
                service_path.unlink()
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    # ---- Windows ----

    def install_windows(self) -> bool:
        """Windows 简版自启动（写入注册表）。"""
        if not IS_WINDOWS:
            return False

        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE,
            )
            python = subprocess.getoutput("where python").split("\n")[0]
            cmd = f'"{python}" -m h_agent.daemon.server'
            winreg.SetValueEx(key, "h-agent", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def uninstall_windows(self) -> bool:
        """Windows 删除自启动注册表项。"""
        if not IS_WINDOWS:
            return False

        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE,
            )
            winreg.DeleteValue(key, "h-agent")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    # ---- Platform-agnostic API ----

    def install(self) -> bool:
        """安装自动启动（平台自动检测）。"""
        if IS_MACOS:
            return self.install_macos()
        elif IS_LINUX:
            return self.install_systemd()
        elif IS_WINDOWS:
            return self.install_windows()
        return False

    def uninstall(self) -> bool:
        """卸载自动启动。"""
        if IS_MACOS:
            return self.uninstall_macos()
        elif IS_LINUX:
            return self.uninstall_systemd()
        elif IS_WINDOWS:
            return self.uninstall_windows()
        return False

    def is_installed(self) -> bool:
        """检查是否已安装自动启动。"""
        if IS_MACOS:
            return self._is_macos_installed()
        elif IS_LINUX:
            service_path = SYSTEMD_USER_DIR / f"{self.SERVICE_NAME}.service"
            return service_path.exists()
        elif IS_WINDOWS:
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_READ,
                )
                winreg.QueryValueEx(key, "h-agent")
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                return False
            except Exception:
                return False
        return False

    def enable(self) -> bool:
        """启用服务（start）。"""
        if IS_MACOS:
            plist = LAUNCH_AGENTS_DIR / self.PLIST_NAME
            if not plist.exists():
                return self.install_macos()
            try:
                subprocess.run(
                    ["launchctl", "start", self.SERVICE_NAME],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception:
                return False
        elif IS_LINUX:
            try:
                subprocess.run(
                    ["systemctl", "--user", "start", self.SERVICE_NAME],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception:
                return False
        return False

    def disable(self) -> bool:
        """停止并禁用服务。"""
        if IS_MACOS:
            try:
                subprocess.run(
                    ["launchctl", "stop", self.SERVICE_NAME],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception:
                return False
        elif IS_LINUX:
            try:
                subprocess.run(
                    ["systemctl", "--user", "stop", self.SERVICE_NAME],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception:
                return False
        return False


# ============================================================
# Session Recovery
# ============================================================

class SessionRecovery:
    """
    Session 状态恢复器。

    在 daemon 启动时:
    1. 加载最近的 session
    2. 重建消息历史
    3. 恢复当前 session 上下文
    4. 加载长时记忆
    """

    RECOVERY_FILE = Path.home() / ".h-agent" / "sessions" / "recovery.json"

    def __init__(self):
        self.last_session_id: Optional[str] = None
        self.last_session_name: Optional[str] = None
        self.crashed: bool = False
        self._load_recovery_info()

    def _load_recovery_info(self):
        """加载恢复信息。"""
        if self.RECOVERY_FILE.exists():
            try:
                data = json.loads(self.RECOVERY_FILE.read_text(encoding="utf-8"))
                self.last_session_id = data.get("last_session_id")
                self.last_session_name = data.get("last_session_name")
                self.crashed = data.get("crashed", False)
            except (json.JSONDecodeError, OSError):
                pass

    def save_recovery_info(self, session_id: str, session_name: str = None):
        """保存恢复信息（每次切换 session 时调用）。"""
        try:
            self.RECOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.RECOVERY_FILE.write_text(
                json.dumps({
                    "last_session_id": session_id,
                    "last_session_name": session_name,
                    "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "crashed": False,
                }, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    def mark_crash(self):
        """标记发生了崩溃（供下次启动检测）。"""
        try:
            if self.RECOVERY_FILE.exists():
                data = json.loads(self.RECOVERY_FILE.read_text(encoding="utf-8"))
            else:
                data = {}
            data["crashed"] = True
            data["crashed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.RECOVERY_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError):
            pass

    def get_recovery_session_id(self) -> Optional[str]:
        """获取需要恢复的 session ID。"""
        return self.last_session_id

    def load_session_history(self, session_id: str, session_manager) -> List[Dict]:
        """加载指定 session 的历史消息。"""
        try:
            return session_manager.get_history(session_id)
        except Exception:
            return []

    def recover(self, session_manager) -> Dict[str, Any]:
        """
        执行完整恢复流程。

        Returns:
            恢复报告，包含 session 信息、历史消息数量等
        """
        report = {
            "recovered": False,
            "session_id": None,
            "session_name": None,
            "message_count": 0,
            "crashed": self.crashed,
            "error": None,
        }

        if not self.last_session_id:
            return report

        # 检查 session 是否存在
        session = session_manager.get_session(self.last_session_id)
        if not session:
            # session 已被删除，尝试最近的一个
            sessions = session_manager.list_sessions()
            if sessions:
                most_recent = sessions[0]
                self.last_session_id = most_recent["session_id"]
                self.last_session_name = most_recent.get("name")
                session = most_recent
            else:
                report["error"] = "No sessions available for recovery"
                return report

        # 加载历史
        history = self.load_session_history(self.last_session_id, session_manager)

        # 设置为当前 session
        session_manager.set_current(self.last_session_id)

        report["recovered"] = True
        report["session_id"] = self.last_session_id
        report["session_name"] = self.last_session_name or session.get("name")
        report["message_count"] = len(history)

        # 清除 crash 标记
        if self.crashed:
            self.crashed = False
            try:
                if self.RECOVERY_FILE.exists():
                    data = json.loads(self.RECOVERY_FILE.read_text(encoding="utf-8"))
                    data["crashed"] = False
                    self.RECOVERY_FILE.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
            except (json.JSONDecodeError, OSError):
                pass

        return report


# ============================================================
# Crash Handler
# ============================================================

class CrashHandler:
    """
    崩溃处理器。
    在 daemon 异常退出时保存状态，以便下次恢复。
    """

    CRASH_FILE = Path.home() / ".h-agent" / "sessions" / "crash.json"
    MAX_CRASH_REPORTS = 5

    @classmethod
    def record_crash(
        cls,
        exception_type: str,
        exception_message: str,
        traceback: str,
        session_id: Optional[str] = None,
    ):
        """记录崩溃信息。"""
        try:
            crash_reports = []
            if cls.CRASH_FILE.exists():
                try:
                    crash_reports = json.loads(cls.CRASH_FILE.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    crash_reports = []

            report = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "exception_type": exception_type,
                "exception_message": exception_message,
                "traceback": traceback,
                "session_id": session_id,
            }

            crash_reports.insert(0, report)
            crash_reports = crash_reports[:cls.MAX_CRASH_REPORTS]

            cls.CRASH_FILE.parent.mkdir(parents=True, exist_ok=True)
            cls.CRASH_FILE.write_text(
                json.dumps(crash_reports, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    @classmethod
    def get_crash_reports(cls) -> List[Dict]:
        """获取崩溃报告列表。"""
        if not cls.CRASH_FILE.exists():
            return []
        try:
            return json.loads(cls.CRASH_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
