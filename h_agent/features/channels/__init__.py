"""
h_agent/features/channels/__init__.py - Channel adapters module.
"""

from h_agent.features.channels.models import InboundMessage, OutboundMessage, ChannelAccount
from h_agent.features.channels.manager import ChannelManager, CLIChannel, MockChannel, build_channel_manager

try:
    from h_agent.features.channels.dingtalk import DingTalkChannel
except ImportError:
    DingTalkChannel = None

try:
    from h_agent.features.channels.feishu import FeishuChannel
except ImportError:
    FeishuChannel = None

try:
    from h_agent.features.channels.telegram import TelegramChannel
except ImportError:
    TelegramChannel = None

__all__ = [
    "InboundMessage",
    "OutboundMessage",
    "ChannelAccount",
    "ChannelManager",
    "CLIChannel",
    "MockChannel",
    "build_channel_manager",
    "DingTalkChannel",
    "FeishuChannel",
    "TelegramChannel",
]
