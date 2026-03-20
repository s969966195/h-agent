"""
h_agent/web/players/mcp_server.py - Playwright MCP Server

Exposes Playwright browser automation as MCP tools.

MCP Tools:
- playwright_navigate(url) -> str
- playwright_click(selector) -> str  
- playwright_type(selector, text) -> str
- playwright_screenshot(path?) -> base64
- playwright_get_cookies() -> json
- playwright_set_cookies(cookies) -> str
- playwright_get_local_storage() -> json
- playwright_set_local_storage(data) -> str
- playwright_extract_tokens() -> json
- playwright_get_session_state() -> json
- playwright_restore_session_state(state) -> str
- playwright_evaluate(script) -> json
- playwright_get_headers() -> json
- playwright_get_page_info() -> json
"""

import json
import asyncio
import threading
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor

from h_agent.web.players.playwright_client import (
    PlaywrightClient,
    BrowserConfig,
    SessionState,
)


# Global client instance (thread-safe)
_client: Optional[PlaywrightClient] = None
_client_lock = threading.Lock()


def get_client() -> PlaywrightClient:
    """Get or create the global Playwright client."""
    global _client
    with _client_lock:
        if _client is None:
            _client = PlaywrightClient()
            # Launch synchronously in a thread
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(_client.launch_sync)
            executor.shutdown(wait=False)
        return _client


def set_client(client: PlaywrightClient):
    """Set the global client."""
    global _client
    with _client_lock:
        _client = client


def reset_client():
    """Close and reset the global client."""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close_sync()
            except Exception:
                pass
        _client = None


# ---- MCP Tool Handlers ----

def handle_navigate(url: str) -> str:
    """Navigate to a URL."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.navigate(url))
        return f"Navigated to {url}"
    finally:
        loop.close()


def handle_click(selector: str) -> str:
    """Click an element."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.click(selector))
        return f"Clicked element: {selector}"
    finally:
        loop.close()


def handle_type(selector: str, text: str) -> str:
    """Type text into an element."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.type(selector, text))
        return f"Typed into {selector}"
    finally:
        loop.close()


def handle_screenshot(path: Optional[str] = None, full_page: bool = False) -> str:
    """Take a screenshot."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        img_bytes = loop.run_until_complete(client.screenshot(path, full_page))
        import base64
        b64 = base64.b64encode(img_bytes).decode()
        return f"Screenshot taken: {len(img_bytes)} bytes (base64: {b64[:50]}...)"
    finally:
        loop.close()


def handle_get_cookies() -> str:
    """Get all cookies."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        cookies = loop.run_until_complete(client.get_cookies())
        return json.dumps(cookies, indent=2)
    finally:
        loop.close()


def handle_set_cookies(cookies_json: str) -> str:
    """Set cookies from JSON."""
    client = get_client()
    cookies = json.loads(cookies_json)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.set_cookies(cookies))
        return f"Set {len(cookies)} cookies"
    finally:
        loop.close()


def handle_get_local_storage() -> str:
    """Get localStorage."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        data = loop.run_until_complete(client.get_local_storage())
        return json.dumps(data, indent=2)
    finally:
        loop.close()


def handle_set_local_storage(data_json: str) -> str:
    """Set localStorage from JSON."""
    client = get_client()
    data = json.loads(data_json)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.set_local_storage(data))
        return f"Set {len(data)} localStorage items"
    finally:
        loop.close()


def handle_extract_tokens() -> str:
    """Extract auth tokens."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        tokens = loop.run_until_complete(client.extract_tokens())
        return json.dumps(tokens, indent=2)
    finally:
        loop.close()


def handle_get_session_state() -> str:
    """Get current session state."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        state = loop.run_until_complete(client.get_session_state())
        return json.dumps(asdict(state), indent=2)
    finally:
        loop.close()


def handle_restore_session_state(state_json: str) -> str:
    """Restore session state from JSON."""
    client = get_client()
    state_dict = json.loads(state_json)
    state = SessionState(**state_dict)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.restore_session_state(state))
        return "Session state restored"
    finally:
        loop.close()


def handle_evaluate(script: str) -> str:
    """Execute JavaScript."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(client.evaluate(script))
        return json.dumps(result, indent=2, default=str)
    finally:
        loop.close()


def handle_get_headers() -> str:
    """Get captured request/response headers."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        headers = loop.run_until_complete(client.get_headers())
        return json.dumps([asdict(h) for h in headers], indent=2, default=str)
    finally:
        loop.close()


def handle_get_page_info() -> str:
    """Get current page info (URL, title, etc.)."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        url = loop.run_until_complete(client.get_current_url())
        title = loop.run_until_complete(client.get_page_title())
        return json.dumps({"url": url, "title": title}, indent=2)
    finally:
        loop.close()


def handle_wait_for_selector(selector: str) -> str:
    """Wait for a selector."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.wait_for_selector(selector))
        return f"Selector found: {selector}"
    finally:
        loop.close()


