"""
tests/test_channels.py - Tests for the channels module.
"""

import json
import time

import pytest

from h_agent.features.channels import (
    InboundMessage,
    OutboundMessage,
    ChannelManager,
    CLIChannel,
    MockChannel,
    build_channel_manager,
)


class TestInboundMessage:
    def test_session_key(self):
        msg = InboundMessage(
            text="hello",
            sender_id="user1",
            channel="dingtalk",
            account_id="acc1",
            peer_id="chat1",
        )
        assert msg.session_key == "dingtalk:acc1:chat1"

    def test_defaults(self):
        msg = InboundMessage(text="hi", sender_id="u1")
        assert msg.channel == ""
        assert msg.is_group is False
        assert msg.media == []


class TestOutboundMessage:
    def test_basic(self):
        msg = OutboundMessage(text="reply", channel="dingtalk", peer_id="chat1")
        assert msg.text == "reply"
        assert msg.metadata == {}


class TestMockChannel:
    def test_receive_and_handler(self):
        ch = MockChannel("test")
        received = []

        def handler(msg):
            received.append(msg)

        ch.set_handler(handler)
        msg = ch.receive("hello", sender_id="alice")
        assert msg.text == "hello"
        assert msg.sender_id == "alice"
        assert len(received) == 1

    def test_send(self):
        ch = MockChannel()
        ok = ch.send(OutboundMessage(text="reply", peer_id="alice"))
        assert ok is True
        assert len(ch.sent) == 1
        assert ch.sent[0].text == "reply"


class TestChannelManager:
    def test_register_and_get(self):
        mgr = ChannelManager()
        cli = CLIChannel()
        mgr.register(cli)
        assert mgr.get("cli") is cli
        assert mgr.list_channels() == ["cli"]

    def test_send_to_channel(self):
        mgr = ChannelManager()
        mock = MockChannel()
        mgr.register(mock)
        ok = mgr.send_to_channel(
            "mock",
            OutboundMessage(text="hello", channel="mock", peer_id="user1"),
        )
        assert ok is True
        assert len(mock.sent) == 1

    def test_unknown_channel_returns_false(self):
        mgr = ChannelManager()
        ok = mgr.send_to_channel("nonexistent", OutboundMessage(text="x"))
        assert ok is False


class TestCLIChannel:
    def test_receive_returns_inbound_message(self):
        ch = CLIChannel()
        # Can't easily test interactive input, just verify structure
        assert ch.name == "cli"


class TestBuildChannelManager:
    def test_build_with_no_env(self, monkeypatch):
        # Clear relevant env vars
        for key in ["DINGTALK_WEBHOOK_URL", "FEISHU_APP_ID",
                    "FEISHU_APP_SECRET", "TELEGRAM_BOT_TOKEN"]:
            monkeypatch.delenv(key, raising=False)
        mgr = build_channel_manager()
        # CLI should always be present
        assert "cli" in mgr.list_channels()
