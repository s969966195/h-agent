#!/usr/bin/env python3
"""
h_agent/cli/commands.py - Command Line Interface

Main entry point for h_agent CLI.
"""

import os
import sys
import json
from pathlib import Path

# Add parent to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(override=True)

# Import from core
from h_agent.core.tools import agent_loop, TOOLS, TOOL_HANDLERS, execute_tool_call
from h_agent.core.config import (
    MODEL, OPENAI_BASE_URL, OPENAI_API_KEY,
    get_config, set_config, list_config, clear_secret,
    AGENT_CONFIG_FILE, AGENT_SECRETS_FILE
)


def cmd_config(args) -> int:
    """Handle config command."""
    if args.show:
        config = list_config()
        print("=== h-agent Configuration ===")
        if "openai_api_key" in config:
            print(f"  OPENAI_API_KEY: {config['openai_api_key']}")
        if "openai_base_url" in config:
            print(f"  OPENAI_BASE_URL: {config['openai_base_url']}")
        if "model_id" in config:
            print(f"  MODEL_ID: {config['model_id']}")
        print()
        print(f"Config file: {AGENT_CONFIG_FILE}")
        print(f"Secrets file: {AGENT_SECRETS_FILE}")
        return 0

    if args.set_api_key:
        key = args.set_api_key
        if key == "__prompt__":
            import getpass
            key = getpass.getpass("Enter API key: ")
        set_config("OPENAI_API_KEY", key, secure=True)
        print("API key saved securely.")
        return 0

    if args.clear_key:
        clear_secret("OPENAI_API_KEY")
        print("API key cleared.")
        return 0

    if args.set_base_url:
        set_config("OPENAI_BASE_URL", args.set_base_url)
        print(f"Base URL set to: {args.set_base_url}")
        return 0

    if args.set_model:
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


def get_system_prompt() -> str:
    """Get the system prompt for the agent."""
    return f"""You are a coding agent at {os.getcwd()}.

Use the available tools to solve tasks efficiently.

Available tools:
- bash: Run shell commands
- read: Read file contents
- write: Write content to files
- edit: Make precise edits to files
- glob: Find files by pattern

Act efficiently. Don't over-explain."""


def interactive_mode():
    """Run interactive REPL mode."""
    print(f"\033[36mh_agent - OpenAI Agent Harness\033[0m")
    print(f"Model: {MODEL}")
    print(f"API: {OPENAI_BASE_URL}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Tools: {', '.join(TOOL_HANDLERS.keys())}")
    print()
    print("Type 'q', 'exit', or press Enter to quit")
    print("=" * 50)
    print()
    
    history = []
    
    while True:
        try:
            query = input("\033[36m>> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if query.strip().lower() in ("q", "exit", ""):
            print("Goodbye!")
            break
        
        # Add user message
        history.append({"role": "user", "content": query})
        
        # Run agent loop
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
            )
            
            while True:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": get_system_prompt()}] + history,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=8000,
                )
                
                message = response.choices[0].message
                history.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": message.tool_calls,
                })
                
                if not message.tool_calls:
                    break
                
                # Execute tool calls
                for tool_call in message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    key_arg = args.get('command') or args.get('path') or args.get('pattern', '')
                    print(f"\033[33m$ {tool_call.function.name}({key_arg[:40]})\033[0m")
                    
                    result = execute_tool_call(tool_call)
                    print(result[:200] + ("..." if len(result) > 200 else ""))
                    
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            
            # Print final response
            if history[-1].get("content"):
                print(f"\n{history[-1]['content']}\n")
                
        except Exception as e:
            print(f"\033[31mError: {e}\033[0m")


def main():
    """Main entry point with argparse."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="h-agent: OpenAI-powered coding agent harness",
        prog="h-agent"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Config subcommand
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")
    config_parser.add_argument("--api-key", dest="set_api_key", metavar="KEY",
        help="Set API key (use __prompt__ for secure input)")
    config_parser.add_argument("--clear-key", action="store_true", help="Remove stored API key")
    config_parser.add_argument("--base-url", dest="set_base_url", metavar="URL",
        help="Set API base URL")
    config_parser.add_argument("--model", dest="set_model", metavar="MODEL",
        help="Set model ID")
    
    args = parser.parse_args()
    
    if args.command == "config":
        return cmd_config(args)
    
    # Interactive mode (default)
    interactive_mode()
    return 0


if __name__ == "__main__":
    sys.exit(main())
