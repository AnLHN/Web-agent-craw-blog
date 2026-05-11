import threading
import time

from src.models.schemas import SearchResultData


class QueryCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, SearchResultData]] = {}

    def _normalize_key(self, query: str, top_k: int) -> str:
        return f"{query.strip().lower()}::{top_k}"

    def get(self, query: str, top_k: int) -> SearchResultData | None:
        key = self._normalize_key(query, top_k)
        now = time.time()
        with self._lock:
            if key not in self._store:
                return None

            expires_at, payload = self._store[key]
            if expires_at < now:
                del self._store[key]
                return None

            return payload.model_copy(deep=True)

    def set(self, query: str, top_k: int, payload: SearchResultData) -> None:
        key = self._normalize_key(query, top_k)
        expires_at = time.time() + max(self.ttl_seconds, 1)
        with self._lock:
            self._store[key] = (expires_at, payload.model_copy(deep=True))
