"""
h_agent/features/channels/manager.py - Channel manager and CLI adapter.

ChannelManager registers and dispatches across multiple channel adapters.
CLIChannel provides standard input/output interaction.
"""

from abc import ABC
import threading
import time
from typing import Callable, Dict, List, Optional

from h_agent.features.channels.models import InboundMessage, OutboundMessage

try:
    from h_agent.features.channels.telegram import TelegramChannel
except ImportError:
    TelegramChannel = None

try:
    from h_agent.features.channels.feishu import FeishuChannel
except ImportError:
    FeishuChannel = None

try:
    from h_agent.features.channels.dingtalk import DingTalkChannel
except ImportError:
    DingTalkChannel = None


class Channel(ABC):
    """Abstract channel base class."""

    name: str = "unknown"

    def __init__(self):
        self._on_message: Optional[Callable[[InboundMessage], None]] = None

    def set_handler(self, handler: Callable[[InboundMessage], None]) -> None:
        self._on_message = handler

    def send(self, msg: OutboundMessage) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        pass


class CLIChannel(Channel):
    """Standard input/output channel."""

    name = "cli"

    def __init__(self, account_id: str = "cli"):
        super().__init__()
        self.account_id = account_id
        self.running = False
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def receive(self) -> Optional[InboundMessage]:
        """Blocking read from stdin (for sync use)."""
        try:
            text = input("\033[36mYou > \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not text:
            return None
        return InboundMessage(
            text=text,
            sender_id="user",
            channel="cli",
            account_id=self.account_id,
            peer_id="user",
        )

    def send(self, msg: OutboundMessage) -> bool:
        print(f"\033[32mAssistant: {msg.text}\033[0m")
        return True


class MockChannel(Channel):
    """In-memory mock channel for testing."""

    name = "mock"

    def __init__(self, account_id: str = "mock"):
        super().__init__()
        self.account_id = account_id
        self.received: List[InboundMessage] = []
        self.sent: List[OutboundMessage] = []

    def receive(self, text: str, sender_id: str = "test-user") -> InboundMessage:
        msg = InboundMessage(
            text=text,
            sender_id=sender_id,
            channel="mock",
            account_id=self.account_id,
        )
        self.received.append(msg)
        if self._on_message:
            self._on_message(msg)
        return msg

    def send(self, msg: OutboundMessage) -> bool:
        self.sent.append(msg)
        return True


class ChannelManager:
    """Register and manage multiple channel adapters."""

    def __init__(self):
        self.channels: Dict[str, Channel] = {}
        self._lock = threading.Lock()

    def register(self, channel: Channel) -> None:
        with self._lock:
            self.channels[channel.name] = channel

    def get(self, name: str) -> Optional[Channel]:
        return self.channels.get(name)

    def list_channels(self) -> List[str]:
        return list(self.channels.keys())

    def start_all(self) -> None:
        for ch in self.channels.values():
            if hasattr(ch, "start"):
                ch.start()

    def stop_all(self) -> None:
        for ch in self.channels.values():
            if hasattr(ch, "stop"):
                ch.stop()
            if hasattr(ch, "close"):
                ch.close()

    def send_to_channel(self, channel: str, msg: OutboundMessage) -> bool:
        ch = self.channels.get(channel)
        if ch:
            return ch.send(msg)
        return False


def build_channel_manager() -> ChannelManager:
    """Auto-configure and build a channel manager from environment.

    Reads DINGTALK_WEBHOOK_URL, FEISHU_APP_ID, TELEGRAM_BOT_TOKEN, etc.
    """
    import os
    mgr = ChannelManager()

    # CLI always included
    cli = CLIChannel()
    mgr.register(cli)

    # DingTalk
    dt_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    if dt_url and DingTalkChannel:
        dt = DingTalkChannel(webhook_url=dt_url)
        mgr.register(dt)

    # Feishu
    fs_id = os.getenv("FEISHU_APP_ID", "").strip()
    fs_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if fs_id and fs_secret and FeishuChannel:
        fs = FeishuChannel(app_id=fs_id, app_secret=fs_secret)
        mgr.register(fs)

    # Telegram (polling started separately)
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if tg_token and TelegramChannel:
        tg = TelegramChannel(bot_token=tg_token)
        mgr.register(tg)

    return mgr
