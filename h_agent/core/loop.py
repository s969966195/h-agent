#!/usr/bin/env python3
"""
h_agent/core/loop.py - Canonical Agent Loop

Shared agent loop implementation with parallel tool execution.
All agent_loop() functions should delegate to this function.

Phase 4 of optimization: Extract shared run_agent_loop() function.
"""

import os
import json
from typing import Optional, Callable, Any

from h_agent.core.client import get_client


def run_agent_loop(
    messages: list,
    client=None,
    tools: list = None,
    tool_handlers: dict = None,
    execute_tool_calls_parallel: Callable = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 8000,
    print_results: bool = True,
) -> None:
    """
    Canonical agent loop with parallel tool execution.
    
    Args:
        messages: Conversation messages list (modified in place)
        client: OpenAI client (defaults to get_client())
        tools: OpenAI tool definitions list
        tool_handlers: Dict mapping tool name -> handler function
        execute_tool_calls_parallel: Function to execute tool calls (receives list, returns list of results)
        system_prompt: Optional system prompt to prepend
        max_tokens: Max tokens for LLM response
        print_results: Whether to print tool executions
    """
    if client is None:
        client = get_client()
    
    if tools is None:
        tools = []
    
    if tool_handlers is None:
        tool_handlers = {}
    
    model = os.getenv("MODEL_ID", "gpt-4o")
    
    # Build messages with optional system prompt
    if system_prompt:
        api_messages = [{"role": "system", "content": system_prompt}] + messages
    else:
        api_messages = messages
    
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
        )
        
        message = response.choices[0].message
        
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": message.tool_calls,
        })
        
        if not message.tool_calls:
            return
        
        if print_results:
            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments)
                if tc.function.name == "bash":
                    print(f"\033[33m$ {args.get('command', '')}\033[0m")
                else:
                    key = next(iter(args.keys()), "")
                    print(f"\033[33m{tc.function.name}({key}=...)\033[0m")
        
        # Execute tools
        if execute_tool_calls_parallel:
            results = execute_tool_calls_parallel(message.tool_calls)
        else:
            # Sequential fallback
            results = []
            for tc in message.tool_calls:
                func_name = tc.function.name
                args = json.loads(tc.function.arguments)
                handler = tool_handlers.get(func_name)
                if handler:
                    result = handler(**args)
                else:
                    result = f"Error: Unknown tool '{func_name}'"
                results.append(result)
        
        # Append results to messages
        for tc, result in zip(message.tool_calls, results):
            if print_results:
                display = result[:200] + ("..." if len(result) > 200 else "")
                print(display)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
