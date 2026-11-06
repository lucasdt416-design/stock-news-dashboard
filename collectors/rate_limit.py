"""A shared request budget, so a long watchlist stays inside a free API's limits."""

import threading
import time
from collections import deque
from typing import Callable, Deque


class RateLimiter:
    """At most max_calls in any period of seconds; wait() blocks until the next call is allowed."""

    def __init__(self, max_calls: int, period: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.max_calls, self.period = max_calls, period
        self.clock, self.sleep = clock, sleep
        self.calls: Deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            while True:
                now = self.clock()
                while self.calls and now - self.calls[0] >= self.period:
                    self.calls.popleft()
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return
                self.sleep(self.period - (now - self.calls[0]))


# Finnhub's free plan allows 60 calls a minute across news and the earnings calendar together.
# A little under that leaves room for the site's own live lookups.
FINNHUB_LIMIT = RateLimiter(50, 60.0)
