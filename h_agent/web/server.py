#!/usr/bin/env python3
"""
h_agent/web/server.py - Web UI Server

Serves a simple chat interface using Flask + SSE.
"""

import os
import json
import asyncio
import threading
import queue
from pathlib import Path
from flask import Flask, render_template, Response, request, jsonify
from dotenv import load_dotenv

load_dotenv(override=True)

# Import from h_agent
from h_agent.session.manager import get_manager
from h_agent.core.config import MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
from h_agent.core.tools import execute_tool_call, TOOLS as CORE_TOOLS

# Lazy-load team
_team = None
def get_team():
    global _team
    if _team is None:
        from h_agent.team.team import AgentTeam
        _team = AgentTeam()
    return _team

# Lazy-load FullAgentHandler
_full_agent_handlers = {}
def get_full_agent_handler(agent_id: str):
    if agent_id not in _full_agent_handlers:
        from h_agent.team.agent import FullAgentHandler, AgentLoader
        profile = AgentLoader.load_profile(agent_id)
        _full_agent_handlers[agent_id] = FullAgentHandler(agent_id, profile)
    return _full_agent_handlers[agent_id]

app = Flask(__name__, 
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))

STATIC_DIR = Path(__file__).parent / "static"


def get_agent_tools():
    """Get tools list compatible with the agent."""
    tools = []
    for t in CORE_TOOLS:
        tools.append({
            "type": "function",
            "function": {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "parameters": t["function"].get("parameters", {})
            }
        })
    return tools


async def run_agent_async(messages: list, q: queue.Queue):
    """Run the agent loop and put SSE events into a queue."""
    from openai import OpenAI
    
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    tools = get_agent_tools()
    system_prompt = f"You are a helpful AI assistant. Current directory: {os.getcwd()}"
    
    api_messages = [{"role": "system", "content": system_prompt}] + messages
    
    try:
        while True:
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=4096,
                )
                
                message = response.choices[0].message
                content = message.content or ""
                tool_calls = message.tool_calls
                
                if content:
                    q.put(("token", {"content": content}))
                else:
                    # Tool call without content - show the tool name
                    if tool_calls:
                        for tc in tool_calls:
                            args = json.loads(tc.function.arguments)
                            q.put(("token", {"content": f"[Calling tool: {tc.function.name}]"}))
                
                if not tool_calls:
                    break
                
                for tool_call in tool_calls:
                    args_dict = json.loads(tool_call.function.arguments)
                    key = list(args_dict.keys())[0] if args_dict else ""
                    val = args_dict.get(key, "")[:60] if key else ""
                    q.put(("tool_start", {"name": tool_call.function.name, "args": val}))
                    
                    result = execute_tool_call(tool_call)
                    if len(result) > 50000:
                        result = result[:25000] + "\n...[truncated]\n" + result[-25000:]
                    
                    q.put(("tool_end", {"name": tool_call.function.name, "result": result[:500]}))
                    q.put(("token", {"content": f"[Tool result: {result[:200]}]\n"}))
                    
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
                q.put(("error", {"error": str(e)}))
                break
        
        q.put(("end", {"done": True}))
        
    except Exception as e:
        q.put(("error", {"error": str(e)}))


# ---- Routes ----

@app.route("/")
def index():
    """Serve the main chat page."""
    return render_template("index.html")

@app.route("/api/sessions", methods=["GET"])
def api_list_sessions():
    """List all sessions."""
    mgr = get_manager()
    sessions = mgr.list_sessions()
    return jsonify({"success": True, "sessions": sessions})

@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    """Create a new session."""
    data = request.json or {}
    mgr = get_manager()
    session = mgr.create_session(data.get("name"), data.get("group"))
    return jsonify({"success": True, "session": session})

@app.route("/api/agents", methods=["GET"])
def api_list_agents():
    """List all available agents (default + team members)."""
    team = get_team()
    members = team.list_members()

    agents = [
        {
            "id": "__default__",
            "name": "默认助手",
            "role": "assistant",
            "description": "默认 AI 助手，可以执行各种任务",
            "team": None,
        }
    ]

    # Add team members
    for m in members:
        agents.append({
            "id": m["name"],
            "name": m["name"],
            "role": m["role"],
            "description": m["description"] or f"{m['role']} agent",
            "team": team.team_id,
        })

    return jsonify({"success": True, "agents": agents})


