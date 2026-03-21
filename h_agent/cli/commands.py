#!/usr/bin/env python3
"""
h_agent/cli/commands.py - Command Line Interface

Main entry point for h_agent CLI.
Supports:
  - Daemon control (start, status, stop, logs)
  - Session management (list, create, history, delete, tag, group, search)
  - RAG (index, search)
  - Run and chat with agent
  - Version info

Cross-platform: supports Linux/macOS (Unix) and Windows.
"""

import os
import sys
import json
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

# Add parent to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from h_agent.platform_utils import (
    IS_WINDOWS, daemon_pid_file, start_daemon_subprocess,
    stop_process, is_process_alive, get_config_dir
)

# Paths - use platform-aware PID file
PID_FILE = str(daemon_pid_file())
DAEMON_PORT = int(os.environ.get("H_AGENT_PORT", 19527))
LOG_FILE = str(daemon_pid_file().parent / "daemon.log")

# Import from core
from h_agent.core.tools import TOOL_HANDLERS, execute_tool_call, TOOLS
from h_agent.core.config import (
    MODEL, OPENAI_BASE_URL, OPENAI_API_KEY,
    list_config
)

from h_agent.session.manager import SessionManager, get_manager
from h_agent.team.agent import (
    AgentLoader, FullAgentHandler, init_agent_profile,
    create_full_handler, list_team_agents, AGENTS_DIR
)
from h_agent import __version__

# ============================================================
# Error helpers
# ============================================================

def _err(msg: str):
    print(f"\033[31mError: {msg}\033[0m", file=sys.stderr)

def _warn(msg: str):
    print(f"\033[33mWarning: {msg}\033[0m")

def _ok(msg: str):
    print(f"\033[32m{msg}\033[0m")

def _find_session(mgr: SessionManager, session_id: str) -> Optional[str]:
    """Find session ID by name or ID, return canonical ID or None."""
    if not session_id:
        return None
    # Direct match
    if mgr.get_session(session_id):
        return session_id
    # Match by name
    for s in mgr.list_sessions():
        if s.get("name") == session_id:
            return s["session_id"]
    return None


# ============================================================
# Init / Wizard
# ============================================================

def cmd_init(args) -> int:
    """Handle init command - interactive setup wizard."""
    from h_agent.cli.init_wizard import run_wizard, run_wizard_quick
    if args.quick:
        return run_wizard_quick()
    return run_wizard()


def cmd_config_wizard(args) -> int:
    """Handle config --wizard command."""
    from h_agent.cli.init_wizard import run_wizard
    return run_wizard()


# ============================================================
# Daemon Control
# ============================================================

def daemon_status() -> dict:
    """Check daemon status (cross-platform)."""
    pid_file = Path(PID_FILE)
    if not pid_file.exists():
        return {"running": False}

    try:
        with open(pid_file) as f:
            data = json.load(f)
        pid = data.get("pid", 0)
        port = data.get("port", DAEMON_PORT)

        if is_process_alive(pid):
            return {"running": True, "pid": pid, "port": port}

        try:
            pid_file.unlink()
        except OSError:
            pass
        return {"running": False}
    except (ValueError, ProcessLookupError, PermissionError, json.JSONDecodeError, OSError):
        try:
            pid_file.unlink()
        except OSError:
            pass
        return {"running": False}


def start_daemon():
    """Start the daemon in background (cross-platform)."""
    status = daemon_status()
    if status.get("running"):
        print(f"Daemon already running (PID: {status['pid']}, Port: {status['port']})")
        return 0

    pid = start_daemon_subprocess(sys.executable, DAEMON_PORT)
    if pid is None:
        _err("Failed to start daemon (subprocess error)")
        return 1

    pid_file = Path(PID_FILE)
    for _ in range(20):
        time.sleep(0.25)
        new_status = daemon_status()
        if new_status.get("running"):
            print(f"Daemon started (PID: {new_status['pid']}, Port: {new_status['port']})")
            return 0

    _err("Failed to start daemon (timeout)")
    return 1


def stop_daemon():
    """Stop the daemon (cross-platform)."""
    status = daemon_status()
    if not status.get("running"):
        print("Daemon not running")
        try:
            Path(PID_FILE).unlink()
        except OSError:
            pass
        return 0

    pid = status["pid"]
    if stop_process(pid, timeout=2.0):
        try:
            Path(PID_FILE).unlink()
        except OSError:
            pass
        print("Daemon stopped")
        return 0
    else:
        _err(f"Failed to stop daemon (PID: {pid}). You may need to stop it manually.")
        return 1


def cmd_start(args) -> int:
    """Handle start command."""
    return start_daemon()


def cmd_status(args) -> int:
    """Handle status command."""
    status = daemon_status()
    if status.get("running"):
        print(f"Daemon running (PID: {status['pid']}, Port: {status['port']})")

        try:
            from h_agent.daemon.client import DaemonClient
            client = DaemonClient(status['port'])
            info = client.status()
            if info.get("success"):
                result = info.get("result", {})
                print(f"  Current session: {result.get('current_session', 'none')}")
                print(f"  Total sessions: {result.get('session_count', 0)}")
        except Exception as e:
            print(f"  (Could not connect to daemon: {e})")
    else:
        print("Daemon not running")
        print("  Run 'h-agent start' to start the daemon")
    return 0


def cmd_autostart(args) -> int:
    """Handle autostart command — install/uninstall daemon auto-start."""
    from h_agent.daemon.recovery import AutoStartManager, AutoStartConfig

    mgr = AutoStartManager()

    action = args.autostart_action

    if action == "install":
        if mgr.is_installed():
            print("Auto-start already installed.")
            return 0
        if mgr.install():
            _ok("Auto-start installed.")
            if IS_MACOS:
                print("  Note: On macOS, you may need to grant Full Disk Access")
                print("  to the LaunchAgent for session recovery to work.")
            return 0
        _err("Failed to install auto-start. Check permissions.")
        return 1

    if action == "uninstall":
        if not mgr.is_installed():
            print("Auto-start not installed.")
            return 0
        if mgr.uninstall():
            _ok("Auto-start uninstalled.")
            return 0
        _err("Failed to uninstall.")
        return 1

    if action == "status":
        installed = mgr.is_installed()
        if installed:
            _ok("Auto-start is installed.")
        else:
            print("Auto-start is NOT installed.")
            print()
            print("Install with: h-agent autostart install")
            print("Supports: macOS (LaunchAgent), Linux (systemd), Windows (Registry)")
        return 0

    return 0


def _create_llm_handler(role_name: str, role_prompt: str):
    """
    Create an LLM-based handler for a team agent.
    The handler calls the configured LLM with the agent's role prompt.
    """
    from openai import OpenAI
    from h_agent.core.config import MODEL, OPENAI_API_KEY, OPENAI_BASE_URL
    from h_agent.team.team import TaskResult, AgentRole

    def handler(msg):
        try:
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
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
            return TaskResult(
                agent_name=role_name,
                role=AgentRole.COORDINATOR,
                success=False,
                content=None,
                error=str(e),
            )
    return handler


# Default agent definitions for team init
DEFAULT_AGENTS = [
    {
        "name": "planner",
        "role": "planner",
        "description": "任务规划师，负责分析需求和分解任务",
        "prompt": "你是一个资深任务规划师。你的职责是：\n1. 理解用户需求，分析任务复杂度\n2. 将大任务分解为可执行的小任务\n3. 评估每个子任务的工期和依赖\n4. 制定合理的执行计划\n\n当收到任务时，先思考再回答，给出清晰的任务分解和执行顺序。",
    },
    {
        "name": "coder",
        "role": "coder",
        "description": "主程序员，负责代码实现",
        "prompt": "你是一个资深 Python 程序员。你的职责是：\n1. 根据需求编写高质量代码\n2. 遵循最佳实践，写出可维护的代码\n3. 编写清晰的注释和文档字符串\n4. 考虑边界情况和错误处理\n\n收到任务后，先分析需求，再给出完整实现代码。",
    },
    {
        "name": "reviewer",
        "role": "reviewer",
        "description": "代码审查员，负责代码质量把关",
        "prompt": "你是一个经验丰富的代码审查员。你的职责是：\n1. 审查代码的正确性、安全性和性能\n2. 提出改进建议\n3. 发现潜在的 bug 和漏洞\n4. 确保代码符合团队规范\n\n收到代码后，给出具体、中肯的审查意见。",
    },
    {
        "name": "devops",
        "role": "devops",
        "description": "运维工程师，负责部署和自动化",
        "prompt": "你是一个资深的 DevOps 工程师。你的职责是：\n1. 编写部署脚本和 CI/CD 配置\n2. 优化构建和部署流程\n3. 配置监控和日志系统\n4. 编写运维文档\n\n收到任务后，给出具体的实施方案。",
    },
]


