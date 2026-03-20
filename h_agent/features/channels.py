#!/usr/bin/env python3
"""
h_agent/features/channels.py - Multi-Channel Support (Unified API)

同一大脑，多个嘴巴。
Channel 封装了平台差异，使 agent 循环只看到统一的 InboundMessage。

支持的通道:
  - CLI (标准输入输出)           -- always available
  - DingTalk (钉钉)              -- via custom robot webhook
  - Feishu/Lark (飞书)           -- via IM API + webhook callback
  - Telegram                     -- via Bot API long polling
  - Mock                          -- in-memory for testing

所有通道都产生相同的 InboundMessage 结构，agent 循环无需感知平台差异。

快速开始:
    from h_agent.features.channels import build_channel_manager

    mgr = build_channel_manager()
    for ch_name in mgr.list_channels():
        print(f"  - {ch_name}")

    # 设置消息处理
    def handle(inbound):
        reply = process_with_llm(inbound.text)
        mgr.send_to_channel(inbound.channel,
            OutboundMessage(text=reply, channel=inbound.channel,
                           peer_id=inbound.peer_id))

    cli = mgr.get("cli")
    msg = cli.receive()
    if msg:
        handle(msg)

.env 配置项:
    DINGTALK_WEBHOOK_URL     钉钉机器人 Webhook URL
    DINGTALK_SECRET          钉钉签名密钥
    FEISHU_APP_ID           飞书 App ID
    FEISHU_APP_SECRET        飞书 App Secret
    FEISHU_BOT_OPEN_ID      飞书机器人 Open ID
    FEISHU_ENCRYPT_KEY      飞书回调加密密钥
    FEISHU_IS_LARK          是否使用 Lark (1/true = 是)
    TELEGRAM_BOT_TOKEN      Telegram Bot Token
    TELEGRAM_ALLOWED_CHATS   Telegram 允许的聊天 ID（逗号分隔）
"""

import os
import sys

# Add parent to path for sub-module imports when running directly
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from h_agent.features.channels.models import (
    InboundMessage,
    OutboundMessage,
    ChannelAccount,
)
from h_agent.features.channels.manager import (
    ChannelManager,
    CLIChannel,
    MockChannel,
    build_channel_manager,
)

# Lazy imports for platform-specific adapters
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
    # Models
    "InboundMessage",
    "OutboundMessage",
    "ChannelAccount",
    # Manager
    "ChannelManager",
    "CLIChannel",
    "MockChannel",
    "build_channel_manager",
    # Adapters (may be None if dependencies missing)
    "DingTalkChannel",
    "FeishuChannel",
    "TelegramChannel",
]
