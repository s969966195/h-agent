"""
h_agent/features/channels/models.py - Channel data models.

Unified message types used across all channel adapters.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InboundMessage:
    """Normalized inbound message from any channel.

    All channel adapters produce this structure. The agent loop
    only sees InboundMessage — platform differences are hidden.
    """
    text: str
    sender_id: str
    channel: str = ""
    account_id: str = ""
    peer_id: str = ""          # Group/channel ID (vs sender_id for DMs)
    is_group: bool = False
    media: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)  # Original platform payload

    @property
    def session_key(self) -> str:
        """Unique key for this conversation: channel:account:peer"""
        return f"{self.channel}:{self.account_id}:{self.peer_id}"


@dataclass
class OutboundMessage:
    """Normalized outbound message to any channel."""
    text: str
    channel: str = ""
    peer_id: str = ""
    account_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelAccount:
    """Configuration for a single bot account on a channel."""
    channel: str
    account_id: str
    token: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
