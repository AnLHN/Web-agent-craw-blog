import time
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx

from src.config.settings import Settings
from src.models.schemas import SourceItem
from src.services.types import ProviderAttemptData, ProviderSearchResult
from src.utils.text import extract_domain


class SearxngSearchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._request_times: deque[float] = deque()
        self._consecutive_failures = 0
        self._circuit_open_until: datetime | None = None

    async def _throttle(self) -> None:
        if self.settings.searxng_max_qps <= 0:
            return

        min_interval = 1.0 / self.settings.searxng_max_qps
        async with self._lock:
            now = time.monotonic()
            while self._request_times and now - self._request_times[0] > 1.0:
                self._request_times.popleft()

            if self._request_times:
                elapsed = now - self._request_times[-1]
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._request_times.append(time.monotonic())

    def _is_circuit_open(self) -> bool:
        if not self._circuit_open_until:
            return False
        return datetime.now(timezone.utc) < self._circuit_open_until

    def _mark_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.settings.searxng_circuit_fail_threshold:
            self._circuit_open_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.settings.searxng_circuit_open_seconds
            )

    def _mark_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = None

    def _candidate_base_urls(self) -> list[str]:
        urls = [self.settings.searxng_base_url.strip()]
        backups = [
            item.strip()
            for item in self.settings.searxng_backup_base_urls.split(",")
            if item.strip()
        ]
        for backup in backups:
            if backup not in urls:
                urls.append(backup)
        return urls

    async def search(self, query: str, top_k: int) -> ProviderSearchResult:
        if self._is_circuit_open():
            return ProviderSearchResult(
                provider="searxng",
                sources=[],
                attempts=[
                    ProviderAttemptData(
                        provider="searxng",
                        status="failed",
                        reason="circuit_open",
                        latency_ms=0,
                        result_count=0,
                    )
                ],
            )

        attempts: list[ProviderAttemptData] = []
        for base_url in self._candidate_base_urls():
            await self._throttle()
            started_at = time.perf_counter()

            try:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    response = await client.get(
                        f"{base_url}/search",
                        params={
                            "q": query,
                            "format": "json",
                            "categories": self.settings.searxng_categories,
                        },
                    )

                latency_ms = int((time.perf_counter() - started_at) * 1000)

                if response.status_code >= 400:
                    attempts.append(
                        ProviderAttemptData(
                            provider="searxng",
                            status="failed",
                            reason=f"http_{response.status_code}:{base_url}",
                            latency_ms=latency_ms,
                            result_count=0,
                        )
                    )
                    continue

                payload = response.json()
                raw_results = payload.get("results", [])[:top_k]
                sources = [
                    SourceItem(
                        title=item.get("title", "Untitled"),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        domain=extract_domain(item.get("url", "")),
                        score=0.5,
                        published_date=item.get("publishedDate"),
                    )
                    for item in raw_results
                    if item.get("url")
                ]

                attempts.append(
                    ProviderAttemptData(
                        provider="searxng",
                        status="success",
                        reason=f"ok:{base_url}",
                        latency_ms=latency_ms,
                        result_count=len(sources),
                    )
                )

                if sources:
                    self._mark_success()
                    return ProviderSearchResult(
                        provider="searxng",
                        sources=sources,
                        attempts=attempts,
                    )
            except httpx.HTTPError:
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                attempts.append(
                    ProviderAttemptData(
                        provider="searxng",
                        status="failed",
                        reason=f"network_error:{base_url}",
                        latency_ms=latency_ms,
                        result_count=0,
                    )
                )

        self._mark_failure()
        if not attempts:
            attempts = [
                ProviderAttemptData(
                    provider="searxng",
                    status="failed",
                    reason="no_instances_configured",
                    latency_ms=0,
                    result_count=0,
                )
            ]

        return ProviderSearchResult(provider="searxng", sources=[], attempts=attempts)