def cmd_team(args) -> int:
    """Handle team command — multi-agent collaboration."""
    from h_agent.team.team import AgentTeam, AgentRole
    from h_agent.team.protocol import TeamProtocol

    action = args.team_action

    if action == "list":
        team = AgentTeam()
        members = team.list_members()
        if not members:
            print("No agents registered in the team.")
            print()
            print("Run 'h-agent team init' to initialize a default team.")
            print("Or register agents programmatically:")
            print("  from h_agent.team import AgentTeam, AgentRole")
            print("  team = AgentTeam()")
            print("  team.register('coder', AgentRole.CODER, my_handler)")
            return 0
        print(f"Team members ({len(members)}):")
        for m in members:
            status = "✅" if m["enabled"] else "❌"
            print(f"  {status} {m['name']} [{m['role']}] — {m['description']}")
        return 0

    if action == "status":
        team = AgentTeam()
        history = team.list_history(limit=5)
        pending = team.list_pending_tasks()
        print(f"Team: {team.team_id}")
        print(f"  Members: {len(team.members)}")
        print(f"  Pending tasks: {len(pending)}")
        print(f"  History entries: {len(history)}")
        return 0

    if action == "init":
        from h_agent.platform_utils import IS_WINDOWS, IS_MACOS, IS_LINUX
        print("Initializing team workspace...")
        if IS_MACOS:
            print("  Platform: macOS")
        elif IS_LINUX:
            print("  Platform: Linux")
        elif IS_WINDOWS:
            print("  Platform: Windows")
        print(f"  Team dir: {__import__('pathlib').Path.home() / '.h-agent' / 'team'}")

        team = AgentTeam(team_id="default")

        # Check if team already has members
        existing = team.list_members()
        if existing:
            print(f"\nTeam already has {len(existing)} registered agents.")
            print("Use 'h-agent team list' to see them.")
            _ok("Team already initialized.")
            return 0

        # Register default agents
        print("\nRegistering default agents:")
        role_map = {
            "planner": AgentRole.PLANNER,
            "coder": AgentRole.CODER,
            "reviewer": AgentRole.REVIEWER,
            "devops": AgentRole.DEVOPS,
        }
        for agent_def in DEFAULT_AGENTS:
            name = agent_def["name"]
            role = role_map.get(agent_def["role"], AgentRole.CODER)
            handler = _create_llm_handler(name, agent_def["prompt"])
            team.register(
                name,
                role,
                handler,
                description=agent_def["description"],
            )
            print(f"  ✅ {name} [{agent_def['role']}] — {agent_def['description']}")

        print()
        _ok("Team initialized with default agents!")
        print()
        print("Try it out:")
        print("  h-agent team list          # View all agents")
        print("  h-agent team talk planner '分析一下如何实现用户登录功能'")
        print("  h-agent team talk coder     '用 Python 实现一个快速排序'")
        return 0

    if action == "talk":
        team = AgentTeam()
        agent_name = args.agent
        message = args.message
        timeout = getattr(args, "timeout", 120)

        print(f"[Talking to {agent_name}] {message}")
        result = team.talk_to(agent_name, message, timeout=timeout)

        if result.success:
            print(f"\n[{agent_name}]:")
            print(result.content or "(no content)")
            return 0
        else:
            _err(f"Failed: {result.error}")
            return 1

    print("h-agent team - Multi-agent collaboration")
    print()
    print("Usage:")
    print("  h-agent team list              List team members")
    print("  h-agent team status           Show team status")
    print("  h-agent team init            Initialize team with default agents")
    print("  h-agent team talk <agent> <msg>  Talk to a specific agent")
    return 0


def cmd_agent(args) -> int:
    """Handle agent command — full-featured agent with IDENTITY/SOUL/USER.md."""
    action = args.agent_action

    if action == "list":
        agents = list_team_agents()
        if not agents:
            print("No agent profiles configured.")
            print()
            print("Create one with:")
            print("  h-agent agent init <name>")
            return 0
        print(f"Agent profiles ({len(agents)}):")
        for a in agents:
            status = "✅" if a["enabled"] else "❌"
            print(f"  {status} {a['name']} [{a['role']}] — {a['description']}")
        return 0

    if action == "init":
        name = args.name
        role = getattr(args, "role", "coordinator")
        description = getattr(args, "description", "")
        profile = init_agent_profile(name, role, description)
        print(f"Created agent profile: {name}")
        print(f"  Config dir: {profile.dir_path}")
        print()
        print("Edit the profile files:")
        print(f"  h-agent agent edit {name} identity  # Edit IDENTITY.md")
        print(f"  h-agent agent edit {name} soul      # Edit SOUL.md")
        print(f"  h-agent agent edit {name} user    # Edit USER.md")
        return 0

    if action == "show":
        name = args.name
        profile = AgentLoader.get_profile(name)
        if not profile.exists():
            print(f"Agent '{name}' does not exist.")
            print(f"Create with: h-agent agent init {name}")
            return 1
        config = AgentLoader.load_config(profile)
        print(f"Agent: {name}")
        print(f"  Role: {config.get('role', 'unknown')}")
        print(f"  Description: {config.get('description', '')}")
        print(f"  Enabled: {config.get('enabled', True)}")
        print(f"  Config dir: {profile.dir_path}")
        print()
        if profile.identity_path.exists():
            print("=== IDENTITY.md ===")
            print(profile.identity_path.read_text()[:500])
            print("...")
        if profile.soul_path.exists():
            print()
            print("=== SOUL.md ===")
            print(profile.soul_path.read_text()[:500])
            print("...")
        return 0

    if action == "edit":
        name = args.name
        file_type = args.file
        profile = AgentLoader.get_profile(name)
        if not profile.exists():
            print(f"Agent '{name}' does not exist.")
            return 1
        path_map = {
            "identity": profile.identity_path,
            "soul": profile.soul_path,
            "user": profile.user_path,
            "config": profile.config_path,
        }
        path = path_map.get(file_type)
        if not path.exists():
            print(f"File {file_type} does not exist for agent '{name}'.")
            return 1
        import subprocess, sys
        editor = os.environ.get("EDITOR", "nano" if sys.platform != "darwin" else "vim")
        subprocess.call([editor, str(path)])
        return 0

    if action == "sessions":
        name = args.name
        from h_agent.team.agent import AgentSessionManager
        mgr = AgentSessionManager(name)
        sessions = mgr.session_store.get_recent_sessions(limit=10)
        if not sessions:
            print(f"No sessions for agent '{name}'.")
            return 0
        print(f"Sessions for agent '{name}':")
        for s in sessions:
            print(f"  {s['session_id']}: {s.get('message_count', 0)} msgs, updated {s.get('updated_at', '')[:19]}")
        return 0

    print("h-agent agent - Full-featured agent management")
    print()
    print("Usage:")
    print("  h-agent agent list                 List all agent profiles")
    print("  h-agent agent init <name>         Create new agent profile")
    print("  h-agent agent show <name>         Show agent profile details")
    print("  h-agent agent edit <name> <file>   Edit agent file (identity/soul/user/config)")
    print("  h-agent agent sessions <name>      List agent sessions")
    return 0


def cmd_stop(args) -> int:
    """Handle stop command."""
    return stop_daemon()


def cmd_logs(args) -> int:
    """Handle logs command - view daemon log."""
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        # Try to find log in common locations
        possible = [
            daemon_pid_file().parent / "daemon.log",
            Path.home() / ".h-agent" / "daemon.log",
        ]
        for p in possible:
            if p.exists():
                log_path = p
                break

    if not log_path.exists():
        _err(f"No daemon log found at {log_path}")
        _err("Start the daemon first with 'h-agent start'")
        return 1

    lines = log_path.read_text(encoding="utf-8", errors="ignore")
    if args.tail:
        line_list = lines.split("\n")
        lines = "\n".join(line_list[-args.tail:])
    elif args.lines:
        line_list = lines.split("\n")
        lines = "\n".join(line_list[-args.lines:])

    print(lines)
    return 0


# ============================================================
# Session Management
# ============================================================

def get_session_manager() -> SessionManager:
    """Get session manager instance (singleton)."""
    return get_manager()


def cmd_session_list(args) -> int:
    """Handle session list command."""
    mgr = get_session_manager()
    sessions = mgr.list_sessions(filter_tag=args.tag, filter_group=args.group)

    if not sessions:
        if args.tag:
            print(f"No sessions with tag '{args.tag}'")
        elif args.group:
            print(f"No sessions in group '{args.group}'")
        else:
            print("No sessions found")
        return 0

    current = mgr.get_current()
    print(f"Sessions ({len(sessions)}):")
    for s in sessions:
        marker = " *" if s["session_id"] == current else ""
        name = s.get("name", "unnamed")
        count = s.get("message_count", 0)
        updated = s.get("updated_at", "")[:19]
        group = s.get("group")
        tags = s.get("tags", [])
        extra = ""
        if group:
            extra += f" [{group}]"
        if tags:
            extra += f" {' '.join('#'+t for t in tags)}"
        print(f"  {s['session_id']}  {name:<20} {count:>3} msgs  {updated}{extra}{marker}")
    return 0


def cmd_session_create(args) -> int:
    """Handle session create command."""
    mgr = get_session_manager()
    session = mgr.create_session(args.name, args.group)
    print(f"Created: {session['session_id']} ({session.get('name', 'unnamed')})")
    if args.group:
        print(f"  Group: {args.group}")
    return 0


def cmd_session_history(args) -> int:
    """Handle session history command."""
    mgr = get_session_manager()
    session_id = _find_session(mgr, args.session_id)

    if not session_id:
        _err(f"Session not found: {args.session_id}")
        return 1

    session = mgr.get_session(session_id)
    history = mgr.get_history(session_id)
    print(f"History for {session_id} ({session.get('name', 'unnamed')}, {len(history)} messages):")
    print("-" * 60)

    for msg in history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 200:
            content = content[:200] + "..."
        print(f"\n[{role.upper()}]")
        print(content)

    return 0


def cmd_session_delete(args) -> int:
    """Handle session delete command."""
    mgr = get_session_manager()
    session_id = _find_session(mgr, args.session_id)

    if not session_id:
        _err(f"Session not found: {args.session_id}")
        return 1

    if mgr.delete_session(session_id):
        _ok(f"Deleted: {session_id}")
        return 0
    _err(f"Failed to delete: {session_id}")
    return 1


def cmd_session_search(args) -> int:
    """Handle session search command."""
    mgr = get_session_manager()
    results = mgr.search(args.query)

    if not results:
        print(f"No sessions matching: {args.query}")
        return 0

    print(f"Found {len(results)} session(s):")
    for s in results:
        group = s.get("group", "")
        tags = s.get("tags", [])
        extra = ""
        if group:
            extra += f" [{group}]"
        if tags:
            extra += f" {' '.join('#'+t for t in tags)}"
        print(f"  {s['session_id']}  {s.get('name', 'unnamed'):<20}  updated: {s.get('updated_at', '')[:19]}{extra}")
    return 0


def cmd_session_rename(args) -> int:
    """Handle session rename command."""
    mgr = get_session_manager()
    session_id = _find_session(mgr, args.session_id)

    if not session_id:
        _err(f"Session not found: {args.session_id}")
        return 1

    if mgr.rename_session(session_id, args.name):
        _ok(f"Renamed to: {args.name}")
        return 0
    _err("Rename failed")
    return 1


# ---- Tags ----

