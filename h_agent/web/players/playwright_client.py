"""
h_agent/web/players/playwright_client.py - Playwright Browser Client

Browser automation with Playwright.
Features:
- Launch browser (Chromium/Firefox/WebKit)
- Navigate, click, type, screenshot
- Extract/set cookies and localStorage tokens
- Header capture via request/response handlers
"""

import json
import os
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional, Iterator, Any
from pathlib import Path


@dataclass
class BrowserConfig:
    """Configuration for browser launch."""
    browser_type: str = "chromium"  # chromium, firefox, webkit
    headless: bool = True
    user_data_dir: Optional[str] = None  # For persistent sessions
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    proxy: Optional[str] = None  # e.g., "http://proxy:8080"
    timeout: int = 30000  # ms


@dataclass
class SessionState:
    """Captured browser session state."""
    cookies: list[dict] = field(default_factory=list)
    local_storage: dict[str, str] = field(default_factory=dict)
    session_storage: dict[str, str] = field(default_factory=dict)
    url: str = ""

    def save(self, path: str):
        """Save session state to a JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f)

    @classmethod
    def load(cls, path: str) -> "SessionState":
        """Load session state from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class HeaderCapture:
    """Captured request/response headers."""
    url: str
    request_headers: dict[str, str]
    response_headers: Optional[dict[str, str]] = None
    status_code: Optional[int] = None
    method: str = "GET"


