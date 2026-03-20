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

from dotenv import load_dotenv
load_dotenv(override=True)

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
        _ok("API key saved.")
        return 0

    if args.clear_key:
        from h_agent.core.config import clear_secret
        clear_secret("OPENAI_API_KEY")
        _ok("API key cleared.")
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
    config_parser.add_argument("--api-key", dest="set_api_key", metavar="KEY",
        help="Set API key (use __prompt__ for secure input)")
    config_parser.add_argument("--clear-key", action="store_true", help="Remove stored API key")
    config_parser.add_argument("--base-url", dest="set_base_url", metavar="URL",
        help="Set API base URL")
    config_parser.add_argument("--model", dest="set_model", metavar="MODEL",
        help="Set model ID")
    config_parser.add_argument("--wizard", action="store_true", help="Run interactive setup wizard")

    # ---- Init ----
    init_parser = subparsers.add_parser("init", help="Initialize h-agent with interactive setup")
    init_parser.add_argument("--quick", action="store_true", help="Quick setup mode")

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

    if args.command == "init":
        return cmd_init(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
