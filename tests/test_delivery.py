"""
tests/test_delivery.py - Tests for the delivery module.
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from h_agent.delivery import (
    DeliveryQueue,
    DeliveryRunner,
    QueuedDelivery,
    chunk_message,
    compute_backoff_ms,
    MAX_RETRIES,
)


class TestQueuedDelivery:
    def test_to_dict_roundtrip(self):
        entry = QueuedDelivery(
            id="test123",
            channel="dingtalk",
            to="user1",
            text="Hello!",
        )
        data = entry.to_dict()
        restored = QueuedDelivery.from_dict(data)
        assert restored.id == entry.id
        assert restored.channel == entry.channel
        assert restored.to == entry.to
        assert restored.text == entry.text

    def test_is_exhausted(self):
        entry = QueuedDelivery(id="x", channel="c", to="t", text="m")
        assert not entry.is_exhausted
        entry.retry_count = MAX_RETRIES
        assert entry.is_exhausted

    def test_compute_next_retry(self):
        entry = QueuedDelivery(id="x", channel="c", to="t", text="m", retry_count=1)
        entry.compute_next_retry()
        assert entry.next_retry_at > time.time()


class TestBackoff:
    def test_backoff_positive(self):
        assert compute_backoff_ms(1) > 0
        # With jitter, check that values are within expected bounds
        from h_agent.delivery.models import BACKOFF_MS
        # retry 1 → 5s base, retry 2 → 25s, retry 3 → 2min, retry 4+ → 10min
        # With +/-20% jitter, each should be at least 80% of base
        assert compute_backoff_ms(1) >= BACKOFF_MS[0] * 0.8
        assert compute_backoff_ms(2) >= BACKOFF_MS[1] * 0.8
        assert compute_backoff_ms(3) >= BACKOFF_MS[2] * 0.8
        assert compute_backoff_ms(4) >= BACKOFF_MS[3] * 0.8

    def test_backoff_zero(self):
        assert compute_backoff_ms(0) == 0


class TestChunkMessage:
    def test_short_message(self):
        chunks = chunk_message("hello", "dingtalk")
        assert chunks == ["hello"]

    def test_long_message_split(self):
        text = "a" * 5000
        chunks = chunk_message(text, "dingtalk")
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 4096

    def test_paragraph_split(self):
        text = "Para1\n\n" + "b" * 3000 + "\n\nPara3"
        chunks = chunk_message(text, "feishu")
        assert len(chunks) >= 1

    def test_empty_message(self):
        assert chunk_message("", "dingtalk") == []


class TestDeliveryQueue:
    def test_enqueue_returns_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            delivery_id = q.enqueue("dingtalk", "user1", "test message")
            assert delivery_id is not None
            assert len(delivery_id) == 12

    def test_load_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            q.enqueue("dingtalk", "user1", "msg1")
            q.enqueue("feishu", "user2", "msg2")
            pending = q.load_pending()
            assert len(pending) == 2

    def test_ack_removes_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            did = q.enqueue("dingtalk", "user1", "test")
            q.ack(did)
            assert q.load_pending() == []

    def test_fail_increments_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            did = q.enqueue("dingtalk", "user1", "test")
            q.fail(did, "network error")
            entry = q._read_entry(did)
            assert entry is not None
            assert entry.retry_count == 1
            assert entry.last_error == "network error"

    def test_fail_exhausted_moves_to_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            did = q.enqueue("dingtalk", "user1", "test")
            for _ in range(MAX_RETRIES):
                q.fail(did, "error")
            assert q.load_pending() == []
            failed = q.load_failed()
            assert len(failed) == 1
            assert failed[0].id == did

    def test_retry_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            did = q.enqueue("dingtalk", "user1", "test")
            for _ in range(MAX_RETRIES):
                q.fail(did, "error")
            count = q.retry_failed()
            assert count == 1
            assert len(q.load_failed()) == 0
            assert len(q.load_pending()) == 1
            restored = q._read_entry(did)
            assert restored.retry_count == 0

    def test_atomic_write(self):
        """Verify no leftover .tmp files after enqueue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            q.enqueue("dingtalk", "user1", "test")
            tmp_files = list(Path(tmpdir).glob(".tmp.*"))
            assert len(tmp_files) == 0


class TestDeliveryRunner:
    def test_enqueue_creates_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            runner = DeliveryRunner(queue=q, deliver_fn=lambda c, t, m: None)
            runner.start()
            time.sleep(0.1)
            runner.enqueue("dingtalk", "user1", "hello")
            time.sleep(1.5)  # Wait for background thread to process (1s poll)
            stats = runner.stats()
            assert stats["pending"] == 0  # Should be delivered
            assert stats["total_attempted"] >= 1
            runner.stop()

    def test_retry_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            q = DeliveryQueue(queue_dir=Path(tmpdir))
            failures = []

            def failing_fn(channel, to, text):
                failures.append(text)
                raise ConnectionError("simulated")

            runner = DeliveryRunner(queue=q, deliver_fn=failing_fn)
            runner.start()
            runner.enqueue("dingtalk", "user1", "will fail")
            time.sleep(1.5)  # Wait for background thread to process (1s poll)
            runner.stop()
            assert len(failures) >= 1
            stats = runner.stats()
            assert stats["total_failed"] >= 1
            assert stats["pending"] == 1  # Still in queue for retry
