"""
h_agent/features/channels/telegram.py - Telegram Bot API adapter.

Supports long polling via Bot API getUpdates.
Features:
- Media group buffering (500ms window to collect all photos/docs)
- Text pasting buffer (1s window for long paste fragments)
- Forum/topic support
- Configurable allowed chats

Setup:
1. Create a bot via @BotFather -> get the bot token
2. Set TELEGRAM_BOT_TOKEN in .env
3. Optionally set TELEGRAM_ALLOWED_CHATS=chatid1,chatid2 for allowlist
"""

import os
import time
import json
from pathlib import Path
from typing import Optional, Callable, List

from h_agent.features.channels.models import InboundMessage, OutboundMessage

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _load_offset(path: Path) -> int:
    try:
        return int(path.read_text().strip())
    except Exception:
        return 0


def _save_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset))


class TelegramChannel:
    """Telegram Bot API adapter with long polling."""

    name = "telegram"
    MAX_MSG_LEN = 4096

    def __init__(
        self,
        bot_token: str = "",
        allowed_chats: str = "",
        account_id: str = "telegram-default",
    ):
        if not HAS_HTTPX:
            raise RuntimeError("TelegramChannel requires httpx: pip install httpx")

        self.account_id = account_id
        token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.allowed_chats = {
            c.strip() for c in allowed_chats.split(",") if c.strip()
        } if allowed_chats else set()
        allowed_chats_env = os.getenv("TELEGRAM_ALLOWED_CHATS", "")
        if allowed_chats_env and not self.allowed_chats:
            self.allowed_chats = {
                c.strip() for c in allowed_chats_env.split(",") if c.strip()
            }

        self._http = httpx.Client(timeout=35.0)
        self._offset_path = self._state_dir() / f"offset-{self.account_id}.txt"
        self._offset = _load_offset(self._offset_path)
        self._seen: set = set()
        self._media_groups: dict = {}
        self._text_buf: dict = {}
        self._on_message: Optional[Callable[[InboundMessage], None]] = None

    def _state_dir(self) -> Path:
        from h_agent.platform_utils import get_config_dir
        d = get_config_dir() / "channels" / "telegram"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def set_handler(self, handler: Callable[[InboundMessage], None]) -> None:
        self._on_message = handler

    def _api(self, method: str, **params) -> dict:
        """Make a Telegram Bot API call."""
        filtered = {k: v for k, v in params.items() if v is not None}
        try:
            resp = self._http.post(f"{self.base_url}/{method}", json=filtered)
            data = resp.json()
            if not data.get("ok"):
                print(f"[telegram] {method}: {data.get('description', '?')}")
                return {}
            return data.get("result", {})
        except Exception as exc:
            print(f"[telegram] {method}: {exc}")
            return {}

    def send_typing(self, chat_id: str) -> None:
        """Send typing indicator."""
        self._api("sendChatAction", chat_id=chat_id, action="typing")

    def poll(self) -> List[InboundMessage]:
        """Poll for updates, return list of collected InboundMessages."""
        result = self._api("getUpdates", offset=self._offset, timeout=30,
                           allowed_updates=["message"])
        if not result or not isinstance(result, list):
            return self._flush_all()

        for update in result:
            uid = update.get("update_id", 0)
            if uid >= self._offset:
                self._offset = uid + 1
                _save_offset(self._offset_path, self._offset)
            if uid in self._seen:
                continue
            self._seen.add(uid)
            if len(self._seen) > 5000:
                self._seen.clear()

            msg = update.get("message")
            if not msg:
                continue
            if msg.get("media_group_id"):
                self._buf_media(msg, update)
                continue
            inbound = self._parse(msg, update)
            if not inbound:
                continue
            if self.allowed_chats and inbound.peer_id not in self.allowed_chats:
                continue
            self._buf_text(inbound)

        return self._flush_all()

    def _flush_all(self) -> List[InboundMessage]:
        ready = self._flush_media()
        ready.extend(self._flush_text())
        return ready

    # --- Media group buffering (500ms window) ---

    def _buf_media(self, msg: dict, update: dict) -> None:
        mgid = msg["media_group_id"]
        if mgid not in self._media_groups:
            self._media_groups[mgid] = {"ts": time.monotonic(), "entries": []}
        self._media_groups[mgid]["entries"].append((msg, update))

    def _flush_media(self) -> List[InboundMessage]:
        now = time.monotonic()
        ready: List[InboundMessage] = []
        expired = [k for k, g in self._media_groups.items()
                   if (now - g["ts"]) >= 0.5]
        for mgid in expired:
            entries = self._media_groups.pop(mgid)["entries"]
            captions, media_items = [], []
            for m, _ in entries:
                if m.get("caption"):
                    captions.append(m["caption"])
                for mt in ("photo", "video", "document", "audio"):
                    if mt in m:
                        raw_m = m[mt]
                        if isinstance(raw_m, list) and raw_m:
                            fid = raw_m[-1].get("file_id", "")
                        elif isinstance(raw_m, dict):
                            fid = raw_m.get("file_id", "")
                        else:
                            fid = ""
                        media_items.append({"type": mt, "file_id": fid})
            inbound = self._parse(entries[0][0], entries[0][1])
            if inbound:
                inbound.text = "\n".join(captions) if captions else "[media group]"
                inbound.media = media_items
                if not self.allowed_chats or inbound.peer_id in self.allowed_chats:
                    ready.append(inbound)
        return ready

    # --- Text pasting buffer (1s window) ---
    # Telegram splits long pastes into multiple fragments

    def _buf_text(self, inbound: InboundMessage) -> None:
        key = (inbound.peer_id, inbound.sender_id)
        now = time.monotonic()
        if key in self._text_buf:
            self._text_buf[key]["text"] += "\n" + inbound.text
            self._text_buf[key]["ts"] = now
        else:
            self._text_buf[key] = {"text": inbound.text, "msg": inbound, "ts": now}

    def _flush_text(self) -> List[InboundMessage]:
        now = time.monotonic()
        ready: List[InboundMessage] = []
        expired = [k for k, b in self._text_buf.items()
                   if (now - b["ts"]) >= 1.0]
        for key in expired:
            buf = self._text_buf.pop(key)
            buf["msg"].text = buf["text"]
            ready.append(buf["msg"])
        return ready

    # --- Message parsing ---

    def _parse(self, msg: dict, raw_update: dict) -> Optional[InboundMessage]:
        chat = msg.get("chat", {})
        chat_type = chat.get("type", "")
        chat_id = str(chat.get("id", ""))
        user_id = str(msg.get("from", {}).get("id", ""))
        text = msg.get("text", "") or msg.get("caption", "")
        if not text:
            return None

        thread_id = msg.get("message_thread_id")
        is_forum = chat.get("is_forum", False)
        is_group = chat_type in ("group", "supergroup")

        if chat_type == "private":
            peer_id = user_id
        elif is_group and is_forum and thread_id is not None:
            peer_id = f"{chat_id}:topic:{thread_id}"
        else:
            peer_id = chat_id

        return InboundMessage(
            text=text,
            sender_id=user_id,
            channel="telegram",
            account_id=self.account_id,
            peer_id=peer_id,
            is_group=is_group,
            raw=raw_update,
        )

    def receive(self) -> Optional[InboundMessage]:
        """Receive a single message (for sync use)."""
        msgs = self.poll()
        return msgs[0] if msgs else None

    def send(self, msg: OutboundMessage) -> bool:
        """Send a text message (with chunking)."""
        chat_id, thread_id = msg.peer_id, None
        if ":topic:" in msg.peer_id:
            parts = msg.peer_id.split(":topic:")
            chat_id, thread_id = parts[0], int(parts[1]) if len(parts) > 1 else None

        ok = True
        for chunk in self._chunk(msg.text):
            if not self._api(
                "sendMessage",
                chat_id=chat_id,
                text=chunk,
                message_thread_id=thread_id,
            ):
                ok = False
        return ok

    def _chunk(self, text: str) -> List[str]:
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

    def close(self) -> None:
        self._http.close()