def handle_press(selector: str, key: str) -> str:
    """Press a key."""
    client = get_client()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.press(selector, key))
        return f"Pressed {key} on {selector}"
    finally:
        loop.close()


# ---- MCP Tool Definitions ----

MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "playwright_navigate",
            "description": "Navigate to a URL in the browser",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_click",
            "description": "Click an element by CSS selector",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of element to click"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_type",
            "description": "Type text into an input element",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of input element"},
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_screenshot",
            "description": "Take a screenshot of the current page",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional file path to save screenshot"},
                    "full_page": {"type": "boolean", "description": "Capture entire scrollable page", "default": False}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_get_cookies",
            "description": "Get all cookies from current browser context",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_set_cookies",
            "description": "Set cookies in browser context",
            "parameters": {
                "type": "object",
                "properties": {
                    "cookies_json": {"type": "string", "description": "JSON array of cookie objects"}
                },
                "required": ["cookies_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_get_local_storage",
            "description": "Get all localStorage key-value pairs",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_set_local_storage",
            "description": "Set localStorage values",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_json": {"type": "string", "description": "JSON object of key-value pairs"}
                },
                "required": ["data_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_extract_tokens",
            "description": "Extract auth tokens from localStorage, sessionStorage, and cookies",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_get_session_state",
            "description": "Get current session state (cookies, localStorage, URL)",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_restore_session_state",
            "description": "Restore a previously saved session state",
            "parameters": {
                "type": "object",
                "properties": {
                    "state_json": {"type": "string", "description": "JSON session state from get_session_state"}
                },
                "required": ["state_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_evaluate",
            "description": "Execute JavaScript in the page context",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "JavaScript code to execute"}
                },
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_get_headers",
            "description": "Get captured request/response headers",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_get_page_info",
            "description": "Get current page URL and title",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_wait_for_selector",
            "description": "Wait for a selector to appear in the page",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_press",
            "description": "Press a key on an element or page",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (or 'body' for page-level)"},
                    "key": {"type": "string", "description": "Key name (e.g., 'Enter', 'Escape', 'Tab')"}
                },
                "required": ["selector", "key"]
            }
        }
    },
]


# Tool name -> handler function mapping
MCP_HANDLERS = {
    "playwright_navigate": lambda args: handle_navigate(args["url"]),
    "playwright_click": lambda args: handle_click(args["selector"]),
    "playwright_type": lambda args: handle_type(args["selector"], args["text"]),
    "playwright_screenshot": lambda args: handle_screenshot(args.get("path"), args.get("full_page", False)),
    "playwright_get_cookies": lambda args: handle_get_cookies(),
    "playwright_set_cookies": lambda args: handle_set_cookies(args["cookies_json"]),
    "playwright_get_local_storage": lambda args: handle_get_local_storage(),
    "playwright_set_local_storage": lambda args: handle_set_local_storage(args["data_json"]),
    "playwright_extract_tokens": lambda args: handle_extract_tokens(),
    "playwright_get_session_state": lambda args: handle_get_session_state(),
    "playwright_restore_session_state": lambda args: handle_restore_session_state(args["state_json"]),
    "playwright_evaluate": lambda args: handle_evaluate(args["script"]),
    "playwright_get_headers": lambda args: handle_get_headers(),
    "playwright_get_page_info": lambda args: handle_get_page_info(),
    "playwright_wait_for_selector": lambda args: handle_wait_for_selector(args["selector"]),
    "playwright_press": lambda args: handle_press(args["selector"], args["key"]),
}


def get_mcp_tools() -> list[dict]:
    """Get all Playwright MCP tool definitions."""
    return MCP_TOOLS


def handle_mcp_tool_call(tool_name: str, arguments: dict) -> str:
    """Handle an MCP tool call."""
    handler = MCP_HANDLERS.get(tool_name)
    if not handler:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return handler(arguments)
    except Exception as e:
        return f"Error: {str(e)}"


class PlaywrightMCPServer:
    """
    MCP server that exposes Playwright tools.
    
    Can be used standalone or integrated with an MCP client.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._running = False

    def get_tools(self) -> list[dict]:
        """Get tool definitions."""
        return MCP_TOOLS

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool and return the result."""
        return handle_mcp_tool_call(tool_name, arguments)

    def start(self):
        """Start the browser."""
        global _client
        with _client_lock:
            if _client is not None:
                reset_client()
            _client = PlaywrightClient(self.config)
            _client.launch_sync()
        self._running = True

    def stop(self):
        """Stop the browser."""
        reset_client()
        self._running = False


# Helper for dataclass asdict with nested
def asdict(obj):
    """Convert dataclass to dict recursively."""
    import dataclasses
    if dataclasses.is_dataclass(obj):
        result = {}
        for k, v in dataclasses.asdict(obj).items():
            result[k] = asdict(v)
        return result
    elif isinstance(obj, list):
        return [asdict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: asdict(v) for k, v in obj.items()}
    return obj
