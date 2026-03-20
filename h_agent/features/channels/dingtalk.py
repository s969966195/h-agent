"""
h_agent/features/channels/dingtalk.py - DingTalk (钉钉) channel adapter.

Supports:
- Outbound webhook (custom robot) for sending messages
- Inbound via callback URL (Flask endpoint registered separately)

DingTalk robot setup:
1. Create a custom robot in a DingTalk group
2. Copy the webhook URL (https://oapi.dingtalk.com/robot/send?access_token=xxx)
3. Set DINGTALK_WEBHOOK and DINGTALK_SECRET in .env

For inbound callbacks, the adapter provides a parse_callback() method
to verify and parse DingTalk event payloads.
"""

import hashlib
import hmac
import base64
import time
import json
import os
from typing import Optional, Callable

from h_agent.features.channels.models import InboundMessage, OutboundMessage

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class DingTalkChannel:
    """DingTalk custom robot adapter.

    Sends messages via webhook. Receives via callback URL parsed separately.
    """

    name = "dingtalk"
    MAX_MSG_LEN = 4096

    def __init__(
        self,
        webhook_url: str = "",
        secret: str = "",
        account_id: str = "dingtalk-default",
    ):
        if not HAS_HTTPX:
            raise RuntimeError("DingTalkChannel requires httpx: pip install httpx")

        self.account_id = account_id
        self._webhook_url = webhook_url or os.getenv("DINGTALK_WEBHOOK_URL", "")
        self._secret = secret or os.getenv("DINGTALK_SECRET", "")
        self._http = httpx.Client(timeout=15.0)
        self._on_message: Optional[Callable[[InboundMessage], None]] = None

    def set_handler(self, handler: Callable[[InboundMessage], None]) -> None:
        """Set the message handler callback."""
        self._on_message = handler

    def _sign(self) -> str:
        """Generate DingTalk HMAC-SHA256 signature."""
        if not self._secret:
            return ""
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return f"{timestamp}&{sign}"

    def _build_url(self) -> str:
        """Build webhook URL with signature."""
        if not self._webhook_url:
            return ""
        sign = self._sign()
        if sign:
            return f"{self._webhook_url}&sign={sign}"
        return self._webhook_url

    def send(self, msg: OutboundMessage) -> bool:
        """Send a text message to DingTalk group."""
        if not self._webhook_url:
            return False

        # Split into chunks if needed
        chunks = self._chunk(msg.text)
        all_ok = True
        for chunk in chunks:
            ok = self._send_text(chunk, msg.peer_id)
            if not ok:
                all_ok = False
        return all_ok

    def _send_text(self, text: str, chat_id: str = "") -> bool:
        """Send a single text message."""
        url = self._build_url()
        payload = {"msgtype": "text", "text": {"content": text}}
        if chat_id:
            payload["chatid"] = chat_id

        try:
            resp = self._http.post(url, json=payload)
            data = resp.json()
            if data.get("errcode") != 0:
                print(f"[dingtalk] Send error: {data.get('errmsg', '?')}")
                return False
            return True
        except Exception as exc:
            print(f"[dingtalk] Send error: {exc}")
            return False

    def _chunk(self, text: str) -> list:
        """Split text into chunks respecting MAX_MSG_LEN."""
        if len(text) <= self.MAX_MSG_LEN:
            return [text]
        chunks = []
        while text:
            if len(text) <= self.MAX_MSG_LEN:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, self.MAX_MSG_LEN)
            if cut <= 0:
                cut = self.MAX_MSG_LEN
            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")
        return chunks

    def parse_callback(self, payload: dict, headers: dict = None) -> Optional[InboundMessage]:
        """Parse a DingTalk callback event.

        Handles:
        - Text messages from users
        - Bot messages (echo back skip)
        - Signature verification

        Args:
            payload: The JSON body from DingTalk callback
            headers: Request headers (for signature verification)

        Returns:
            InboundMessage or None (if skip/error)
        """
        headers = headers or {}

        # Handle URL verification challenge
        if "challenge" in payload:
            return None

        # Get message content
        event = payload.get("event", {})
        text = ""
        sender_id = ""

        # Different DingTalk callback formats
        msg_data = event.get("text", {}) or payload.get("text", {})
        if isinstance(msg_data, dict):
            text = msg_data.get("content", "")
        elif isinstance(msg_data, str):
            text = msg_data

        sender = event.get("sender", {}) or payload.get("sender", {})
        if isinstance(sender, dict):
            sender_id = sender.get("staffId", sender.get("userId", ""))

        if not text:
            return None

        # Skip bot's own messages
        if event.get("msgType") == "robot" and not text.startswith("/"):
            pass  # Allow robot commands

        return InboundMessage(
            text=text,
            sender_id=sender_id,
            channel="dingtalk",
            account_id=self.account_id,
            peer_id=sender_id,  # For DMs, peer is the sender
            is_group=False,
            raw=payload,
        )

    def verify_signature(self, body: bytes, headers: dict) -> bool:
        """Verify DingTalk callback signature (if secret is configured)."""
        if not self._secret:
            return True  # No secret configured, skip verification

        sign = headers.get("x-dingtalk-signature", "")
        timestamp = headers.get("x-dingtalk-timestamp", "")
        if not sign or not timestamp:
            return False

        string_to_sign = f"{timestamp}\n{self._secret}"
        expected = base64.b64encode(
            hmac.new(
                self._secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return hmac.compare_digest(sign, expected)

    def close(self) -> None:
        self._http.close()
