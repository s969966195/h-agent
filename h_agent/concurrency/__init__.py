"""
h_agent/concurrency/__init__.py - Named lane concurrency module.

Provides:
- LaneQueue: a named FIFO queue with max_concurrency control
- CommandQueue: central dispatcher routing work to named lanes
- Generation tracking for graceful task invalidation on restart

Usage:
    from h_agent.concurrency import CommandQueue, LANE_MAIN, LANE_CRON, LANE_HEARTBEAT

    q = CommandQueue()
    q.get_or_create_lane(LANE_MAIN, max_concurrency=1)

    # Enqueue work into a lane, get a Future
    future = q.enqueue(LANE_MAIN, lambda: expensive_computation())
    result = future.result(timeout=60)

    # Reset all lanes (invalidates old generation tasks)
    q.reset_all()
"""

from h_agent.concurrency.lanes import (
    LaneQueue,
    CommandQueue,
    LANE_MAIN,
    LANE_CRON,
    LANE_HEARTBEAT,
)

__all__ = [
    "LaneQueue",
    "CommandQueue",
    "LANE_MAIN",
    "LANE_CRON",
    "LANE_HEARTBEAT",
]
