"""
h_agent/delivery/runner.py - Background delivery runner.

DeliveryRunner is a background thread that processes the delivery queue,
attempting to send each message and applying exponential backoff on failure.
"""

import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from h_agent.delivery.models import QueuedDelivery, MAX_RETRIES, compute_backoff_ms
from h_agent.delivery.queue import DeliveryQueue


# Channel-specific message size limits
CHANNEL_LIMITS: Dict[str, int] = {
    "telegram": 4096,
    "feishu": 4096,
    "dingtalk": 4096,
    "discord": 2000,
    "whatsapp": 4096,
    "cli": 65536,
    "default": 4096,
}


def chunk_message(text: str, channel: str = "default") -> List[str]:
    """Split a message into chunks respecting channel limits.

    Strategy: paragraph-first, then hard-cut at limit.
    """
    if not text:
        return []
    limit = CHANNEL_LIMITS.get(channel, CHANNEL_LIMITS["default"])
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    for para in text.split("\n\n"):
        if chunks and len(chunks[-1]) + len(para) + 2 <= limit:
            chunks[-1] += "\n\n" + para
        else:
            while len(para) > limit:
                chunks.append(para[:limit])
                para = para[limit:]
            if para:
                chunks.append(para)
    return chunks or [text[:limit]]


class DeliveryRunner:
    """Background thread that processes the delivery queue with retry logic."""

    def __init__(
        self,
        queue: Optional[DeliveryQueue] = None,
        deliver_fn: Optional[Callable[[str, str, str], None]] = None,
        queue_dir: Optional[Path] = None,
    ):
        self._queue = queue or DeliveryQueue(queue_dir=queue_dir)
        self._deliver_fn = deliver_fn or self._default_deliver
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._total_attempted = 0
        self._total_succeeded = 0
        self._total_failed = 0

    def _default_deliver(self, channel: str, to: str, text: str) -> None:
        """Default deliver function — logs to stdout."""
        print(f"[delivery][{channel}] -> {to}: {text[:60]}...")

    def start(self) -> None:
        """Start the background delivery thread after a recovery scan."""
        self._recovery_scan()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="delivery-runner",
        )
        self._thread.start()

    def _recovery_scan(self) -> None:
        """On startup, report pending and failed entries."""
        pending = self._queue.load_pending()
        failed = self._queue.load_failed()
        parts = []
        if pending:
            parts.append(f"{len(pending)} pending")
        if failed:
            parts.append(f"{len(failed)} failed")
        msg = f"Recovery: {', '.join(parts)}" if parts else "Recovery: queue is clean"
        print(f"[delivery] {msg}")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_pending()
            except Exception as exc:
                print(f"[delivery] Loop error: {exc}")
            self._stop_event.wait(timeout=1.0)

    def _process_pending(self) -> None:
        """Process all entries whose next_retry_at has passed."""
        pending = self._queue.load_pending()
        now = time.time()

        for entry in pending:
            if self._stop_event.is_set():
                break
            if entry.next_retry_at > now:
                continue

            self._total_attempted += 1
            try:
                self._deliver_fn(entry.channel, entry.to, entry.text)
                self._queue.ack(entry.id)
                self._total_succeeded += 1
            except Exception as exc:
                error_msg = str(exc)
                self._queue.fail(entry.id, error_msg)
                self._total_failed += 1
                retry = entry.retry_count + 1
                if retry >= MAX_RETRIES:
                    print(f"[delivery] {entry.id[:8]}... -> failed/ (exhausted): {error_msg}")
                else:
                    backoff_s = compute_backoff_ms(retry) / 1000
                    print(f"[delivery] {entry.id[:8]}... failed (retry {retry}/{MAX_RETRIES}), "
                          f"next in {backoff_s:.0f}s: {error_msg}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def stats(self) -> dict:
        return {
            "pending": len(self._queue.load_pending()),
            "failed": len(self._queue.load_failed()),
            "total_attempted": self._total_attempted,
            "total_succeeded": self._total_succeeded,
            "total_failed": self._total_failed,
        }

    def enqueue(self, channel: str, to: str, text: str) -> str:
        """Convenience method: enqueue a message for delivery."""
        return self._queue.enqueue(channel, to, text)
