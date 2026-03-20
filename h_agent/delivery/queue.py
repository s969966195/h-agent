"""
h_agent/delivery/queue.py - Disk-persistent delivery queue.

Write-ahead log: every outbound message is written to disk before delivery.
On crash/restart, pending messages are recovered from disk.

Atomic writes via tmp + os.replace().
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Optional

from h_agent.delivery.models import QueuedDelivery, MAX_RETRIES


class DeliveryQueue:
    """Reliable FIFO delivery queue with disk persistence."""

    def __init__(self, queue_dir: Optional[Path] = None, failed_dir: Optional[Path] = None):
        self.queue_dir = queue_dir or self._default_queue_dir()
        self.failed_dir = failed_dir or (self.queue_dir / "failed")
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def _default_queue_dir(self) -> Path:
        """Get default queue directory in agent workspace."""
        from h_agent.platform_utils import get_config_dir
        return get_config_dir() / "delivery-queue"

    def enqueue(self, channel: str, to: str, text: str, metadata: dict = None) -> str:
        """Create a delivery entry and atomically write to disk. Returns delivery_id."""
        delivery_id = uuid.uuid4().hex[:12]
        entry = QueuedDelivery(
            id=delivery_id,
            channel=channel,
            to=to,
            text=text,
            enqueued_at=time.time(),
            next_retry_at=0.0,
            metadata=metadata or {},
        )
        self._write_entry(entry)
        return delivery_id

    def _write_entry(self, entry: QueuedDelivery) -> None:
        """Atomic write: tmp file + os.replace()."""
        final_path = self.queue_dir / f"{entry.id}.json"
        tmp_path = self.queue_dir / f".tmp.{os.getpid()}.{entry.id}.json"
        data = json.dumps(entry.to_dict(), indent=2, ensure_ascii=False)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(final_path))

    def _read_entry(self, delivery_id: str) -> Optional[QueuedDelivery]:
        path = self.queue_dir / f"{delivery_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return QueuedDelivery.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def ack(self, delivery_id: str) -> None:
        """Mark delivery as successful — remove from queue."""
        path = self.queue_dir / f"{delivery_id}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def fail(self, delivery_id: str, error: str) -> None:
        """Increment retry count. Move to failed/ if exhausted."""
        entry = self._read_entry(delivery_id)
        if entry is None:
            return
        entry.retry_count += 1
        entry.last_error = error
        if entry.is_exhausted:
            self.move_to_failed(delivery_id)
            return
        entry.compute_next_retry()
        self._write_entry(entry)

    def move_to_failed(self, delivery_id: str) -> None:
        src = self.queue_dir / f"{delivery_id}.json"
        dst = self.failed_dir / f"{delivery_id}.json"
        try:
            os.replace(str(src), str(dst))
        except FileNotFoundError:
            pass

    def load_pending(self) -> List[QueuedDelivery]:
        """Scan queue dir, load all pending entries sorted by enqueue time."""
        entries: List[QueuedDelivery] = []
        if not self.queue_dir.exists():
            return entries
        for path in self.queue_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entries.append(QueuedDelivery.from_dict(json.load(f)))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        entries.sort(key=lambda e: e.enqueued_at)
        return entries

    def load_failed(self) -> List[QueuedDelivery]:
        """Load all permanently failed entries."""
        entries: List[QueuedDelivery] = []
        if not self.failed_dir.exists():
            return entries
        for path in self.failed_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entries.append(QueuedDelivery.from_dict(json.load(f)))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        entries.sort(key=lambda e: e.enqueued_at)
        return entries

    def retry_failed(self) -> int:
        """Move all failed/ entries back to queue with reset retry count."""
        count = 0
        if not self.failed_dir.exists():
            return count
        for path in list(self.failed_dir.glob("*.json")):
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entry = QueuedDelivery.from_dict(json.load(f))
                entry.retry_count = 0
                entry.last_error = None
                entry.next_retry_at = 0.0
                self._write_entry(entry)
                path.unlink()
                count += 1
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return count

    def stats(self) -> dict:
        """Return queue statistics."""
        pending = self.load_pending()
        failed = self.load_failed()
        return {
            "pending": len(pending),
            "failed": len(failed),
            "queue_dir": str(self.queue_dir),
        }