def cmd_session_tag(args) -> int:
    """Handle session tag command."""
    mgr = get_session_manager()
    action = args.tag_action

    if action == "list":
        tags = mgr.list_tags()
        if not tags:
            print("No tags found")
        else:
            print(f"Tags ({len(tags)}):")
            for tag, count in sorted(tags.items()):
                print(f"  #{tag:<20} {count} session(s)")
        return 0

    if action == "add":
        session_id = _find_session(mgr, args.session_id)
        if not session_id:
            _err(f"Session not found: {args.session_id}")
            return 1
        if mgr.add_tag(session_id, args.tag):
            _ok(f"Added tag '#{args.tag}' to {session_id}")
            return 0
        _err("Failed to add tag")
        return 1

    if action == "remove":
        session_id = _find_session(mgr, args.session_id)
        if not session_id:
            _err(f"Session not found: {args.session_id}")
            return 1
        if mgr.remove_tag(session_id, args.tag):
            _ok(f"Removed tag '#{args.tag}' from {session_id}")
            return 0
        _err("Failed to remove tag")
        return 1

    if action == "get":
        session_id = _find_session(mgr, args.session_id)
        if not session_id:
            _err(f"Session not found: {args.session_id}")
            return 1
        tags = mgr.get_session_tags(session_id)
        print(f"Tags for {session_id}:")
        if tags:
            print("  " + " ".join(f"#{t}" for t in tags))
        else:
            print("  (no tags)")
        return 0

    return 0


# ---- Groups ----

def cmd_session_group(args) -> int:
    """Handle session group command."""
    mgr = get_session_manager()
    action = args.group_action

    if action == "list":
        groups = mgr.list_groups()
        if not groups:
            print("No groups found")
        else:
            print(f"Groups ({len(groups)}):")
            for g, count in sorted(groups.items()):
                print(f"  {g:<20} {count} session(s)")
        return 0

    if action == "set":
        session_id = _find_session(mgr, args.session_id)
        if not session_id:
            _err(f"Session not found: {args.session_id}")
            return 1
        group = args.group_name if args.group_name else None
        if mgr.set_group(session_id, group):
            if group:
                _ok(f"Set group '{group}' for {session_id}")
            else:
                _ok(f"Cleared group for {session_id}")
            return 0
        _err("Failed to set group")
        return 1

    if action == "sessions":
        sessions = mgr.get_sessions_in_group(args.group_name)
        if not sessions:
            print(f"No sessions in group '{args.group_name}'")
        else:
            print(f"Sessions in '{args.group_name}' ({len(sessions)}):")
            for s in sessions:
                print(f"  {s['session_id']}  {s.get('name', 'unnamed'):<20}")
        return 0

    return 0


# ============================================================
# Memory
# ============================================================

def cmd_memory(args) -> int:
    """Handle memory command."""
    from h_agent.memory.long_term import (
        remember, recall, forget, list_memories,
        search_memory, memory_dump, memory_stats, MemoryType
    )
    from h_agent.memory.retriever import MemoryRetriever

    action = args.memory_action

    # ---- list ----
    if action == "list":
        mem_type = args.list_type
        stats = memory_stats()
        print("=== Memory Stats ===")
        total = 0
        for t, count in sorted(stats.items()):
            if t == "all":
                continue
            marker = " ← filtered" if mem_type and mem_type != "all" and t != mem_type else ""
            print(f"  {t}: {count} entries{marker}")
            total += count
        print(f"  TOTAL: {total}")
        print()
        entries = list_memories(mem_type) if mem_type and mem_type != "all" else None

        def print_entries(entries_or_dict, type_label=""):
            if isinstance(entries_or_dict, list):
                # Flat list of entries
                for e in entries_or_dict:
                    t = e.get("type", type_label)
                    key = e.get("key", "")
                    value = e.get("value", "")
                    reason = e.get("reason", "")
                    tags = e.get("tags", [])
                    ts = e.get("created_at", "")[:19]
                    tag_str = f" [{', '.join('#'+t for t in tags)}]" if tags else ""
                    reason_str = f" reason: {reason}" if reason else ""
                    print(f"  [{t}] {key}: {value}{reason_str}{tag_str} ({ts})")
            elif isinstance(entries_or_dict, dict):
                # Dict from list_memories when no filter
                for t, ents in entries_or_dict.items():
                    if not ents:
                        continue
                    print(f"\n## {t.upper()}")
                    print_entries(ents, t)

        if mem_type and mem_type != "all":
            entries = list_memories(mem_type)
            print_entries(entries, type_label=mem_type)
        else:
            # Print all types
            for t in ["user", "project", "decision", "fact", "error"]:
                entries = list_memories(t)
                if entries:
                    print(f"\n## {t.upper()}")
                    print_entries(entries, t)
        return 0

    # ---- add ----
    if action == "add":
        mem_type = args.add_type
        key = args.add_key
        value = args.add_value
        reason = args.reason
        tags = args.tags.split(",") if args.tags else None

        valid_types = ["user", "project", "decision", "fact", "error"]
        if mem_type not in valid_types:
            _err(f"Invalid type '{mem_type}'. Choose from: {', '.join(valid_types)}")
            return 1

        if not key:
            _err("Key cannot be empty")
            return 1

        if remember(mem_type, key, value, reason=reason, tags=tags):
            _ok(f"Stored: [{mem_type}] {key} = {value}")
            if reason:
                print(f"  reason: {reason}")
            if tags:
                print(f"  tags: {', '.join('#'+t for t in tags)}")
        else:
            _err("Failed to store memory")
            return 1
        return 0

    # ---- get ----
    if action == "get":
        key = args.get_key
        found = False
        for mem_type in ["user", "project", "decision", "fact", "error"]:
            entry = recall(mem_type, key)
            if entry is not None:
                print(f"[{mem_type}] {key} = {entry}")
                found = True
        if not found:
            _err(f"Memory not found: {key}")
            return 1
        return 0

    # ---- delete ----
    if action == "delete":
        mem_type = args.delete_type
        key = args.delete_key
        valid_types = ["user", "project", "decision", "fact", "error"]
        if mem_type not in valid_types:
            _err(f"Invalid type '{mem_type}'. Choose from: {', '.join(valid_types)}")
            return 1
        if forget(mem_type, key):
            _ok(f"Deleted: [{mem_type}] {key}")
        else:
            _err(f"Memory not found: [{mem_type}] {key}")
            return 1
        return 0

    # ---- search ----
    if action == "search":
        query = args.search_query
        if not query:
            _err("Search query is required")
            return 1

        # Search long-term memories
        lt_results = search_memory(query)
        if lt_results:
            print(f"\n=== Long-term Memory Results ({len(lt_results)}) ===")
            for r in lt_results[:10]:
                t = r.get("type", "?")
                key = r.get("key", "")
                value = r.get("value", "")
                reason = r.get("reason", "")
                reason_str = f" — {reason}" if reason else ""
                print(f"  [{t}] {key}: {value}{reason_str}")
        else:
            print("No long-term memory results.")

        # Search sessions
        if args.search_sessions:
            retriever = MemoryRetriever()
            session_results = retriever.search_sessions(query, days_back=args.days or 30)
            if session_results:
                print(f"\n=== Session History Results ({len(session_results)}) ===")
                for r in session_results[:5]:
                    sid = r.get("session_id", "?")
                    excerpts = r.get("excerpts", [])
                    print(f"  Session {sid} (score={r.get('score', 0)}):")
                    for ex in excerpts[:2]:
                        print(f"    ...{ex}...")
            else:
                print("\nNo session history results.")

        # Search summaries
        if args.search_summaries:
            retriever = MemoryRetriever()
            summary_results = retriever.search_summaries(query)
            if summary_results:
                print(f"\n=== Summary Results ({len(summary_results)}) ===")
                for r in summary_results[:5]:
                    sid = r.get("session_id", "?")
                    print(f"  Session {sid}:")
                    print(f"    {r.get('excerpt', '')[:200]}")
            else:
                print("\nNo summary results.")
        return 0

    # ---- dump ----
    if action == "dump":
        mem_type = args.dump_type if args.dump_type != "all" else None
        text = memory_dump(mem_type=mem_type)
        print(text)
        return 0

    # Default help
    print("h-agent memory - Long-term memory management")
    print()
    print("Usage:")
    print("  h-agent memory list [--type TYPE]           List memories")
    print("  h-agent memory add <TYPE> <KEY> <VALUE>     Store a memory")
    print("  h-agent memory get <KEY>                    Get a memory by key")
    print("  h-agent memory delete <TYPE> <KEY>          Delete a memory")
    print("  h-agent memory search <QUERY>               Search memories")
    print("  h-agent memory dump [--type TYPE]          Dump all as text")
    print()
    print("Memory types: user, project, decision, fact, error")
    print()
    print("Examples:")
    print("  h-agent memory add user language Chinese")
    print("  h-agent memory add decision use_sqlite 'Simplicity' --reason 'MVP phase'")
    print("  h-agent memory add project framework FastAPI --tags api,python")
    print("  h-agent memory search authentication")
    print("  h-agent memory dump --type decision")
    return 0


# ============================================================
# RAG
# ============================================================

def cmd_rag(args) -> int:
    """Handle rag command."""
    from h_agent.features.rag import get_or_create_rag, HAS_CHROMA

    action = args.rag_action

    if action == "index":
        root = os.path.abspath(args.directory) if args.directory else os.getcwd()
        print(f"Indexing codebase at: {root}")

        rag = get_or_create_rag(root)

        if not HAS_CHROMA:
            _warn("chromadb not installed. Vector search unavailable. Install with: pip install h-agent[rag]")

        rag.index_codebase(verbose=True)
        _ok("Indexing complete!")
        return 0

    if action == "search":
        if not args.query:
            _err("Search query is required. Usage: h-agent rag search <query>")
            return 1

        # Use current directory unless specified
        root = os.path.abspath(args.directory) if args.directory else os.getcwd()
        rag = get_or_create_rag(root)

        if not rag.index.files:
            _err("Codebase not indexed. Run 'h-agent rag index' first.")
            return 1

        results = rag.search(args.query, n=args.limit)

        print(f"\n=== Search results for: {args.query} ===\n")

        if results["symbols"]:
            print(f"📌 Symbols ({len(results['symbols'])}):")
            for sym in results["symbols"][:10]:
                print(f"  [{sym['kind']}] {sym['name']} @ {sym['file']}:{sym['line']}")
                if sym.get("snippet"):
                    snippet = sym["snippet"][:60].replace("\n", " ")
                    print(f"      {snippet}")
            print()

        if results["documents"]:
            print(f"📄 Code chunks ({len(results['documents'])}):")
            for doc in results["documents"][:5]:
                lang = doc.get("metadata", {}).get("language", "")
                file_ = doc.get("id", "")
                score = doc.get("score", 0)
                content = doc.get("content", "")[:200].replace("\n", " ")
                print(f"  [{lang}] {file_} (relevance: {score:.2f})")
                print(f"    {content}...")
                print()
        elif not results["symbols"]:
            print("No results found.")

        return 0

    if action == "stats":
        root = os.path.abspath(args.directory) if args.directory else os.getcwd()
        rag = get_or_create_rag(root)
        stats = rag.index.get_stats()

        print("Codebase Index Statistics:")
        print(f"  Root directory: {stats.get('root_dir', root)}")
        print(f"  Total files: {stats.get('files', 0)}")
        print(f"  Total symbols: {stats.get('symbols', 0)}")
        print(f"  Languages: {stats.get('languages', {})}")

        if rag.vector_store:
            print(f"  Vector chunks: {rag.vector_store.count()}")

        if rag.vector_store and HAS_CHROMA:
            print(f"  ChromaDB: ✅ available")
        else:
            print(f"  ChromaDB: ❌ not available (pip install chromadb)")

        return 0

    # Default: print rag help
    print("h-agent rag - Codebase RAG commands")
    print()
    print("Usage:")
    print("  h-agent rag index [--directory DIR]     Index a codebase")
    print("  h-agent rag search <query> [--limit N]  Search indexed codebase")
    print("  h-agent rag stats [--directory DIR]     Show index statistics")
    return 0


