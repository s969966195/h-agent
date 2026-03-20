"""
h_agent/web/players/__init__.py - Web Player Package

Browser automation using Playwright.
Exposes tools via MCP protocol.
"""

from h_agent.web.players.playwright_client import (
    PlaywrightClient,
    BrowserConfig,
    SessionState,
    HeaderCapture,
)

from h_agent.web.players.mcp_server import (
    PlaywrightMCPServer,
    get_mcp_tools,
    handle_mcp_tool_call,
    reset_client,
)

__all__ = [
    "PlaywrightClient",
    "BrowserConfig", 
    "SessionState",
    "HeaderCapture",
    "PlaywrightMCPServer",
    "get_mcp_tools",
    "handle_mcp_tool_call",
    "reset_client",
]