class PlaywrightClient:
    """
    Playwright-based browser automation client.
    
    Example:
        client = PlaywrightClient()
        await client.launch()
        await client.navigate("https://example.com")
        await client.click("button.submit")
        await client.type("input[name='q']", "search query")
        screenshot = await client.screenshot()
        await client.close()
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._browser = None
        self._context = None
        self._page = None
        self._headers_capture: list[HeaderCapture] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _ensure_browser(self):
        """Ensure browser is launched."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                raise RuntimeError(
                    "playwright not installed. Run: pip install playwright && playwright install chromium"
                )
            
            self._playwright = await async_playwright().start()
            browser_type = self.config.browser_type
            
            launch_args = []
            if self.config.headless:
                launch_args.append("--headless")
            
            # Additional args for better compatibility
            launch_args.extend([
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ])
            
            launch_options = {
                "headless": self.config.headless,
                "args": launch_args,
            }
            
            if self.config.user_data_dir:
                launch_options["user_data_dir"] = self.config.user_data_dir
            
            if self.config.proxy:
                launch_options["proxy"] = {"server": self.config.proxy}
            
            self._browser = getattr(self._playwright, browser_type).launch(**launch_options)

    async def _create_context(self):
        """Create a new browser context."""
        await self._ensure_browser()
        
        context_options = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }
        
        if self.config.user_agent:
            context_options["user_agent"] = self.config.user_agent
        
        self._context = await self._browser.new_context(**context_options)
        
        # Set up header capture
        self._headers_capture = []
        self._context.on("request", self._on_request)
        self._context.on("response", self._on_response)
        
        self._page = await self._context.new_page()

    async def _on_request(self, request):
        """Capture request headers."""
        self._headers_capture.append(HeaderCapture(
            url=request.url,
            request_headers=dict(request.headers),
            method=request.method,
        ))

    async def _on_response(self, response):
        """Update captured headers with response info."""
        for cap in reversed(self._headers_capture):
            if cap.url == response.url:
                cap.response_headers = dict(response.headers)
                cap.status_code = response.status
                break

    # ---- Public API ----

    async def launch(self):
        """Launch browser and create context."""
        await self._create_context()
        return self

    async def navigate(self, url: str, wait_until: str = "load"):
        """
        Navigate to a URL.
        
        wait_until: "load", "domcontentloaded", "networkidle", "commit"
        """
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        await self._page.goto(url, wait_until=wait_until)
        return self

    async def click(self, selector: str, timeout: int = 30000):
        """Click an element by CSS selector."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        await self._page.click(selector, timeout=timeout)
        return self

    async def type(self, selector: str, text: str, delay: int = 0):
        """Type text into an input element."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        await self._page.fill(selector, text)
        if delay:
            await asyncio.sleep(delay / 1000)
        return self

    async def press(self, selector: str, key: str):
        """Press a key on an element or page."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        await self._page.press(selector, key)
        return self

    async def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> bytes:
        """
        Take a screenshot.
        
        Args:
            path: Optional file path to save to
            full_page: If True, capture the entire scrollable page
            
        Returns:
            PNG image bytes
        """
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        img = await self._page.screenshot(full_page=full_page, type="png")
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(img)
        return img

    async def get_cookies(self) -> list[dict]:
        """Get all cookies from current context."""
        if self._context is None:
            return []
        return await self._context.cookies()

    async def set_cookies(self, cookies: list[dict]):
        """Set cookies in current context."""
        if self._context is None:
            raise RuntimeError("Browser not launched.")
        await self._context.add_cookies(cookies)

    async def get_local_storage(self) -> dict[str, str]:
        """Get localStorage as a dict."""
        if self._page is None:
            return {}
        return await self._page.evaluate("() => ({ ...localStorage })")

    async def set_local_storage(self, data: dict[str, str]):
        """Set localStorage values."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        for key, value in data.items():
            await self._page.evaluate(
                f"() => {{ localStorage.setItem({json.dumps(key)}, {json.dumps(value)}) }}"
            )

    async def get_session_storage(self) -> dict[str, str]:
        """Get sessionStorage as a dict."""
        if self._page is None:
            return {}
        return await self._page.evaluate("() => ({ ...sessionStorage })")

    async def get_headers(self) -> list[HeaderCapture]:
        """Get captured request/response headers."""
        return self._headers_capture

    async def extract_tokens(self) -> dict[str, Any]:
        """
        Extract common auth tokens from the page.
        
        Looks for tokens in:
        - localStorage (auth_token, token, id_token, etc.)
        - sessionStorage
        - Cookies
        """
        tokens = {
            "localStorage": await self.get_local_storage(),
            "sessionStorage": await self.get_session_storage(),
            "cookies": await self.get_cookies(),
        }
        
        # Try to find token-like values
        token_keys = [
            "auth_token", "access_token", "id_token", "token",
            "refresh_token", "session_token", "jwt", "bearer",
        ]
        
        found_tokens = {}
        for key in token_keys:
            for storage_name, storage in [("localStorage", tokens["localStorage"]), 
                                           ("sessionStorage", tokens["sessionStorage"])]:
                if key in storage:
                    found_tokens[f"{storage_name}.{key}"] = storage[key]
        
        tokens["detected_tokens"] = found_tokens
        return tokens

    async def get_session_state(self) -> SessionState:
        """Get current session state (cookies + storage)."""
        return SessionState(
            cookies=await self.get_cookies(),
            local_storage=await self.get_local_storage(),
            session_storage=await self.get_session_storage(),
            url=self._page.url if self._page else "",
        )

    async def restore_session_state(self, state: SessionState):
        """Restore a previously saved session state."""
        if self._context is None:
            raise RuntimeError("Browser not launched.")
        
        if state.cookies:
            await self._context.add_cookies(state.cookies)
        
        if state.local_storage:
            await self.set_local_storage(state.local_storage)

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript in the page context."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        return await self._page.evaluate(script)

    async def wait_for_selector(self, selector: str, timeout: int = 30000):
        """Wait for a selector to appear."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        await self._page.wait_for_selector(selector, timeout=timeout)
        return self

    async def get_page_title(self) -> str:
        """Get the current page title."""
        if self._page is None:
            return ""
        return await self._page.title()

    async def get_current_url(self) -> str:
        """Get the current URL."""
        if self._page is None:
            return ""
        return self._page.url

    async def close(self):
        """Close the browser and cleanup."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ---- Synchronous wrappers for non-async use ----

    def launch_sync(self) -> "PlaywrightClient":
        """Synchronous wrapper for launch()."""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        
        if self._loop.is_running():
            # If loop is already running, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self._loop.run_until_complete, self.launch())
                return future.result()
        else:
            return self._loop.run_until_complete(self.launch())

    def close_sync(self):
        """Synchronous wrapper for close()."""
        if self._loop and not self._loop.is_closed():
            self._loop.run_until_complete(self.close())

    def __enter__(self):
        self.launch_sync()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_sync()
        return False
