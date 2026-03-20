"""
tests/test_concurrency.py - Tests for the concurrency/lanes module.
"""

import threading
import time
import concurrent.futures

import pytest

from h_agent.concurrency import (
    LaneQueue,
    CommandQueue,
    LANE_MAIN,
    LANE_CRON,
    LANE_HEARTBEAT,
)


class TestLaneQueue:
    def test_enqueue_returns_future(self):
        lane = LaneQueue("test", max_concurrency=1)
        future = lane.enqueue(lambda: 42)
        assert isinstance(future, concurrent.futures.Future)
        assert future.result(timeout=5) == 42

    def test_fifo_order(self):
        lane = LaneQueue("test", max_concurrency=1)
        results = []

        def make_adder(n):
            return lambda: results.append(n)

        lane.enqueue(make_adder(1))
        lane.enqueue(make_adder(2))
        lane.enqueue(make_adder(3))
        lane.wait_for_idle(timeout=5)
        assert results == [1, 2, 3]

    def test_max_concurrency_respected(self):
        lane = LaneQueue("test", max_concurrency=1)
        active = []
        lock = threading.Lock()

        def hold():
            with lock:
                active.append(1)
            time.sleep(0.2)
            with lock:
                active.pop()
            return "done"

        # Submit 3 tasks, only 1 should be active at a time
        futures = [lane.enqueue(hold) for _ in range(3)]
        time.sleep(0.05)
        assert len(active) == 1  # max=1
        for f in futures:
            f.result(timeout=5)
        lane.wait_for_idle(timeout=5)

    def test_generation_increment(self):
        lane = LaneQueue("test")
        assert lane.generation == 0
        with lane._condition:
            lane._generation = 5
        assert lane.generation == 5

    def test_wait_for_idle_timeout(self):
        lane = LaneQueue("test")
        result = lane.wait_for_idle(timeout=0.1)
        assert result is True

        lane.enqueue(lambda: time.sleep(1))
        result = lane.wait_for_idle(timeout=0.05)
        assert result is False

    def test_stats(self):
        lane = LaneQueue("mylane", max_concurrency=2)
        stats = lane.stats()
        assert stats["name"] == "mylane"
        assert stats["max_concurrency"] == 2
        assert stats["queue_depth"] == 0
        assert stats["active"] == 0

    def test_exception_propagates(self):
        lane = LaneQueue("test")

        def bad():
            raise ValueError("test error")

        future = lane.enqueue(bad)
        with pytest.raises(ValueError, match="test error"):
            future.result(timeout=5)


class TestCommandQueue:
    def test_get_or_create_lane(self):
        q = CommandQueue()
        lane1 = q.get_or_create_lane("my lane", max_concurrency=2)
        lane2 = q.get_or_create_lane("my lane")
        assert lane1 is lane2  # Same lane returned
        assert lane2.max_concurrency == 2

    def test_enqueue_routes_to_lane(self):
        q = CommandQueue()
        q.get_or_create_lane(LANE_MAIN, max_concurrency=1)
        results = []

        def capture(v):
            return lambda: results.append(v)

        f1 = q.enqueue(LANE_MAIN, capture(1))
        f2 = q.enqueue(LANE_CRON, capture(2))
        f1.result(timeout=5)
        f2.result(timeout=5)
        assert 1 in results
        assert 2 in results

    def test_reset_all_increments_generation(self):
        q = CommandQueue()
        q.get_or_create_lane(LANE_MAIN)
        q.get_or_create_lane(LANE_CRON)
        result = q.reset_all()
        assert LANE_MAIN in result
        assert LANE_CRON in result
        assert result[LANE_MAIN] >= 1
        assert result[LANE_CRON] >= 1

    def test_wait_for_all(self):
        q = CommandQueue()
        q.get_or_create_lane(LANE_MAIN)
        q.get_or_create_lane(LANE_CRON)
        q.enqueue(LANE_MAIN, lambda: time.sleep(0.1))
        q.enqueue(LANE_CRON, lambda: time.sleep(0.1))
        result = q.wait_for_all(timeout=5)
        assert result is True

    def test_stats_all_lanes(self):
        q = CommandQueue()
        q.get_or_create_lane(LANE_MAIN)
        q.get_or_create_lane(LANE_CRON)
        stats = q.stats()
        assert LANE_MAIN in stats
        assert LANE_CRON in stats

    def test_lane_names(self):
        q = CommandQueue()
        q.get_or_create_lane("alpha")
        q.get_or_create_lane("beta")
        names = q.lane_names()
        assert "alpha" in names
        assert "beta" in names