# ============================================================
# Run / Chat
# ============================================================

def cmd_run(args) -> int:
    """Handle run command - single prompt execution."""
    from openai import OpenAI

    prompt = args.prompt
    session_id = args.session

    mgr = get_session_manager()

    if session_id:
        found_id = _find_session(mgr, session_id)
        if not found_id:
            _err(f"Session not found: {session_id}")
            return 1
        session_id = found_id
    else:
        if not mgr.get_current():
            session = mgr.create_session("default")
            session_id = session["session_id"]
        else:
            session_id = mgr.get_current()

    mgr.set_current(session_id)
    messages = mgr.get_history(session_id)
    messages.append({"role": "user", "content": prompt})
    mgr.add_message(session_id, "user", prompt)

    system_prompt = f"You are a helpful AI assistant. Current directory: {os.getcwd()}"
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=api_messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )

            message = response.choices[0].message

            if message.content:
                print(message.content)

            content = message.content or ""
            tool_calls = message.tool_calls

            mgr.add_message(session_id, "assistant", content)

            if not tool_calls:
                break

            for tool_call in tool_calls:
                print(f"\n$ {tool_call.function.name}(...)", file=sys.stderr)
                result = execute_tool_call(tool_call)
                if len(result) > 50000:
                    result = result[:25000] + "\n...[truncated]\n" + result[-25000:]
                mgr.add_message(session_id, "tool", f"[{tool_call.function.name}] {result}")
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            api_messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

        except Exception as e:
            _err(str(e))
            return 1

    return 0


def cmd_chat(args) -> int:
    """Handle chat command - interactive mode."""
    from openai import OpenAI

    session_id = args.session
    mgr = get_session_manager()

    if session_id:
        found_id = _find_session(mgr, session_id)
        if not found_id:
            _err(f"Session not found: {session_id}")
            return 1
        session_id = found_id
        mgr.set_current(session_id)
    else:
        if not mgr.get_current():
            session = mgr.create_session("chat")
            session_id = session["session_id"]
        else:
            session_id = mgr.get_current()

    print(f"\033[36mh_agent - Chat Mode\033[0m")
    print(f"Session: {session_id}")
    print(f"Model: {MODEL}")
    print(f"Type 'q', 'exit' or press Enter to quit")
    print("=" * 50)

    messages = mgr.get_history(session_id)

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    system_prompt = f"You are a helpful AI assistant. Current directory: {os.getcwd()}"

    while True:
        try:
            query = input("\n\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if query.lower() in ("q", "exit", ""):
            print("Goodbye!")
            break

        if query.lower() == "/clear":
            messages = []
            print("History cleared")
            continue

        if query.lower() == "/history":
            print(f"Messages so far: {len(mgr.get_history(session_id))}")
            continue

        messages.append({"role": "user", "content": query})
        mgr.add_message(session_id, "user", query)
        api_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            while True:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                )

                message = response.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": message.tool_calls,
                })

                if not message.tool_calls:
                    if message.content:
                        print(f"\n{message.content}")
                        mgr.add_message(session_id, "assistant", message.content)
                    break

                for tool_call in message.tool_calls:
                    args_dict = json.loads(tool_call.function.arguments)
                    key = list(args_dict.keys())[0] if args_dict else ""
                    val = args_dict.get(key, "")[:60] if key else ""
                    print(f"\n\033[33m$ {tool_call.function.name}({val})\033[0m", file=sys.stderr)
                    result = execute_tool_call(tool_call)
                    print(f"\033[90m{result[:500]}{'...' if len(result) > 500 else ''}\033[0m", file=sys.stderr)
                    if len(result) > 50000:
                        result = result[:25000] + "\n...[truncated]\n" + result[-25000:]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                    mgr.add_message(session_id, "tool", f"[{tool_call.function.name}] {result}")

                api_messages = [{"role": "system", "content": system_prompt}] + messages

        except Exception as e:
            print(f"\033[31mError: {e}\033[0m")

    return 0


# ============================================================
# Config
# ============================================================

def cmd_config(args) -> int:
    """Handle config command."""
    # Import refreshed config functions
    from importlib import reload
    from h_agent.core import config as config_module
    reload(config_module)

    if args.list_all:
        all_cfg = config_module.list_all_config()
        print("=== All Config Profiles ===")
        print(f"Current profile: {all_cfg['current_profile']}")
        print(f"Available profiles: {', '.join(all_cfg['profiles'].keys())}")
        for name, cfg in all_cfg["profiles"].items():
            marker = " ← current" if name == all_cfg["current_profile"] else ""
            print(f"\n[{name}]{marker}")
            for k, v in cfg.items():
                print(f"  {k}: {v}")
        return 0

    if args.show:
        config = config_module.list_config()
        profile = config_module.get_current_profile()
        print(f"=== h-agent Configuration (profile: {profile}) ===")
        if "openai_api_key" in config:
            print(f"  OPENAI_API_KEY: {config['openai_api_key']}")
        if "openai_base_url" in config:
            print(f"  OPENAI_BASE_URL: {config['openai_base_url']}")
        if "model_id" in config:
            print(f"  MODEL_ID: {config['model_id']}")
        if "context_safe_limit" in config:
            print(f"  CONTEXT_SAFE_LIMIT: {config['context_safe_limit']}")
        if "max_tool_output" in config:
            print(f"  MAX_TOOL_OUTPUT: {config['max_tool_output']}")
        if "tool_timeout" in config:
            print(f"  TOOL_TIMEOUT: {config['tool_timeout']}")
        print()
        print(f"Config dir: {config_module.AGENT_CONFIG_DIR}")
        print(f"Config file: {config_module._get_profile_config_path(profile)}")
        return 0

    if args.profile_delete:
        name = args.profile_delete
        if name == "default":
            _err("Cannot delete the 'default' profile")
            return 1
        if config_module.delete_profile(name):
            _ok(f"Deleted profile: {name}")
        else:
            _err(f"Failed to delete profile '{name}'")
        return 0

    if args.profile_create:
        name = args.profile_create
        if config_module.create_profile(name):
            _ok(f"Created profile: {name}")
        else:
            _err(f"Profile '{name}' already exists")
        return 0

    if args.profile_switch:
        profile = args.profile_switch
        if config_module.set_current_profile(profile):
            _ok(f"Switched to profile: {profile}")
        else:
            _err(f"Profile '{profile}' not found")
        return 0

    if args.set_api_key:
        key = args.set_api_key
        if key == "__prompt__":
            import getpass
            key = getpass.getpass("Enter API key: ")
        config_module.set_config("OPENAI_API_KEY", key, secure=True)
        _ok("API key saved.")
        return 0

    if args.clear_key:
        config_module.clear_secret("OPENAI_API_KEY")
        _ok("API key cleared.")
        return 0

    if args.set_base_url:
        config_module.set_config("OPENAI_BASE_URL", args.set_base_url)
        print(f"Base URL set to: {args.set_base_url}")
        return 0

    if args.set_model:
        config_module.set_config("MODEL_ID", args.set_model)
        print(f"Model set to: {args.set_model}")
        return 0

    if args.export:
        path = config_module.export_config()
        _ok(f"Exported to: {path}")
        return 0

    if args.import_cfg:
        path = Path(args.import_cfg)
        if not path.exists():
            _err(f"File not found: {path}")
            return 1
        if config_module.import_config(path):
            _ok(f"Imported from: {path}")
        else:
            _err("Import failed")
        return 0

    print("h-agent config - Configuration management")
    print()
    print("Usage:")
    print("  h-agent config --show              Show current config")
    print("  h-agent config --list-all         Show all profiles")
    print("  h-agent config --profile <name>    Switch to profile")
    print("  h-agent config --profile create <name>  Create new profile")
    print("  h-agent config --profile delete <name>  Delete a profile")
    print("  h-agent config --api-key KEY       Set API key")
    print("  h-agent config --api-key __prompt__  Set API key (prompt)")
    print("  h-agent config --clear-key         Remove stored API key")
    print("  h-agent config --base-url URL      Set API base URL")
    print("  h-agent config --model MODEL       Set model ID")
    print("  h-agent config --export            Export config to JSON")
    print("  h-agent config --import FILE       Import config from JSON")
    return 0


# ============================================================
# Template Management
# ============================================================

TEMPLATE_DIR = Path.home() / ".h-agent" / "templates"


