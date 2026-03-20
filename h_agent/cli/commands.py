#!/usr/bin/env python3
"""
h_agent/cli/commands.py - Command Line Interface

Main entry point for h_agent CLI.
Supports:
  - Daemon control (start, status, stop)
  - Session management (list, create, history, delete)
  - Run and chat with agent

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

from dotenv import load_dotenv
load_dotenv(override=True)

from h_agent.platform_utils import (
    IS_WINDOWS, daemon_pid_file, start_daemon_subprocess,
    stop_process, is_process_alive, get_config_dir
)

# Paths - use platform-aware PID file
PID_FILE = str(daemon_pid_file())
DAEMON_PORT = int(os.environ.get("H_AGENT_PORT", 19527))

# Import from core
from h_agent.core.tools import TOOL_HANDLERS, execute_tool_call, TOOLS
from h_agent.core.config import (
    MODEL, OPENAI_BASE_URL, OPENAI_API_KEY,
    list_config
)

from h_agent.session.manager import SessionManager


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

        # Check if process is alive (cross-platform)
        if is_process_alive(pid):
            return {"running": True, "pid": pid, "port": port}
        
        # Process dead but PID file exists - clean up
        try:
            pid_file.unlink()
        except OSError:
            pass
        return {"running": False}
    except (ValueError, ProcessLookupError, PermissionError, json.JSONDecodeError, OSError):
        # Clean up stale PID file
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

    # Use platform-aware subprocess start
    pid = start_daemon_subprocess(sys.executable, DAEMON_PORT)
    if pid is None:
        print("Failed to start daemon (subprocess error)")
        return 1

    # Wait for daemon to write its PID file
    pid_file = Path(PID_FILE)
    for _ in range(20):
        time.sleep(0.25)
        new_status = daemon_status()
        if new_status.get("running"):
            print(f"Daemon started (PID: {new_status['pid']}, Port: {new_status['port']})")
            return 0

    print("Failed to start daemon (timeout)")
    return 1


def stop_daemon():
    """Stop the daemon (cross-platform)."""
    status = daemon_status()
    if not status.get("running"):
        print("Daemon not running")
        # Clean up stale files
        try:
            Path(PID_FILE).unlink()
        except OSError:
            pass
        return 0

    pid = status["pid"]
    if stop_process(pid, timeout=2.0):
        # Clean up PID file
        try:
            Path(PID_FILE).unlink()
        except OSError:
            pass
        print("Daemon stopped")
        return 0
    else:
        print(f"Failed to stop daemon (PID: {pid}). You may need to stop it manually.")
        return 1


def cmd_start(args) -> int:
    """Handle start command."""
    return start_daemon()


def cmd_status(args) -> int:
    """Handle status command."""
    status = daemon_status()
    if status.get("running"):
        print(f"Daemon running (PID: {status['pid']}, Port: {status['port']})")

        # Try to get more info via client
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


def cmd_stop(args) -> int:
    """Handle stop command."""
    return stop_daemon()


# ============================================================
# Session Management
# ============================================================

def get_session_manager() -> SessionManager:
    """Get session manager instance."""
    return SessionManager()


def cmd_session_list(args) -> int:
    """Handle session list command."""
    mgr = get_session_manager()
    sessions = mgr.list_sessions()

    if not sessions:
        print("No sessions found")
        return 0

    current = mgr.get_current()
    print(f"Sessions ({len(sessions)}):")
    for s in sessions:
        marker = " *" if s["session_id"] == current else ""
        name = s.get("name", "unnamed")
        count = s.get("message_count", 0)
        updated = s.get("updated_at", "")[:19]
        print(f"  {s['session_id']}  {name:<20} {count:>3} msgs  {updated}{marker}")
    return 0


def cmd_session_create(args) -> int:
    """Handle session create command."""
    mgr = get_session_manager()
    name = args.name if hasattr(args, 'name') and args.name else None
    session = mgr.create_session(name)
    print(f"Created: {session['session_id']} ({session.get('name', 'unnamed')})")
    return 0


def cmd_session_history(args) -> int:
    """Handle session history command."""
    mgr = get_session_manager()
    session_id = args.session_id

    # Find session
    session = mgr.get_session(session_id)
    if not session:
        # Try to find by name
        for s in mgr.list_sessions():
            if s.get("name") == session_id:
                session = s
                session_id = s["session_id"]
                break

    if not session:
        print(f"Session not found: {session_id}")
        return 1

    history = mgr.get_history(session_id)
    print(f"History for {session_id} ({len(history)} messages):")
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
    session_id = args.session_id

    # Find session
    session = mgr.get_session(session_id)
    if not session:
        # Try to find by name
        for s in mgr.list_sessions():
            if s.get("name") == session_id:
                session = s
                session_id = s["session_id"]
                break

    if not session:
        print(f"Session not found: {session_id}")
        return 1

    if mgr.delete_session(session_id):
        print(f"Deleted: {session_id}")
        return 0
    return 1


# ============================================================
# Run / Chat
# ============================================================

def cmd_run(args) -> int:
    """Handle run command - single prompt execution."""
    from openai import OpenAI

    prompt = args.prompt
    session_id = args.session

    # Get or create session
    mgr = get_session_manager()

    if session_id:
        # Try to find by name first
        session = mgr.get_session(session_id)
        if not session:
            for s in mgr.list_sessions():
                if s.get("name") == session_id:
                    session_id = s["session_id"]
                    session = s
                    break

        if not session:
            print(f"Session not found: {session_id}")
            return 1
    else:
        # Create or use current
        if not mgr.get_current():
            session = mgr.create_session("default")
            session_id = session["session_id"]
        else:
            session_id = mgr.get_current()

    mgr.set_current(session_id)

    # Load history
    messages = mgr.get_history(session_id)

    # Add user message
    messages.append({"role": "user", "content": prompt})
    mgr.add_message(session_id, "user", prompt)

    # Build messages for API
    system_prompt = f"You are a helpful AI assistant. Current directory: {os.getcwd()}"
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    # Run agent loop
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

            # Add assistant message to history
            content = message.content or ""
            tool_calls = message.tool_calls

            mgr.add_message(session_id, "assistant", content)

            if not tool_calls:
                break

            # Execute tools
            for tool_call in tool_calls:
                print(f"\n$ {tool_call.function.name}(...)", file=sys.stderr)

                args_dict = json.loads(tool_call.function.arguments)
                result = execute_tool_call(tool_call)

                # Truncate long outputs for storage
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
            print(f"Error: {e}")
            return 1

    return 0


def cmd_chat(args) -> int:
    """Handle chat command - interactive mode."""
    from openai import OpenAI

    session_id = args.session

    # Get or create session
    mgr = get_session_manager()

    if session_id:
        session = mgr.get_session(session_id)
        if not session:
            for s in mgr.list_sessions():
                if s.get("name") == session_id:
                    session_id = s["session_id"]
                    session = s
                    break

        if not session:
            print(f"Session not found: {session_id}")
            return 1
        else:
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

    # Load history
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

        # Add user message
        messages.append({"role": "user", "content": query})
        mgr.add_message(session_id, "user", query)

        # Build API messages
        api_messages = [{"role": "system", "content": system_prompt}] + messages

        # Run agent loop
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

                # Add to history
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

                # Execute tools
                for tool_call in message.tool_calls:
                    args_dict = json.loads(tool_call.function.arguments)
                    key = list(args_dict.keys())[0] if args_dict else ""
                    val = args_dict.get(key, "")[:60] if key else ""
                    print(f"\n\033[33m$ {tool_call.function.name}({val})\033[0m", file=sys.stderr)

                    result = execute_tool_call(tool_call)
                    print(f"\033[90m{result[:500]}{'...' if len(result) > 500 else ''}\033[0m", file=sys.stderr)

                    # Truncate for storage
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
    if args.show:
        config = list_config()
        print("=== h-agent Configuration ===")
        if "openai_api_key" in config:
            print(f"  OPENAI_API_KEY: {config['openai_api_key'][:10]}...")
        if "openai_base_url" in config:
            print(f"  OPENAI_BASE_URL: {config['openai_base_url']}")
        if "model_id" in config:
            print(f"  MODEL_ID: {config['model_id']}")
        print()
        print(f"Config file: {Path.home() / '.h-agent' / 'config.json'}")
        return 0

    if args.set_api_key:
        from h_agent.core.config import set_config
        key = args.set_api_key
        if key == "__prompt__":
            import getpass
            key = getpass.getpass("Enter API key: ")
        set_config("OPENAI_API_KEY", key, secure=True)
        print("API key saved.")
        return 0

    if args.clear_key:
        from h_agent.core.config import clear_secret
        clear_secret("OPENAI_API_KEY")
        print("API key cleared.")
        return 0

    if args.set_base_url:
        from h_agent.core.config import set_config
        set_config("OPENAI_BASE_URL", args.set_base_url)
        print(f"Base URL set to: {args.set_base_url}")
        return 0

    if args.set_model:
        from h_agent.core.config import set_config
        set_config("MODEL_ID", args.set_model)
        print(f"Model set to: {args.set_model}")
        return 0

    # No subcommand: show help
    print("h-agent config - Configuration management")
    print()
    print("Usage:")
    print("  h-agent config --show              Show current config")
    print("  h-agent config --api-key KEY       Set API key")
    print("  h-agent config --api-key __prompt__  Set API key (prompt for input)")
    print("  h-agent config --clear-key         Remove stored API key")
    print("  h-agent config --base-url URL      Set API base URL")
    print("  h-agent config --model MODEL       Set model ID")
    return 0


# ============================================================
# Main
# ============================================================

def main():
    """Main entry point with argparse."""
    import argparse

    parser = argparse.ArgumentParser(
        description="h-agent: AI coding agent with session management",
        prog="h-agent"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Daemon commands
    start_parser = subparsers.add_parser("start", help="Start daemon service")
    status_parser = subparsers.add_parser("status", help="Check daemon status")
    stop_parser = subparsers.add_parser("stop", help="Stop daemon service")

    # Session commands
    session_parser = subparsers.add_parser("session", help="Session management")
    session_subparsers = session_parser.add_subparsers(dest="subcommand")

    session_list_parser = session_subparsers.add_parser("list", help="List sessions")
    session_create_parser = session_subparsers.add_parser("create", help="Create session")
    session_create_parser.add_argument("--name", help="Session name")
    session_history_parser = session_subparsers.add_parser("history", help="Show session history")
    session_history_parser.add_argument("session_id", help="Session ID or name")
    session_delete_parser = session_subparsers.add_parser("delete", help="Delete session")
    session_delete_parser.add_argument("session_id", help="Session ID or name")

    # Run and chat
    run_parser = subparsers.add_parser("run", help="Run single prompt")
    run_parser.add_argument("--session", help="Session ID or name")
    run_parser.add_argument("prompt", nargs="+", help="Prompt text")

    chat_parser = subparsers.add_parser("chat", help="Interactive chat mode")
    chat_parser.add_argument("--session", help="Session ID or name")

    # Config
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")
    config_parser.add_argument("--api-key", dest="set_api_key", metavar="KEY",
        help="Set API key (use __prompt__ for secure input)")
    config_parser.add_argument("--clear-key", action="store_true", help="Remove stored API key")
    config_parser.add_argument("--base-url", dest="set_base_url", metavar="URL",
        help="Set API base URL")
    config_parser.add_argument("--model", dest="set_model", metavar="MODEL",
        help="Set model ID")
    config_parser.add_argument("--wizard", action="store_true", help="Run interactive setup wizard")

    # Init
    init_parser = subparsers.add_parser("init", help="Initialize h-agent with interactive setup")
    init_parser.add_argument("--quick", action="store_true", help="Quick setup mode")

    args = parser.parse_args()

    if not args.command:
        # Default: interactive chat
        return cmd_chat(Namespace(session=None))

    if args.command == "start":
        return cmd_start(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "stop":
        return cmd_stop(args)

    if args.command == "session":
        if args.subcommand == "list":
            return cmd_session_list(args)
        if args.subcommand == "create":
            return cmd_session_create(args)
        if args.subcommand == "history":
            return cmd_session_history(args)
        if args.subcommand == "delete":
            return cmd_session_delete(args)
        session_parser.print_help()
        return 1

    if args.command == "run":
        args.prompt = " ".join(args.prompt)
        return cmd_run(args)

    if args.command == "chat":
        return cmd_chat(args)

    if args.command == "config":
        if getattr(args, 'wizard', False):
            return cmd_config_wizard(args)
        return cmd_config(args)
    
    if args.command == "init":
        return cmd_init(args)

    parser.print_help()
    return 1


class Namespace:
    """Simple namespace for passing args."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


if __name__ == "__main__":
    sys.exit(main())