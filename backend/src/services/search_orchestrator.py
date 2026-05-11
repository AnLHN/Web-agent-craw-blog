from src.config.settings import Settings
from src.models.schemas import ProviderAttempt, SearchResultData
from src.services.query_cache import QueryCache
from src.services.searxng_service import SearxngSearchService
from src.services.tavily_service import TavilySearchService
from src.utils.text import build_summary, compute_confidence, is_quality_enough


class SearchOrchestrator:
    def __init__(
        self,
        settings: Settings,
        tavily_service: TavilySearchService,
        searxng_service: SearxngSearchService,
        query_cache: QueryCache,
    ):
        self.settings = settings
        self.tavily_service = tavily_service
        self.searxng_service = searxng_service
        self.query_cache = query_cache

    async def search(self, query: str, top_k: int) -> SearchResultData:
        cached = self.query_cache.get(query=query, top_k=top_k)
        if cached:
            cached.attempts.insert(
                0,
                ProviderAttempt(
                    provider="cache",
                    status="success",
                    reason="cache_hit",
                    latency_ms=0,
                    result_count=len(cached.sources),
                ),
            )
            return cached

        attempts: list[ProviderAttempt] = []

        tavily_result = await self.tavily_service.search(query=query, top_k=top_k)
        attempts.extend(
            ProviderAttempt(**attempt.__dict__) for attempt in tavily_result.attempts
        )

        if is_quality_enough(
            tavily_result.sources,
            min_results=self.settings.quality_min_results,
            min_domains=self.settings.quality_min_unique_domains,
        ):
            summary = build_summary(query=query, sources=tavily_result.sources)
            data = SearchResultData(
                query=query,
                provider_used="tavily",
                summary=summary,
                confidence=compute_confidence(tavily_result.sources),
                sources=tavily_result.sources,
                attempts=attempts,
            )
            self.query_cache.set(query=query, top_k=top_k, payload=data)
            return data

        searxng_result = await self.searxng_service.search(query=query, top_k=top_k)
        attempts.extend(
            ProviderAttempt(**attempt.__dict__) for attempt in searxng_result.attempts
        )

        if not searxng_result.sources and tavily_result.sources:
            summary = build_summary(query=query, sources=tavily_result.sources)
            data = SearchResultData(
                query=query,
                provider_used="tavily_low_quality",
                summary=summary,
                confidence=compute_confidence(tavily_result.sources),
                sources=tavily_result.sources,
                attempts=attempts,
            )
            self.query_cache.set(query=query, top_k=top_k, payload=data)
            return data

        if not searxng_result.sources:
            data = SearchResultData(
                query=query,
                provider_used="none",
                summary="Khong tim thay ket qua phu hop tu Tavily hoac SearXNG.",
                confidence=0.0,
                sources=[],
                attempts=attempts,
            )
            self.query_cache.set(query=query, top_k=top_k, payload=data)
            return data

        summary = build_summary(query=query, sources=searxng_result.sources)
        data = SearchResultData(
            query=query,
            provider_used="searxng_fallback",
            summary=summary,
            confidence=compute_confidence(searxng_result.sources),
            sources=searxng_result.sources,
            attempts=attempts,
        )
        self.query_cache.set(query=query, top_k=top_k, payload=data)
        return data
