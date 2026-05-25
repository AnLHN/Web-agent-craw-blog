from collections import defaultdict, deque
from time import monotonic


class InMemoryRateLimiter:
    def __init__(self, window_seconds: int, max_attempts: int):
        self.window_seconds = max(1, window_seconds)
        self.max_attempts = max(1, max_attempts)
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        attempts = self._attempts[key]
        cutoff = now - self.window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            return False
        attempts.append(now)
        return True
