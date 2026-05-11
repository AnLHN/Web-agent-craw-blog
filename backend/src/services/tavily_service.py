import time

import httpx

from src.config.settings import Settings
from src.models.schemas import SourceItem
from src.services.key_store import TavilyKeyStore
from src.services.types import ProviderAttemptData, ProviderSearchResult
from src.utils.text import extract_domain


class TavilySearchService:
    def __init__(self, settings: Settings, key_store: TavilyKeyStore):
        self.settings = settings
        self.key_store = key_store

    async def search(self, query: str, top_k: int) -> ProviderSearchResult:
        attempts: list[ProviderAttemptData] = []

        if not self.key_store.has_keys():
            attempts.append(
                ProviderAttemptData(
                    provider="tavily",
                    status="skipped",
                    reason="no_keys_configured",
                    latency_ms=0,
                    result_count=0,
                )
            )
            return ProviderSearchResult(provider="tavily", sources=[], attempts=attempts)

        for _ in range(0, 12):
            key_record = self.key_store.get_next_active_key()
            if not key_record:
                attempts.append(
                    ProviderAttemptData(
                        provider="tavily",
                        status="failed",
                        reason="all_keys_unavailable",
                        latency_ms=0,
                        result_count=0,
                    )
                )
                return ProviderSearchResult(provider="tavily", sources=[], attempts=attempts)

            started_at = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    response = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": key_record.api_key,
                            "query": query,
                            "search_depth": self.settings.tavily_search_depth,
                            "max_results": top_k,
                            "include_answer": False,
                        },
                    )

                latency_ms = int((time.perf_counter() - started_at) * 1000)

                if response.status_code == 429:
                    self.key_store.mark_rate_limited(
                        key_id=key_record.id,
                        cooldown_seconds=self.settings.tavily_max_cooldown_seconds,
                    )
                    attempts.append(
                        ProviderAttemptData(
                            provider="tavily",
                            status="failed",
                            reason="rate_limited",
                            latency_ms=latency_ms,
                            result_count=0,
                        )
                    )
                    continue

                if response.status_code in {401, 403}:
                    self.key_store.mark_unhealthy(key_record.id)
                    attempts.append(
                        ProviderAttemptData(
                            provider="tavily",
                            status="failed",
                            reason=f"http_{response.status_code}",
                            latency_ms=latency_ms,
                            result_count=0,
                        )
                    )
                    continue

                if response.status_code >= 400:
                    self.key_store.mark_failure(key_record.id)
                    attempts.append(
                        ProviderAttemptData(
                            provider="tavily",
                            status="failed",
                            reason=f"http_{response.status_code}",
                            latency_ms=latency_ms,
                            result_count=0,
                        )
                    )
                    continue

                payload = response.json()
                raw_results = payload.get("results", [])

                sources = [
                    SourceItem(
                        title=item.get("title", "Untitled"),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        domain=extract_domain(item.get("url", "")),
                        score=float(item.get("score") or 0.0),
                        published_date=item.get("published_date"),
                    )
                    for item in raw_results
                    if item.get("url")
                ]

                self.key_store.mark_success(key_record.id)
                attempts.append(
                    ProviderAttemptData(
                        provider="tavily",
                        status="success",
                        reason="ok",
                        latency_ms=latency_ms,
                        result_count=len(sources),
                    )
                )
                return ProviderSearchResult(provider="tavily", sources=sources, attempts=attempts)
            except httpx.HTTPError:
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                self.key_store.mark_failure(key_record.id)
                attempts.append(
                    ProviderAttemptData(
                        provider="tavily",
                        status="failed",
                        reason="network_error",
                        latency_ms=latency_ms,
                        result_count=0,
                    )
                )

        attempts.append(
            ProviderAttemptData(
                provider="tavily",
                status="failed",
                reason="retry_budget_exhausted",
                latency_ms=0,
                result_count=0,
            )
        )
        return ProviderSearchResult(provider="tavily", sources=[], attempts=attempts)