@app.route("/api/agents/<agent_id>/message", methods=["POST"])
def api_agent_message(agent_id):
    """Send a message to a team agent and stream response via SSE."""
    data = request.json or {}
    message = data.get("message", "")
    session_id = data.get("session_id")
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    def generate():
        try:
            handler = get_full_agent_handler(agent_id)
            
            for event in handler.run_streaming(message, session_id):
                event_type = event["event"]
                event_data = event["data"]
                
                if event_type == "token":
                    yield f"event: token\ndata: {json.dumps({'token': event_data['token']})}\n\n"
                elif event_type == "tool_start":
                    yield f"event: tool_start\ndata: {json.dumps({'name': event_data['name'], 'args': event_data['args']})}\n\n"
                elif event_type == "tool_end":
                    yield f"event: tool_end\ndata: {json.dumps({'name': event_data['name'], 'result': event_data['result']})}\n\n"
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'error': event_data['error']})}\n\n"
                elif event_type == "end":
                    yield f"event: end\ndata: {json.dumps({'done': event_data['done']})}\n\n"
                    
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            yield f"event: end\ndata: {json.dumps({'done': True})}\n\n"
    
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/teams", methods=["GET"])
def api_list_teams():
    """List all teams and their members."""
    team = get_team()
    members = team.list_members()

    return jsonify({
        "success": True,
        "teams": [
            {
                "team_id": team.team_id,
                "members": members,
            }
        ]
    })


@app.route("/api/sessions/<session_id>/history", methods=["GET"])
def api_session_history(session_id):
    """Get session message history."""
    mgr = get_manager()
    history = mgr.get_history(session_id)
    return jsonify({"success": True, "history": history})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Start a chat stream using SSE."""
    data = request.json or {}
    session_id = data.get("session_id")
    message = data.get("message", "")
    agent_id = data.get("agent", "__default__")
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    # Get or create session
    mgr = get_manager()
    if not session_id:
        session_name = message[:50] + "..." if len(message) > 50 else message
        session = mgr.create_session(session_name)
        session_id = session["session_id"]
    
    # Add user message
    mgr.add_message(session_id, "user", message)
    
    # Get history
    messages = mgr.get_history(session_id)
    
    # Queue for communication between async task and SSE response
    q: queue.Queue = queue.Queue()
    
    def run_async():
        """Run the async agent in a separate thread with its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if agent_id == "__default__":
                loop.run_until_complete(run_agent_async(messages, q))
            else:
                loop.run_until_complete(run_team_agent_async(agent_id, message, messages, q))
        finally:
            loop.close()
    
    # Start async task in background thread
    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()
    
    def generate():
        while True:
            try:
                event_type, data = q.get(timeout=120)
                
                if event_type == "token":
                    yield f"event: token\ndata: {json.dumps({'token': data['content']})}\n\n"
                
                elif event_type == "tool_start":
                    yield f"event: tool_start\ndata: {json.dumps({'name': data['name'], 'args': data['args']})}\n\n"
                
                elif event_type == "tool_end":
                    yield f"event: tool_end\ndata: {json.dumps({'name': data['name'], 'result': data['result']})}\n\n"
                
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'error': data['error']})}\n\n"
                    break
                
                elif event_type == "end":
                    yield f"event: end\ndata: {json.dumps({'done': True, 'session_id': session_id})}\n\n"
                    break
                    
            except queue.Empty:
                yield f"event: error\ndata: {json.dumps({'error': 'Timeout waiting for response'})}\n\n"
                break
    
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


async def run_team_agent_async(agent_name: str, message: str, messages: list, q: queue.Queue):
    """Run a team agent and stream its response via SSE."""
    try:
        team = get_team()
        member = team.get_member(agent_name)
        
        if not member:
            q.put(("error", {"error": f"Agent '{agent_name}' not found"}))
            q.put(("end", {"done": True}))
            return
        
        if not member.enabled:
            q.put(("error", {"error": f"Agent '{agent_name}' is disabled"}))
            q.put(("end", {"done": True}))
            return
        
        # Use talk_to for conversational interaction
        from h_agent.team.team import TeamMessage, AgentRole
        
        msg = TeamMessage(
            msg_id=f"web-{os.urandom(4).hex()}",
            sender="user",
            receiver=agent_name,
            role=AgentRole.COORDINATOR,
            type="dialog",
            content=message,
        )
        
        result = member.handle_message(msg)
        
        if result.success:
            # Stream the response as tokens
            content = result.content or ""
            if content:
                q.put(("token", {"content": content}))
        else:
            q.put(("error", {"error": result.error or "Unknown error"}))
        
        q.put(("end", {"done": True}))
        
    except Exception as e:
        q.put(("error", {"error": str(e)}))
        q.put(("end", {"done": True}))

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    """Delete a session."""
    mgr = get_manager()
    deleted = mgr.delete_session(session_id)
    return jsonify({"success": deleted})


# ---- Startup ----

def run_server(port: int = 8080, open_browser: bool = True):
    """Run the web server."""
    import webbrowser
    import time
    
    if open_browser:
        def open_after_start():
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        t = threading.Thread(target=open_after_start, daemon=True)
        t.start()
    
    print(f"\033[36m🌐 h-agent Web UI\033[0m")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Network: http://0.0.0.0:{port}")
    print(f"\n  Press Ctrl+C to stop\n")
    
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="h-agent Web UI")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()
    run_server(port=args.port, open_browser=not args.no_browser)