def _load_template(name: str) -> Optional[dict]:
    """Load a template by name."""
    import yaml
    template_path = TEMPLATE_DIR / f"{name}.yaml"
    if not template_path.exists():
        return None
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _list_templates() -> list:
    """List all available templates."""
    import yaml
    templates = []
    if not TEMPLATE_DIR.exists():
        return templates
    for f in sorted(TEMPLATE_DIR.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
                templates.append({
                    "name": f.stem,
                    "display_name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "version": data.get("version", "1.0"),
                    "path": f,
                })
        except Exception:
            templates.append({
                "name": f.stem,
                "display_name": f.stem,
                "description": "(parse error)",
                "version": "?",
                "path": f,
            })
    return templates


def cmd_template(args) -> int:
    """Handle template command."""
    action = args.template_action

    if action == "list":
        templates = _list_templates()
        if not templates:
            print("No templates found.")
            print(f"  Templates directory: {TEMPLATE_DIR}")
            print("  Create templates as .yaml files in that directory.")
            return 0
        print(f"Available templates ({len(templates)}):")
        print()
        for t in templates:
            print(f"  {t['name']}")
            print(f"    Name: {t['display_name']}")
            print(f"    Description: {t['description']}")
            print(f"    Version: {t['version']}")
            print()
        return 0

    if action == "apply":
        name = args.template_name
        template = _load_template(name)
        if not template:
            _err(f"Template not found: {name}")
            _err(f"Available templates: {', '.join(t['name'] for t in _list_templates())}")
            return 1

        print(f"Applying template: {template.get('name', name)}")
        print(f"Description: {template.get('description', '')}")
        print()

        # Apply model if specified
        if "recommended_model" in template:
            model = template["recommended_model"]
            print(f"Setting model to: {model}")
            from h_agent.core import config as config_module
            from importlib import reload
            reload(config_module)
            config_module.set_config("MODEL_ID", model)

        # Apply config overrides
        if "config" in template:
            from importlib import reload as reload_module
            from h_agent.core import config as config_module
            reload_module(config_module)
            for key, value in template["config"].items():
                config_module.set_config(key.upper(), str(value))
                print(f"  Config {key}: {value}")

        _ok(f"Template '{name}' applied successfully!")
        print()
        print("Note: System prompt will be loaded when you start a new session.")
        return 0

    if action == "show":
        name = args.template_name
        template = _load_template(name)
        if not template:
            _err(f"Template not found: {name}")
            return 1
        print(f"=== Template: {template.get('name', name)} ===")
        print(f"Description: {template.get('description', '')}")
        print(f"Version: {template.get('version', '1.0')}")
        print()
        print("System Prompt:")
        print("-" * 40)
        print(template.get("system_prompt", "(none)"))
        print("-" * 40)
        print()
        print("Tools:")
        for tool in template.get("tools", []):
            print(f"  - {tool}")
        print()
        if "recommended_model" in template:
            print(f"Recommended Model: {template['recommended_model']}")
        if "config" in template:
            print("Config overrides:")
            for k, v in template["config"].items():
                print(f"  {k}: {v}")
        return 0

    if action == "create":
        name = args.template_name
        template_path = TEMPLATE_DIR / f"{name}.yaml"
        if template_path.exists():
            _err(f"Template already exists: {name}")
            return 1
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        # Copy from example
        example = """name: {name}
description: Your template description here
version: "1.0"

system_prompt: |
  Define your agent's system prompt here.

tools:
  - read
  - write
  - bash

recommended_model: gpt-4o-mini

config:
  max_tool_output: 50000
  context_safe_limit: 120000
"""
        template_path.write_text(example.format(name=name), encoding="utf-8")
        _ok(f"Created template: {name}")
        print(f"  Edit: {template_path}")
        return 0

    if action == "delete":
        name = args.template_name
        template_path = TEMPLATE_DIR / f"{name}.yaml"
        if not template_path.exists():
            _err(f"Template not found: {name}")
            return 1
        template_path.unlink()
        _ok(f"Deleted template: {name}")
        return 0

    print("h-agent template - Agent template management")
    print()
    print("Usage:")
    print("  h-agent template list                    List all templates")
    print("  h-agent template show <name>            Show template details")
    print("  h-agent template apply <name>           Apply a template")
    print("  h-agent template create <name>          Create new template")
    print("  h-agent template delete <name>          Delete a template")
    print()
    print(f"Template directory: {TEMPLATE_DIR}")
    return 0


# ============================================================
# Model Management
# ============================================================

MODELS_CONFIG = Path.home() / ".h-agent" / "models.yaml"


def _load_models_config() -> dict:
    """Load models configuration."""
    import yaml
    if MODELS_CONFIG.exists():
        with open(MODELS_CONFIG, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def cmd_model(args) -> int:
    """Handle model command."""
    action = args.model_action

    models_cfg = _load_models_config()
    models = models_cfg.get("models", {})
    providers = models_cfg.get("providers", {})

    if action == "list":
        if not models:
            print("No models configured.")
            print(f"  Models config: {MODELS_CONFIG}")
            return 0

        # Group by provider
        by_provider = {}
        for model_id, model_cfg in models.items():
            provider = model_cfg.get("provider", "unknown")
            by_provider.setdefault(provider, []).append((model_id, model_cfg))

        print("Available models:")
        print()

        for provider, model_list in sorted(by_provider.items()):
            provider_info = providers.get(provider, {})
            provider_name = provider_info.get("name", provider)
            print(f"[{provider_name}]")
            for model_id, cfg in model_list:
                desc = cfg.get("description", "")
                context = cfg.get("context_window", "?")
                print(f"  {model_id}")
                if desc:
                    print(f"    {desc}")
                print(f"    Context: {context}")
            print()

        # Show current model
        from importlib import reload
        from h_agent.core import config as config_module
        reload(config_module)
        current = config_module.MODEL_ID
        print(f"Current model: {current}")
        return 0

    if action == "switch":
        model_id = args.model_name
        if model_id not in models:
            _err(f"Unknown model: {model_id}")
            print("Available models:")
            for mid in models:
                print(f"  - {mid}")
            return 1

        model_cfg = models[model_id]
        base_url = model_cfg.get("base_url", "")
        provider = model_cfg.get("provider", "")

        print(f"Switching to model: {model_id}")
        print(f"  Provider: {provider}")
        print(f"  Base URL: {base_url}")

        from importlib import reload
        from h_agent.core import config as config_module
        reload(config_module)

        # Update model
        config_module.set_config("MODEL_ID", model_id)

        # Update base URL if specified
        if base_url:
            config_module.set_config("OPENAI_BASE_URL", base_url)

        _ok(f"Model switched to: {model_id}")
        print()
        print("Note: If the provider requires an API key, make sure it's configured.")
        return 0

    if action == "info":
        model_id = args.model_name
        if model_id not in models:
            _err(f"Unknown model: {model_id}")
            return 1

        cfg = models[model_id]
        print(f"=== Model: {model_id} ===")
        print(f"Name: {cfg.get('name', model_id)}")
        print(f"Provider: {cfg.get('provider', 'unknown')}")
        print(f"Description: {cfg.get('description', 'N/A')}")
        print(f"API Type: {cfg.get('api_type', 'openai')}")
        print(f"Base URL: {cfg.get('base_url', 'N/A')}")
        print(f"Max Tokens: {cfg.get('max_tokens', 'N/A')}")
        print(f"Context Window: {cfg.get('context_window', 'N/A')}")
        return 0

    if action == "add":
        # Interactive add model
        print("Add new model - feature coming soon")
        print(f"  Edit models config: {MODELS_CONFIG}")
        return 0

    print("h-agent model - Model management")
    print()
    print("Usage:")
    print("  h-agent model list                    List all available models")
    print("  h-agent model switch <model>          Switch to a different model")
    print("  h-agent model info <model>           Show model details")
    print()
    print(f"Models config: {MODELS_CONFIG}")
    return 0


# ============================================================
# Plugin Management
# ============================================================

def cmd_plugin(args) -> int:
    """Handle plugin command."""
    from importlib import reload
    from h_agent import plugins as plugins_module
    reload(plugins_module)

    action = args.plugin_action

    if action == "list":
        plugins_module.load_all_plugins()
        plugins = plugins_module.list_plugins()
        if not plugins:
            print("No plugins loaded.")
            print("  Built-in plugin 'web_tools' provides web_fetch and web_search.")
            print("  Place .py files in h_agent/plugins/ to load custom plugins.")
            return 0
        print(f"Plugins ({len(plugins)}):")
        for p in plugins:
            status = "✅ enabled" if p.enabled else "❌ disabled"
            tools = ", ".join(t["function"]["name"] for t in p.tools) if p.tools else "(no tools)"
            print(f"  {p.name} v{p.version} [{status}]")
            print(f"    {p.description}")
            if p.tools:
                print(f"    Tools: {tools}")
        return 0

    if action == "enable":
        plugins_module.load_all_plugins()
        name = args.plugin_name
        if plugins_module.enable_plugin(name):
            _ok(f"Enabled plugin: {name}")
        else:
            _err(f"Plugin not found: {name}")
        return 0

    if action == "disable":
        plugins_module.load_all_plugins()
        name = args.plugin_name
        if plugins_module.disable_plugin(name):
            _ok(f"Disabled plugin: {name}")
        else:
            _err(f"Plugin not found: {name}")
        return 0

    if action == "install":
        url = args.plugin_url
        if not url:
            _err("Plugin URL required: h-agent plugin install <url>")
            return 1
        print(f"Installing plugin from: {url}")
        # Simple git clone or download
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "h-agent/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
            # Try to detect if it's a git URL
            if url.endswith(".git"):
                import subprocess
                name = url.split("/")[-1].replace(".git", "")
                dest = plugins_module.PLUGIN_DIR / name
                print(f"Cloning into {dest}...")
                r = subprocess.run(["git", "clone", url, str(dest)],
                                   capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    _ok(f"Installed plugin: {name}")
                else:
                    _err(f"Git clone failed: {r.stderr}")
                return 0
            # Try to save as plugin file
            name = url.split("/")[-1]
            if not name.endswith(".py"):
                name += ".py"
            dest = plugins_module.PLUGIN_DIR / name
            dest.write_bytes(content)
            _ok(f"Installed plugin: {dest.name}")
            return 0
        except Exception as e:
            _err(f"Install failed: {e}")
            return 1

    if action == "uninstall":
        name = args.plugin_name
        plugins_module.load_all_plugins()
        plugin = plugins_module.get_plugin(name)
        if not plugin or not plugin.path:
            _err(f"Plugin not found: {name}")
            return 1
        try:
            if plugin.path.is_file():
                plugin.path.unlink()
            elif plugin.path.is_dir():
                import shutil
                shutil.rmtree(plugin.path)
            _ok(f"Uninstalled plugin: {name}")
        except OSError as e:
            _err(f"Failed to uninstall: {e}")
        return 0

    if action == "info":
        plugins_module.load_all_plugins()
        plugin = plugins_module.get_plugin(args.plugin_name)
        if not plugin:
            _err(f"Plugin not found: {args.plugin_name}")
            return 1
        print(f"Plugin: {plugin.name}")
        print(f"  Version: {plugin.version}")
        print(f"  Author: {plugin.author}")
        print(f"  Description: {plugin.description}")
        print(f"  Status: {'enabled' if plugin.enabled else 'disabled'}")
        print(f"  Path: {plugin.path}")
        print(f"  Tools ({len(plugin.tools)}):")
        for t in plugin.tools:
            print(f"    - {t['function']['name']}: {t['function'].get('description', '')}")
        return 0

    print("h-agent plugin - Plugin management")
    print()
    print("Usage:")
    print("  h-agent plugin list                       List all plugins")
    print("  h-agent plugin info <name>                Show plugin details")
    print("  h-agent plugin enable <name>              Enable a plugin")
    print("  h-agent plugin disable <name>             Disable a plugin")
    print("  h-agent plugin install <url>              Install plugin from URL")
    print("  h-agent plugin uninstall <name>          Uninstall a plugin")
    return 0


# ============================================================
# Skills
# ============================================================

def cmd_skill(args) -> int:
    """Handle skill command."""
    from importlib import reload
    from h_agent import skills as skills_module
    reload(skills_module)

    action = args.skill_action

    if action == "list":
        skills_module.load_all_skills()
        skills = skills_module.list_skills(include_all=getattr(args, 'all', False))
        if not skills:
            print("No skills loaded.")
            print("  Built-in skills: office (Word, Excel, PowerPoint)")
            print("                    outlook (Mail, Calendar, Contacts)")
            print("  Place skill packages in h_agent/skills/ to load custom skills.")
            return 0
        print(f"Skills ({len(skills)}):")
        for s in skills:
            platform = ", ".join(s.platforms)
            deps_status = []
            for dep, ok in s.check_dependencies().items():
                deps_status.append(f"{dep}: {'✅' if ok else '❌'}")
            status = "✅ enabled" if s.enabled else "❌ disabled"
            available = "✅ available" if s.is_available() else "❌ unavailable"
            print(f"  {s.name} v{s.version} [{status}] [{available}]")
            print(f"    {s.description}")
            print(f"    Category: {s.category} | Platform: {platform}")
            print(f"    Dependencies: {', '.join(deps_status)}")
            if s.tools:
                tools = ", ".join(t.get("function", {}).get("name", "unknown") for t in s.tools)
                print(f"    Tools: {tools}")
        return 0

    if action == "info":
        skills_module.load_all_skills()
        skill = skills_module.get_skill(args.skill_name)
        if not skill:
            _err(f"Skill not found: {args.skill_name}")
            return 1
        print(f"Skill: {skill.name}")
        print(f"  Version: {skill.version}")
        print(f"  Author: {skill.author}")
        print(f"  Description: {skill.description}")
        print(f"  Category: {skill.category}")
        print(f"  Platforms: {', '.join(skill.platforms)}")
        print(f"  Status: {'enabled' if skill.enabled else 'disabled'}")
        print(f"  Installed: {skill.installed}")
        if skill.path:
            print(f"  Path: {skill.path}")
        if skill.pip_package:
            print(f"  Pip Package: {skill.pip_package}")
        print(f"  Dependencies:")
        for dep, ok in skill.check_dependencies().items():
            status = "✅ installed" if ok else "❌ missing"
            print(f"    - {dep}: {status}")
        print(f"  Functions ({len(skill.functions)}):")
        for func_name in skill.functions:
            print(f"    - {func_name}")
        return 0

    if action == "enable":
        skills_module.load_all_skills()
        name = args.skill_name
        if skills_module.enable_skill(name):
            _ok(f"Enabled skill: {name}")
        else:
            _err(f"Skill not found: {name}")
        return 0

    if action == "disable":
        skills_module.load_all_skills()
        name = args.skill_name
        if skills_module.disable_skill(name):
            _ok(f"Disabled skill: {name}")
        else:
            _err(f"Skill not found: {name}")
        return 0

    if action == "install":
        name = args.skill_name
        package = getattr(args, 'package', None)
        print(f"Installing skill: {name}")
        if skills_module.install_skill(name, package):
            _ok(f"Installed skill: {name}")
            return 0
        else:
            _err(f"Failed to install skill: {name}")
            return 1

    if action == "uninstall":
        name = args.skill_name
        if skills_module.uninstall_skill(name):
            _ok(f"Uninstalled skill: {name}")
            return 0
        else:
            _err(f"Failed to uninstall skill: {name}")
            return 1

    if action == "run":
        skills_module.load_all_skills()
        name = args.skill_name
        func_name = args.function_name
        skill_args = args.args

        try:
            result = skills_module.call_skill_function(name, func_name, *skill_args)
            if result is not None:
                print(result)
            return 0
        except ValueError as e:
            _err(str(e))
            return 1
        except Exception as e:
            _err(f"Error running {name}.{func_name}: {e}")
            return 1

    print("h-agent skill - Skill management")
    print()
    print("Usage:")
    print("  h-agent skill list [--all]                     List all skills")
    print("  h-agent skill info <name>                      Show skill details")
    print("  h-agent skill enable <name>                    Enable a skill")
    print("  h-agent skill disable <name>                   Disable a skill")
    print("  h-agent skill install <name> [--package NAME]  Install skill via pip")
    print("  h-agent skill uninstall <name>                 Uninstall a skill")
    print("  h-agent skill run <name> <func> [args...]      Run a skill function")
    return 0


# ============================================================
# Web UI
# ============================================================

def cmd_web(args) -> int:
    """Handle web command - start the Web UI server."""
    from h_agent.web.server import run_server
    run_server(port=args.port, open_browser=not args.no_browser)
    return 0


# ============================================================
# Main
# ============================================================

class Namespace:
    """Simple namespace for passing args."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def main():
    """Main entry point with argparse."""
    import argparse

    parser = argparse.ArgumentParser(
        description="h-agent: AI coding agent with session management and RAG",
        prog="h-agent"
    )

    # Global flags
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ---- Daemon ----
    start_parser = subparsers.add_parser("start", help="Start daemon service")
    status_parser = subparsers.add_parser("status", help="Check daemon status")
    stop_parser = subparsers.add_parser("stop", help="Stop daemon service")

    # ---- Autostart ----
    autostart_parser = subparsers.add_parser("autostart", help="Daemon auto-start management")
    autostart_subparsers = autostart_parser.add_subparsers(dest="autostart_action")
    autostart_install = autostart_subparsers.add_parser("install", help="Install auto-start")
    autostart_uninstall = autostart_subparsers.add_parser("uninstall", help="Uninstall auto-start")
    autostart_status = autostart_subparsers.add_parser("status", help="Check auto-start status")

    # ---- Team ----
    team_parser = subparsers.add_parser("team", help="Multi-agent team management")
    team_subparsers = team_parser.add_subparsers(dest="team_action")
    team_list_parser = team_subparsers.add_parser("list", help="List team members")
    team_status_parser = team_subparsers.add_parser("status", help="Show team status")
    team_init_parser = team_subparsers.add_parser("init", help="Initialize team workspace")
    team_talk_parser = team_subparsers.add_parser("talk", help="Talk to a specific agent")
    team_talk_parser.add_argument("agent", help="Target agent name")
    team_talk_parser.add_argument("message", help="Message to send")
    team_talk_parser.add_argument("--timeout", type=float, default=120, help="Timeout in seconds")

    # ---- Agent ----
    agent_parser = subparsers.add_parser("agent", help="Agent profile management")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_action")

    agent_list_parser = agent_subparsers.add_parser("list", help="List all agent profiles")
    agent_init_parser = agent_subparsers.add_parser("init", help="Initialize a new agent profile")
    agent_init_parser.add_argument("name", help="Agent name")
    agent_init_parser.add_argument("--role", default="coordinator", help="Agent role")
    agent_init_parser.add_argument("--description", default="", help="Agent description")
    agent_show_parser = agent_subparsers.add_parser("show", help="Show agent profile")
    agent_show_parser.add_argument("name", help="Agent name")
    agent_edit_parser = agent_subparsers.add_parser("edit", help="Edit agent profile file")
    agent_edit_parser.add_argument("name", help="Agent name")
    agent_edit_parser.add_argument("file", choices=["identity", "soul", "user", "config"], help="File to edit")
    agent_sessions_parser = agent_subparsers.add_parser("sessions", help="List agent sessions")
    agent_sessions_parser.add_argument("name", help="Agent name")

    # ---- Logs ----
    logs_parser = subparsers.add_parser("logs", help="View daemon log")
    logs_parser.add_argument("--tail", type=int, help="Show last N lines")
    logs_parser.add_argument("--lines", type=int, dest="lines", help="Alias for --tail")

    # ---- Session ----
    session_parser = subparsers.add_parser("session", help="Session management")
    session_subparsers = session_parser.add_subparsers(dest="subcommand")

    # session list
    sl_parser = session_subparsers.add_parser("list", help="List sessions")
    sl_parser.add_argument("--tag", help="Filter by tag")
    sl_parser.add_argument("--group", help="Filter by group")

    # session create
    sc_parser = session_subparsers.add_parser("create", help="Create session")
    sc_parser.add_argument("--name", help="Session name")
    sc_parser.add_argument("--group", help="Group name")

    # session history
    sh_parser = session_subparsers.add_parser("history", help="Show session history")
    sh_parser.add_argument("session_id", help="Session ID or name")

    # session delete
    sd_parser = session_subparsers.add_parser("delete", help="Delete session")
    sd_parser.add_argument("session_id", help="Session ID or name")

    # session search
    ss_parser = session_subparsers.add_parser("search", help="Search sessions")
    ss_parser.add_argument("query", help="Search query")

    # session rename
    sr_parser = session_subparsers.add_parser("rename", help="Rename session")
    sr_parser.add_argument("session_id", help="Session ID or name")
    sr_parser.add_argument("name", help="New name")

    # session tag
    st_parser = session_subparsers.add_parser("tag", help="Manage session tags")
    st_subparsers = st_parser.add_subparsers(dest="tag_action")
    st_list_parser = st_subparsers.add_parser("list", help="List all tags")
    st_add_parser = st_subparsers.add_parser("add", help="Add tag to session")
    st_add_parser.add_argument("session_id", help="Session ID or name")
    st_add_parser.add_argument("tag", help="Tag name")
    st_rm_parser = st_subparsers.add_parser("remove", help="Remove tag from session")
    st_rm_parser.add_argument("session_id", help="Session ID or name")
    st_rm_parser.add_argument("tag", help="Tag name")
    st_get_parser = st_subparsers.add_parser("get", help="Get session tags")
    st_get_parser.add_argument("session_id", help="Session ID or name")

    # session group
    sg_parser = session_subparsers.add_parser("group", help="Manage session groups")
    sg_subparsers = sg_parser.add_subparsers(dest="group_action")
    sg_list_parser = sg_subparsers.add_parser("list", help="List all groups")
    sg_set_parser = sg_subparsers.add_parser("set", help="Set group for session")
    sg_set_parser.add_argument("session_id", help="Session ID or name")
    sg_set_parser.add_argument("group_name", nargs="?", help="Group name (empty to clear)")
    sg_sessions_parser = sg_subparsers.add_parser("sessions", help="List sessions in group")
    sg_sessions_parser.add_argument("group_name", help="Group name")

    # ---- RAG ----
    rag_parser = subparsers.add_parser("rag", help="Codebase RAG")
    rag_subparsers = rag_parser.add_subparsers(dest="rag_action")
    rag_index_parser = rag_subparsers.add_parser("index", help="Index a codebase")
    rag_index_parser.add_argument("--directory", "-d", help="Directory to index")
    rag_search_parser = rag_subparsers.add_parser("search", help="Search codebase")
    rag_search_parser.add_argument("query", nargs="?", help="Search query")
    rag_search_parser.add_argument("--directory", "-d", help="Directory to search")
    rag_search_parser.add_argument("--limit", type=int, default=5, help="Result limit")
    rag_stats_parser = rag_subparsers.add_parser("stats", help="Show index statistics")
    rag_stats_parser.add_argument("--directory", "-d", dest="directory", help="Directory")

    # ---- Run and Chat ----
    run_parser = subparsers.add_parser("run", help="Run single prompt")
    run_parser.add_argument("--session", help="Session ID or name")
    run_parser.add_argument("prompt", nargs="+", help="Prompt text")

    chat_parser = subparsers.add_parser("chat", help="Interactive chat mode")
    chat_parser.add_argument("--session", help="Session ID or name")

    # ---- Config ----
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")
    config_parser.add_argument("--list-all", dest="list_all", action="store_true",
        help="Show all config profiles")
    config_parser.add_argument("--api-key", dest="set_api_key", metavar="KEY",
        help="Set API key (use __prompt__ for secure input)")
    config_parser.add_argument("--clear-key", action="store_true", help="Remove stored API key")
    config_parser.add_argument("--base-url", dest="set_base_url", metavar="URL",
        help="Set API base URL")
    config_parser.add_argument("--model", dest="set_model", metavar="MODEL",
        help="Set model ID")
    config_parser.add_argument("--wizard", action="store_true", help="Run interactive setup wizard")
    config_parser.add_argument("--profile", dest="profile_switch", metavar="NAME",
        help="Switch to a config profile")
    config_parser.add_argument("--profile-create", dest="profile_create", metavar="NAME",
        help="Create a new config profile")
    config_parser.add_argument("--profile-delete", dest="profile_delete", metavar="NAME",
        help="Delete a config profile")
    config_parser.add_argument("--export", action="store_true", help="Export config to JSON")
    config_parser.add_argument("--import", dest="import_cfg", metavar="FILE",
        help="Import config from JSON file")

    # ---- Memory ----
    memory_parser = subparsers.add_parser("memory", help="Long-term memory management")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_action")

    memory_list_parser = memory_subparsers.add_parser("list", help="List all memories")
    memory_list_parser.add_argument("--type", dest="list_type", metavar="TYPE",
        help="Filter by type: user, project, decision, fact, error")

    memory_add_parser = memory_subparsers.add_parser("add", help="Store a memory")
    memory_add_parser.add_argument("add_type", metavar="TYPE", help="Memory type")
    memory_add_parser.add_argument("add_key", metavar="KEY", help="Memory key")
    memory_add_parser.add_argument("add_value", metavar="VALUE", help="Memory value")
    memory_add_parser.add_argument("--reason", help="Reason/explanation")
    memory_add_parser.add_argument("--tags", help="Comma-separated tags")

    memory_get_parser = memory_subparsers.add_parser("get", help="Get a memory by key")
    memory_get_parser.add_argument("get_key", metavar="KEY", help="Memory key")

    memory_delete_parser = memory_subparsers.add_parser("delete", help="Delete a memory")
    memory_delete_parser.add_argument("delete_type", metavar="TYPE", help="Memory type")
    memory_delete_parser.add_argument("delete_key", metavar="KEY", help="Memory key")

    memory_search_parser = memory_subparsers.add_parser("search", help="Search memories")
    memory_search_parser.add_argument("search_query", nargs="?", help="Search query")
    memory_search_parser.add_argument("--sessions", action="store_true", dest="search_sessions",
        help="Also search session history")
    memory_search_parser.add_argument("--summaries", action="store_true", dest="search_summaries",
        help="Also search LLM summaries")
    memory_search_parser.add_argument("--days", type=int, help="Only search sessions from last N days")

    memory_dump_parser = memory_subparsers.add_parser("dump", help="Dump memories as text")
    memory_dump_parser.add_argument("--type", dest="dump_type", default="all",
        help="Filter by type (default: all)")

    # ---- Plugin ----
    plugin_parser = subparsers.add_parser("plugin", help="Plugin management")
    plugin_subparsers = plugin_parser.add_subparsers(dest="plugin_action")
    plugin_list_parser = plugin_subparsers.add_parser("list", help="List all plugins")
    plugin_info_parser = plugin_subparsers.add_parser("info", help="Show plugin details")
    plugin_info_parser.add_argument("plugin_name", help="Plugin name")
    plugin_enable_parser = plugin_subparsers.add_parser("enable", help="Enable a plugin")
    plugin_enable_parser.add_argument("plugin_name", help="Plugin name")
    plugin_disable_parser = plugin_subparsers.add_parser("disable", help="Disable a plugin")
    plugin_disable_parser.add_argument("plugin_name", help="Plugin name")
    plugin_install_parser = plugin_subparsers.add_parser("install", help="Install plugin from URL")
    plugin_install_parser.add_argument("plugin_url", help="Plugin URL or git repo")
    plugin_uninstall_parser = plugin_subparsers.add_parser("uninstall", help="Uninstall a plugin")
    plugin_uninstall_parser.add_argument("plugin_name", help="Plugin name")

    # ---- Skill ----
    skill_parser = subparsers.add_parser("skill", help="Skill management")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_action")
    skill_list_parser = skill_subparsers.add_parser("list", help="List all skills")
    skill_list_parser.add_argument("--all", action="store_true", help="Include disabled skills")
    skill_info_parser = skill_subparsers.add_parser("info", help="Show skill details")
    skill_info_parser.add_argument("skill_name", help="Skill name")
    skill_enable_parser = skill_subparsers.add_parser("enable", help="Enable a skill")
    skill_enable_parser.add_argument("skill_name", help="Skill name")
    skill_disable_parser = skill_subparsers.add_parser("disable", help="Disable a skill")
    skill_disable_parser.add_argument("skill_name", help="Skill name")
    skill_install_parser = skill_subparsers.add_parser("install", help="Install skill via pip")
    skill_install_parser.add_argument("skill_name", help="Skill name")
    skill_install_parser.add_argument("--package", help="Pip package name (default: h_agent_skill_<name>)")
    skill_uninstall_parser = skill_subparsers.add_parser("uninstall", help="Uninstall a skill")
    skill_uninstall_parser.add_argument("skill_name", help="Skill name")
    skill_run_parser = skill_subparsers.add_parser("run", help="Run a skill function")
    skill_run_parser.add_argument("skill_name", help="Skill name")
    skill_run_parser.add_argument("function_name", help="Function name to run")
    skill_run_parser.add_argument("args", nargs="*", help="Function arguments")

    # ---- Template ----
    template_parser = subparsers.add_parser("template", help="Agent template management")
    template_subparsers = template_parser.add_subparsers(dest="template_action")
    template_list_parser = template_subparsers.add_parser("list", help="List all templates")
    template_apply_parser = template_subparsers.add_parser("apply", help="Apply a template")
    template_apply_parser.add_argument("template_name", help="Template name")
    template_show_parser = template_subparsers.add_parser("show", help="Show template details")
    template_show_parser.add_argument("template_name", help="Template name")
    template_create_parser = template_subparsers.add_parser("create", help="Create a new template")
    template_create_parser.add_argument("template_name", help="Template name")
    template_delete_parser = template_subparsers.add_parser("delete", help="Delete a template")
    template_delete_parser.add_argument("template_name", help="Template name")

    # ---- Model ----
    model_parser = subparsers.add_parser("model", help="Model management")
    model_subparsers = model_parser.add_subparsers(dest="model_action")
    model_list_parser = model_subparsers.add_parser("list", help="List all available models")
    model_switch_parser = model_subparsers.add_parser("switch", help="Switch to a different model")
    model_switch_parser.add_argument("model_name", help="Model name")
    model_info_parser = model_subparsers.add_parser("info", help="Show model details")
    model_info_parser.add_argument("model_name", help="Model name")
    model_add_parser = model_subparsers.add_parser("add", help="Add a new model")

    # ---- Init ----
    init_parser = subparsers.add_parser("init", help="Initialize h-agent with interactive setup")
    init_parser.add_argument("--quick", action="store_true", help="Quick setup mode")

    # ---- Web UI ----
    web_parser = subparsers.add_parser("web", help="Start Web UI server")
    web_parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    web_parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")

    # ---- Cron ----
    cron_parser = subparsers.add_parser("cron", help="Cron job scheduling")
    cron_subparsers = cron_parser.add_subparsers(dest="cron_action")

    cron_list_parser = cron_subparsers.add_parser("list", help="List all cron jobs")
    cron_list_parser.add_argument("--verbose", "-v", action="store_true", help="Show details")

    cron_add_parser = cron_subparsers.add_parser("add", help="Add a cron job")
    cron_add_parser.add_argument("expression", help="Cron expression (e.g., '*/5 * * * *')")
    cron_add_parser.add_argument("cmd", help="Command to execute")
    cron_add_parser.add_argument("--name", "-n", dest="job_name", help="Job name")

    cron_remove_parser = cron_subparsers.add_parser("remove", help="Remove a cron job")
    cron_remove_parser.add_argument("job_id", help="Job ID to remove")

    cron_enable_parser = cron_subparsers.add_parser("enable", help="Enable a cron job")
    cron_enable_parser.add_argument("job_id", help="Job ID to enable")

    cron_disable_parser = cron_subparsers.add_parser("disable", help="Disable a cron job")
    cron_disable_parser.add_argument("job_id", help="Job ID to disable")

    cron_exec_parser = cron_subparsers.add_parser("exec", help="Execute a cron job now")
    cron_exec_parser.add_argument("job_id", help="Job ID to execute")

    cron_log_parser = cron_subparsers.add_parser("log", help="Show execution logs")
    cron_log_parser.add_argument("--job", dest="job_id", help="Filter by job ID")
    cron_log_parser.add_argument("--limit", type=int, default=20, help="Number of records")

    # ---- Heartbeat ----
    heartbeat_parser = subparsers.add_parser("heartbeat", help="Heartbeat management")
    heartbeat_subparsers = heartbeat_parser.add_subparsers(dest="heartbeat_action")

    heartbeat_start_parser = heartbeat_subparsers.add_parser("start", help="Start heartbeat")
    heartbeat_start_parser.add_argument("--interval", type=int, default=60,
        help="Check interval in seconds (default: 60)")

    heartbeat_stop_parser = heartbeat_subparsers.add_parser("stop", help="Stop heartbeat")

    heartbeat_status_parser = heartbeat_subparsers.add_parser("status", help="Show heartbeat status")

    heartbeat_run_parser = heartbeat_subparsers.add_parser("run", help="Run heartbeat check once")

    args = parser.parse_args()

    # ---- Version ----
    if args.version:
        print(f"h-agent {__version__}")
        return 0

    if not args.command:
        # Default: interactive chat
        return cmd_chat(Namespace(session=None))

    if args.command == "start":
        return cmd_start(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "stop":
        return cmd_stop(args)
    if args.command == "logs":
        return cmd_logs(args)

    if args.command == "autostart":
        return cmd_autostart(args)

    if args.command == "team":
        return cmd_team(args)

    if args.command == "agent":
        return cmd_agent(args)

    if args.command == "session":
        sub = args.subcommand
        if sub == "list":
            return cmd_session_list(args)
        if sub == "create":
            return cmd_session_create(args)
        if sub == "history":
            return cmd_session_history(args)
        if sub == "delete":
            return cmd_session_delete(args)
        if sub == "search":
            return cmd_session_search(args)
        if sub == "rename":
            return cmd_session_rename(args)
        if sub == "tag":
            return cmd_session_tag(args)
        if sub == "group":
            return cmd_session_group(args)
        session_parser.print_help()
        return 1

    if args.command == "rag":
        return cmd_rag(args)

    if args.command == "run":
        args.prompt = " ".join(args.prompt)
        return cmd_run(args)

    if args.command == "chat":
        return cmd_chat(args)

    if args.command == "config":
        if getattr(args, 'wizard', False):
            return cmd_config_wizard(args)
        return cmd_config(args)

    if args.command == "memory":
        return cmd_memory(args)

    if args.command == "plugin":
        return cmd_plugin(args)

    if args.command == "skill":
        return cmd_skill(args)

    if args.command == "template":
        return cmd_template(args)

    if args.command == "model":
        return cmd_model(args)

    if args.command == "init":
        return cmd_init(args)

    if args.command == "web":
        return cmd_web(args)

    # ---- Cron ----
    if args.command == "cron":
        return cmd_cron(args)

    # ---- Heartbeat ----
    if args.command == "heartbeat":
        return cmd_heartbeat(args)

    parser.print_help()
    return 1


# ============================================================
# Cron Commands
# ============================================================

def cmd_cron(args) -> int:
    """Handle cron commands."""
    from datetime import datetime
    from h_agent.scheduler import (
        list_cron_jobs, get_cron_job, delete_cron_job,
        enable_cron_job, disable_cron_job, add_cron_job,
        list_executions, HeartbeatMonitor,
        validate_cron, format_next_run, CronExpression,
    )

    sub = args.cron_action

    if sub == "list":
        jobs = list_cron_jobs()
        if not jobs:
            print("No cron jobs configured.")
            return 0

        if args.verbose:
            print(f"{'ID':<10} {'Name':<20} {'Expression':<20} {'Status':<10} {'Next Run':<20}")
            print("-" * 80)
            for job in jobs:
                next_run = format_next_run(
                    datetime.fromtimestamp(job.next_run) if job.next_run else None
                )
                status = "✓ active" if job.enabled else "✗ disabled"
                print(f"{job.id:<10} {job.name[:20]:<20} {job.expression:<20} {status:<12} {next_run:<20}")
        else:
            print(f"{'ID':<10} {'Name':<20} {'Expression':<15} {'Status':<10}")
            print("-" * 60)
            for job in jobs:
                status = "active" if job.enabled else "disabled"
                print(f"{job.id:<10} {job.name[:20]:<20} {job.expression:<15} {status:<10}")
        return 0

    if sub == "add":
        expression = args.expression
        command = args.cmd
        name = args.job_name or f"Job {expression}"

        # Validate expression
        is_valid, error = validate_cron(expression)
        if not is_valid:
            _err(f"Invalid cron expression: {error}")
            return 1

        try:
            job = add_cron_job(expression, command, name)
            _ok(f"Added cron job '{name}' (ID: {job.id})")
            print(f"  Expression: {expression}")
            print(f"  Command: {command}")
            print(f"  Next run: {format_next_run(datetime.fromtimestamp(job.next_run) if job.next_run else None)}")
            return 0
        except Exception as e:
            _err(f"Failed to add cron job: {e}")
            return 1

    if sub == "remove":
        job_id = args.job_id
        job = get_cron_job(job_id)
        if not job:
            _err(f"Cron job not found: {job_id}")
            return 1

        deleted = delete_cron_job(job_id)
        if deleted:
            _ok(f"Removed cron job: {job.name} ({job_id})")
            return 0
        else:
            _err(f"Failed to remove cron job: {job_id}")
            return 1

    if sub == "enable":
        job_id = args.job_id
        job = get_cron_job(job_id)
        if not job:
            _err(f"Cron job not found: {job_id}")
            return 1

        if enable_cron_job(job_id):
            _ok(f"Enabled cron job: {job.name} ({job_id})")
            return 0
        else:
            _err(f"Failed to enable cron job: {job_id}")
            return 1

    if sub == "disable":
        job_id = args.job_id
        job = get_cron_job(job_id)
        if not job:
            _err(f"Cron job not found: {job_id}")
            return 1

        if disable_cron_job(job_id):
            _ok(f"Disabled cron job: {job.name} ({job_id})")
            return 0
        else:
            _err(f"Failed to disable cron job: {job_id}")
            return 1

    if sub == "exec":
        job_id = args.job_id
        job = get_cron_job(job_id)
        if not job:
            _err(f"Cron job not found: {job_id}")
            return 1

        print(f"Executing job: {job.name}...")
        monitor = HeartbeatMonitor()
        results = monitor.run_once()
        
        for r in results:
            if r["job_id"] == job_id:
                if r["success"]:
                    _ok(f"Job executed successfully")
                    if r["output"]:
                        print(f"Output: {r['output']}")
                else:
                    _err(f"Job failed: {r['error']}")
                return 0

        print("Job was not executed (not due to run)")
        return 0

    if sub == "log":
        job_id = args.job_id
        limit = args.limit

        records = list_executions(task_id=job_id, limit=limit)
        if not records:
            print("No execution records found.")
            return 0

        print(f"{'ID':<10} {'Job ID':<10} {'Started':<25} {'Status':<8} {'Exit':<5}")
        print("-" * 65)
        for rec in records:
            started = datetime.fromtimestamp(rec.started_at).strftime("%Y-%m-%d %H:%M:%S")
            status = "✓" if rec.success else "✗"
            exit_code = str(rec.exit_code) if rec.exit_code else "-"
            print(f"{rec.id:<10} {rec.task_id:<10} {started:<25} {status:<8} {exit_code:<5}")
        return 0

    cron_parser.print_help()
    return 1


# ============================================================
# Heartbeat Commands
# ============================================================

def cmd_heartbeat(args) -> int:
    """Handle heartbeat commands."""
    from h_agent.scheduler import (
        heartbeat_status, start_heartbeat, stop_heartbeat,
        is_heartbeat_running, HeartbeatMonitor,
    )

    sub = args.heartbeat_action

    if sub == "start":
        if is_heartbeat_running():
            _warn("Heartbeat is already running")
            return 0

        interval = args.interval
        if start_heartbeat(interval=interval):
            _ok(f"Heartbeat started (interval: {interval}s)")
            return 0
        else:
            _err("Failed to start heartbeat")
            return 1

    if sub == "stop":
        if not is_heartbeat_running():
            _warn("Heartbeat is not running")
            return 0

        if stop_heartbeat():
            _ok("Heartbeat stopped")
            return 0
        else:
            _err("Failed to stop heartbeat")
            return 1

    if sub == "status":
        status = heartbeat_status()
        running = status.get("running", False)

        print(f"Heartbeat: {'running' if running else 'stopped'}")
        if running:
            print(f"  PID: {status.get('pid', 'N/A')}")
            print(f"  Interval: {status.get('interval', 60)}s")
            if status.get("last_check"):
                from datetime import datetime
                last = datetime.fromtimestamp(status["last_check"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"  Last check: {last}")
            print(f"  Total executions: {status.get('executions', 0)}")
        return 0

    if sub == "run":
        print("Running heartbeat check...")
        monitor = HeartbeatMonitor()
        results = monitor.run_once()
        if results:
            print(f"Executed {len(results)} task(s):")
            for r in results:
                status = "✓" if r["success"] else "✗"
                print(f"  {status} {r['job_name']}")
        else:
            print("No tasks due to run.")
        return 0

    heartbeat_parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
