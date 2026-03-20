"""
h_agent/features/channels/feishu.py - Feishu/Lark channel adapter.

Supports:
- Outbound via Feishu IM API (send messages to chats)
- Inbound via webhook callback URL

Setup:
1. Create a Feishu app at https://open.feishu.cn/app
2. Enable "Enable Bot" capability
3. Set permissions: im:message (send messages)
4. Get App ID and App Secret from Credentials tab
5. Set FEISHU_APP_ID, FEISHU_APP_SECRET in .env
6. Set webhook URL in your Feishu app's "Event Subscription"

For is_lark=True, uses https://open.larksuite.com/open-apis instead.
"""

import json
import os
import time
from typing import Optional, Callable, List, Dict, Any

from h_agent.features.channels.models import InboundMessage, OutboundMessage

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class FeishuChannel:
    """Feishu/Lark bot adapter.

    Sends via IM API with tenant token auth.
    Receives via webhook callback parsed by parse_event().
    """

    name = "feishu"

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        bot_open_id: str = "",
        is_lark: bool = False,
        account_id: str = "feishu-default",
        encrypt_key: str = "",
    ):
        if not HAS_HTTPX:
            raise RuntimeError("FeishuChannel requires httpx: pip install httpx")

        self.account_id = account_id
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self._encrypt_key = encrypt_key or os.getenv("FEISHU_ENCRYPT_KEY", "")
        self._bot_open_id = bot_open_id or os.getenv("FEISHU_BOT_OPEN_ID", "")
        is_lark = is_lark or os.getenv("FEISHU_IS_LARK", "").lower() in ("1", "true")
        self.api_base = (
            "https://open.larksuite.com/open-apis" if is_lark
            else "https://open.feishu.cn/open-apis"
        )
        self._tenant_token = ""
        self._token_expires_at = 0.0
        self._http = httpx.Client(timeout=15.0)
        self._on_message: Optional[Callable[[InboundMessage], None]] = None

    def set_handler(self, handler: Callable[[InboundMessage], None]) -> None:
        self._on_message = handler

    def _refresh_token(self) -> str:
        """Get a valid tenant access token, refreshing if expired."""
        if self._tenant_token and time.time() < self._token_expires_at:
            return self._tenant_token

        try:
            resp = self._http.post(
                f"{self.api_base}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()
            if data.get("code") != 0:
                print(f"[feishu] Token error: {data.get('msg', '?')}")
                return ""
            self._tenant_token = data.get("tenant_access_token", "")
            # Expire 5 min before actual expiry for safety margin
            self._token_expires_at = time.time() + data.get("expire", 7200) - 300
            return self._tenant_token
        except Exception as exc:
            print(f"[feishu] Token error: {exc}")
            return ""

    def _bot_mentioned(self, event: dict) -> bool:
        """Check if the bot was mentioned in a group message."""
        for m in event.get("message", {}).get("mentions", []):
            mid = m.get("id", {})
            if isinstance(mid, dict) and mid.get("open_id") == self._bot_open_id:
                return True
            if isinstance(mid, str) and mid == self._bot_open_id:
                return True
            if m.get("key") == self._bot_open_id:
                return True
        return False

    def _parse_content(self, message: dict) -> tuple[str, List[dict]]:
        """Parse Feishu message content to plain text."""
        msg_type = message.get("msg_type", "text")
        raw = message.get("content", "{}")
        try:
            content = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return "", []

        media: List[dict] = []
        if msg_type == "text":
            return content.get("text", ""), media
        if msg_type == "post":
            texts: List[str] = []
            for lc in content.values():
                if not isinstance(lc, dict):
                    continue
                title = lc.get("title", "")
                if title:
                    texts.append(title)
                for para in lc.get("content", []):
                    for node in para:
                        tag = node.get("tag")
                        if tag == "text":
                            texts.append(node.get("text", ""))
                        elif tag == "a":
                            texts.append(node.get("text", "") + " " + node.get("href", ""))
            return "\n".join(texts), media
        if msg_type == "image":
            key = content.get("image_key", "")
            if key:
                media.append({"type": "image", "key": key})
            return "[image]", media
        return "", media

    def parse_event(
        self, payload: dict, token: str = ""
    ) -> Optional[InboundMessage]:
        """Parse a Feishu webhook event payload.

        Handles text, post, and image messages.
        In groups, only processes messages where bot is mentioned.

        Args:
            payload: The JSON body from Feishu callback
            token: Verification token (from query param)

        Returns:
            InboundMessage or None (skip/error)
        """
        # URL verification challenge
        if "challenge" in payload:
            return None

        # Encrypt key verification
        if self._encrypt_key and token and token != self._encrypt_key:
            print("[feishu] Token verification failed")
            return None

        event = payload.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        user_id = sender.get("open_id", sender.get("user_id", ""))
        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "")
        is_group = chat_type == "group"

        # In groups, only respond if bot is mentioned
        if is_group and self._bot_open_id and not self._bot_mentioned(event):
            return None

        text, media = self._parse_content(message)
        if not text:
            return None

        return InboundMessage(
            text=text,
            sender_id=user_id,
            channel="feishu",
            account_id=self.account_id,
            peer_id=user_id if chat_type == "p2p" else chat_id,
            is_group=is_group,
            media=media,
            raw=payload,
        )

    def send(self, msg: OutboundMessage) -> bool:
        """Send a text message via Feishu IM API."""
        token = self._refresh_token()
        if not token:
            return False

        try:
            resp = self._http.post(
                f"{self.api_base}/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": msg.peer_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": msg.text}),
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                print(f"[feishu] Send error: {data.get('msg', '?')}")
                return False
            return True
        except Exception as exc:
            print(f"[feishu] Send error: {exc}")
            return False

    def close(self) -> None:
        self._http.close()
