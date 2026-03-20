"""
h_agent/delivery/__init__.py - Reliable message delivery module.

Provides disk-persistent delivery queue with exponential backoff retry.

Usage:
    from h_agent.delivery import DeliveryQueue, DeliveryRunner

    queue = DeliveryQueue()
    runner = DeliveryRunner(queue, deliver_fn=my_send_function)
    runner.start()

    # Enqueue a message for delivery
    runner.enqueue("dingtalk", "user123", "Hello from h-agent!")
"""

from h_agent.delivery.models import QueuedDelivery, compute_backoff_ms, MAX_RETRIES
from h_agent.delivery.queue import DeliveryQueue
from h_agent.delivery.runner import DeliveryRunner, chunk_message, CHANNEL_LIMITS

__all__ = [
    "QueuedDelivery",
    "DeliveryQueue",
    "DeliveryRunner",
    "chunk_message",
    "compute_backoff_ms",
    "MAX_RETRIES",
    "CHANNEL_LIMITS",
]
