"""
h_agent/concurrency/lanes.py - Named lane concurrency system.

Replaces raw threading.Lock with a named lane system where each lane is
an independent FIFO queue with configurable max concurrency.

Key concepts:
- LaneQueue: a named FIFO queue with max_concurrency control
- CommandQueue: central dispatcher routing work to named lanes
- Generation tracking: stale tasks from old generations are ignored after reset

Usage:
    from h_agent.concurrency import CommandQueue, LANE_MAIN, LANE_CRON, LANE_HEARTBEAT

    q = CommandQueue()
    q.get_or_create_lane(LANE_MAIN, max_concurrency=1)

    future = q.enqueue(LANE_MAIN, lambda: do_work())
    result = future.result(timeout=30)
"""

import threading
import time
import concurrent.futures
from collections import deque
from typing import Any, Callable, Dict, List, Optional

# Standard lane names
LANE_MAIN = "main"
LANE_CRON = "cron"
LANE_HEARTBEAT = "heartbeat"


class LaneQueue:
    """A named FIFO queue with max_concurrency control.

    Each enqueued callable runs in its own thread. Results are delivered
    via concurrent.futures.Future. Generation tracking ensures that tasks
    from an old generation (before a reset) won't repump the queue when
    they complete.
    """

    def __init__(self, name: str, max_concurrency: int = 1) -> None:
        self.name = name
        self.max_concurrency = max(1, max_concurrency)
        self._deque: deque = deque()
        self._condition = threading.Condition()
        self._active_count = 0
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    def enqueue(
        self, fn: Callable[[], Any], generation: Optional[int] = None
    ) -> concurrent.futures.Future:
        """Enqueue a callable. Returns a Future with the result."""
        future: concurrent.futures.Future = concurrent.futures.Future()
        with self._condition:
            gen = generation if generation is not None else self._generation
            self._deque.append((fn, future, gen))
            self._pump()
        return future

    def _pump(self) -> None:
        """Pop tasks from deque and start threads until active >= max_concurrency.

        Must be called while holding self._condition.
        """
        while self._active_count < self.max_concurrency and self._deque:
            fn, future, gen = self._deque.popleft()
            self._active_count += 1
            t = threading.Thread(
                target=self._run_task,
                args=(fn, future, gen),
                daemon=True,
                name=f"lane-{self.name}",
            )
            t.start()

    def _run_task(
        self,
        fn: Callable[[], Any],
        future: concurrent.futures.Future,
        gen: int,
    ) -> None:
        """Execute fn, set future result/exception, then call _task_done."""
        try:
            result = fn()
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)
        finally:
            self._task_done(gen)

    def _task_done(self, gen: int) -> None:
        """Decrement active count. Repump only if generation matches."""
        with self._condition:
            self._active_count -= 1
            if gen == self._generation:
                self._pump()
            self._condition.notify_all()

    def wait_for_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until active_count == 0 and deque is empty. Returns True on idle."""
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        with self._condition:
            while self._active_count > 0 or len(self._deque) > 0:
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                self._condition.wait(timeout=remaining)
            return True

    def stats(self) -> Dict[str, Any]:
        with self._condition:
            return {
                "name": self.name,
                "queue_depth": len(self._deque),
                "active": self._active_count,
                "max_concurrency": self.max_concurrency,
                "generation": self._generation,
            }


class CommandQueue:
    """Central dispatcher routing callables to named LaneQueues.

    Lanes are created lazily on first use. reset_all() increments all
    generation counters so that stale tasks from the previous lifecycle
    won't repump the queue when they finish.
    """

    def __init__(self) -> None:
        self._lanes: Dict[str, LaneQueue] = {}
        self._lock = threading.Lock()

    def get_or_create_lane(self, name: str, max_concurrency: int = 1) -> LaneQueue:
        """Get an existing lane or create a new one."""
        with self._lock:
            if name not in self._lanes:
                self._lanes[name] = LaneQueue(name, max_concurrency)
            return self._lanes[name]

    def enqueue(self, lane_name: str, fn: Callable[[], Any]) -> concurrent.futures.Future:
        """Route callable to the named lane. Returns a Future."""
        lane = self.get_or_create_lane(lane_name)
        return lane.enqueue(fn)

    def reset_all(self) -> Dict[str, int]:
        """Increment generation on all lanes. Returns lane_name -> new_generation."""
        result: Dict[str, int] = {}
        with self._lock:
            for name, lane in self._lanes.items():
                with lane._condition:
                    lane._generation += 1
                    result[name] = lane._generation
        return result

    def wait_for_all(self, timeout: float = 10.0) -> bool:
        """Wait for all lanes to become idle. Returns True if all idle."""
        deadline = time.monotonic() + timeout
        with self._lock:
            lanes = list(self._lanes.values())
        for lane in lanes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if not lane.wait_for_idle(timeout=remaining):
                return False
        return True

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """Return stats for all lanes."""
        with self._lock:
            return {name: lane.stats() for name, lane in self._lanes.items()}

    def lane_names(self) -> List[str]:
        with self._lock:
            return list(self._lanes.keys())
