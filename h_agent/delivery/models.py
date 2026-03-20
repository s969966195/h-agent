"""
h_agent/delivery/models.py - Delivery queue data models.

Defines QueuedDelivery and backoff utilities for reliable message delivery.
"""

import random
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


# Exponential backoff schedule: [5s, 25s, 2min, 10min]
BACKOFF_MS = [5_000, 25_000, 120_000, 600_000]
MAX_RETRIES = 5


def compute_backoff_ms(retry_count: int) -> int:
    """Exponential backoff with +/- 20% jitter to avoid thundering herd."""
    if retry_count <= 0:
        return 0
    idx = min(retry_count - 1, len(BACKOFF_MS) - 1)
    base = BACKOFF_MS[idx]
    jitter = random.randint(-base // 5, base // 5)
    return max(0, base + jitter)


@dataclass
class QueuedDelivery:
    """A message queued for delivery with retry support."""
    id: str
    channel: str
    to: str
    text: str
    retry_count: int = 0
    last_error: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    next_retry_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QueuedDelivery":
        return cls(**data)

    def compute_next_retry(self) -> None:
        """Update next_retry_at based on current retry_count."""
        backoff_ms = compute_backoff_ms(self.retry_count)
        self.next_retry_at = time.time() + backoff_ms / 1000.0

    @property
    def is_exhausted(self) -> bool:
        return self.retry_count >= MAX_RETRIES
