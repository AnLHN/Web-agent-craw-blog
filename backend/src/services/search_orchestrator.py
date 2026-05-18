import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from src.config.settings import Settings
from src.models.schemas import ProviderAttempt, QueryAnalysisInfo, SearchResultData, SourceItem
from src.services.evidence_merge_service import EvidenceMergeService
from src.services.llm_summary_service import LlmSummaryService
from src.services.query_analyst_service import QueryAnalystService
from src.services.query_planner_service import QueryPlannerService
from src.services.query_cache import QueryCache
from src.services.searxng_service import SearxngSearchService
from src.services.tavily_service import TavilySearchService
from src.utils.text import build_summary, compute_confidence, is_quality_enough

SearchEventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


class SearchOrchestrator:
    def __init__(
        self,
        settings: Settings,
        query_analyst_service: QueryAnalystService,
        query_planner_service: QueryPlannerService,
        evidence_merge_service: EvidenceMergeService,
        tavily_service: TavilySearchService,
        searxng_service: SearxngSearchService,
        llm_summary_service: LlmSummaryService,
        query_cache: QueryCache,
    ):
        self.settings = settings
        self.query_analyst_service = query_analyst_service
        self.query_planner_service = query_planner_service
        self.evidence_merge_service = evidence_merge_service
        self.tavily_service = tavily_service
        self.searxng_service = searxng_service
        self.llm_summary_service = llm_summary_service
        self.query_cache = query_cache

    def _cache_scope(self) -> str:
        runtime = self.llm_summary_service.runtime_store.get()
        scope_payload = "|".join(
            [
                str(runtime.get("base_url") or ""),
                str(runtime.get("model") or ""),
                str(runtime.get("temperature") or ""),
                str(runtime.get("max_tokens") or ""),
                str(runtime.get("summary_max_tokens") or ""),
                str(runtime.get("summary_system_prompt") or ""),
            ]
        )
        digest = hashlib.sha256(scope_payload.encode("utf-8")).hexdigest()[:16]
        return f"prompt:{digest}"

    async def _resolve_summary(
        self,
        query: str,
        sources,
        attempts: list[ProviderAttempt],
    ) -> str:
        llm_result = await self.llm_summary_service.summarize(query=query, sources=sources)
        attempts.append(ProviderAttempt(**llm_result.attempt.__dict__))
        if llm_result.summary:
            return llm_result.summary
        return build_summary(query=query, sources=sources)

    async def _run_single_query(
        self,
        query: str,
        top_k: int,
        trace_sub_query: str | None = None,
        force_searxng: bool = False,
    ) -> SearchResultData:
        attempts: list[ProviderAttempt] = []

        tavily_result = await self.tavily_service.search(query=query, top_k=top_k)
        for attempt in tavily_result.attempts:
            attempt_data = {**attempt.__dict__, "sub_query": trace_sub_query}
            attempts.append(ProviderAttempt(**attempt_data))

        if is_quality_enough(
            tavily_result.sources,
            min_results=self.settings.quality_min_results,
            min_domains=self.settings.quality_min_unique_domains,
        ):
            return SearchResultData(
                query=query,
                provider_used="tavily",
                summary="",
                confidence=compute_confidence(tavily_result.sources),
                sources=tavily_result.sources,
                attempts=attempts,
            )

        searxng_result = await self.searxng_service.search(
            query=query,
            top_k=top_k,
            ignore_circuit=force_searxng,
        )
        for attempt in searxng_result.attempts:
            attempt_data = {**attempt.__dict__, "sub_query": trace_sub_query}
            attempts.append(ProviderAttempt(**attempt_data))

        if not searxng_result.sources and tavily_result.sources:
            return SearchResultData(
                query=query,
                provider_used="tavily_low_quality",
                summary="",
                confidence=compute_confidence(tavily_result.sources),
                sources=tavily_result.sources,
                attempts=attempts,
            )

        if not searxng_result.sources:
            return SearchResultData(
                query=query,
                provider_used="none",
                summary="",
                confidence=0.0,
                sources=[],
                attempts=attempts,
            )

        return SearchResultData(
            query=query,
            provider_used="searxng_fallback",
            summary="",
            confidence=compute_confidence(searxng_result.sources),
            sources=searxng_result.sources,
            attempts=attempts,
        )

    async def _run_multi_query(
        self,
        queries: list[str],
        top_k: int,
        force_searxng: bool = False,
    ) -> tuple[list[SearchResultData], list[ProviderAttempt], int]:
        semaphore = asyncio.Semaphore(max(1, self.settings.max_parallel_subquery))
        attempts: list[ProviderAttempt] = []
        cache_hits = 0

        cache_scope = self._cache_scope()

        async def worker(sub_query: str) -> tuple[SearchResultData, bool]:
            cached_sub = self.query_cache.get_subquery(query=sub_query, top_k=top_k, scope=cache_scope)
            if cached_sub is not None:
                cached_sub.attempts.insert(
                    0,
                    ProviderAttempt(
                        provider="subquery_cache",
                        status="success",
                        reason="cache_hit",
                        latency_ms=0,
                        result_count=len(cached_sub.sources),
                        sub_query=sub_query,
                    ),
                )
                return cached_sub, True
            async with semaphore:
                result = await asyncio.wait_for(
                    self._run_single_query(
                        query=sub_query,
                        top_k=top_k,
                        trace_sub_query=sub_query,
                        force_searxng=force_searxng,
                    ),
                    timeout=max(
                        0.5,
                        self.settings.subquery_timeout_seconds,
                        self.settings.request_timeout_seconds + 1.0,
                    ),
                )
                self.query_cache.set_subquery(query=sub_query, top_k=top_k, payload=result, scope=cache_scope)
                return result, False

        tasks = [asyncio.create_task(worker(q)) for q in queries]
        results: list[SearchResultData] = []
        for task in tasks:
            try:
                item, is_cache_hit = await task
                if is_cache_hit:
                    cache_hits += 1
                results.append(item)
                attempts.extend(item.attempts)
            except asyncio.TimeoutError:
                attempts.append(
                    ProviderAttempt(
                        provider="multi_query",
                        status="failed",
                        reason="subquery_timeout",
                        latency_ms=int(self.settings.subquery_timeout_seconds * 1000),
                        result_count=0,
                    )
                )
        return results, attempts, cache_hits

    async def search(self, query: str, top_k: int) -> SearchResultData:
        return await self.search_with_events(query=query, top_k=top_k, emit=None)

    async def search_with_events(
        self,
        query: str,
        top_k: int,
        emit: SearchEventEmitter | None = None,
    ) -> SearchResultData:
        async def send(status: str, **payload: Any) -> None:
            if emit is not None:
                await emit("status", {"status": status, **payload})

        cache_scope = self._cache_scope()
        cached = self.query_cache.get(query=query, top_k=top_k, scope=cache_scope)
        if cached:
            await send("cache_hit", source_count=len(cached.sources))
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
        analysis = None
        plan = None
        run_queries = [query]
        fallback_queries: list[str] = []
        force_searxng = False

        if self.settings.pipeline_mode != "classic":
            await send("query_analysis_started")
            analysis = await self.query_analyst_service.analyze(query=query)
            if analysis.attempt:
                attempts.append(ProviderAttempt(**analysis.attempt.__dict__))
            await send(
                "query_analysis_done",
                subquery_count=len(analysis.sub_queries),
                intent=analysis.intent,
            )
            await send("query_planning_started")
            plan = await self.query_planner_service.plan(analysis.sub_queries)
            if plan.attempt:
                attempts.append(ProviderAttempt(**plan.attempt.__dict__))
            await send(
                "query_planning_done",
                planned_subquery_count=len(plan.planned_sub_queries),
                complexity=plan.complexity,
                retrieval_budget=plan.retrieval_budget,
            )
            run_queries = plan.planned_sub_queries or [analysis.normalized_query or query]
            fallback_queries = [
                item for item in analysis.sub_queries if item not in run_queries
            ]
            if self.tavily_service.key_store.has_keys():
                run_queries = run_queries[:1]
            else:
                force_searxng = self.settings.force_searxng_test_mode
        total_subquery_count = len(run_queries)

        await send("retrieval_started", subquery_count=len(run_queries))
        multi_results, multi_attempts, cache_hits = await self._run_multi_query(
            queries=run_queries,
            top_k=top_k,
            force_searxng=force_searxng,
        )
        attempts.extend(multi_attempts)
        await send(
            "retrieval_done",
            source_count=sum(len(item.sources) for item in multi_results),
            cache_hits=cache_hits,
        )

        await send("evidence_merge_started")
        merge_result = self.evidence_merge_service.merge(
            all_sources=[src for item in multi_results for src in item.sources],
            top_k=max(top_k, self.settings.quality_min_results),
        )
        if merge_result.attempt:
            attempts.append(ProviderAttempt(**merge_result.attempt.__dict__))
        merged_sources = merge_result.kept_sources
        await send(
            "evidence_merge_done",
            kept_count=len(merged_sources),
            dropped_count=merge_result.dropped_count,
        )

        if not merged_sources:
            await send("fallback_single_query_started")
            attempts.append(
                ProviderAttempt(
                    provider="fallback_single_query",
                    status="retry",
                    reason="recover_from_empty_multi_query",
                    latency_ms=0,
                    result_count=0,
                )
            )
            fallback_result = await self._run_single_query(
                query=query,
                top_k=top_k,
                force_searxng=force_searxng,
            )
            attempts.extend(fallback_result.attempts)
            merge_result = self.evidence_merge_service.merge(
                all_sources=fallback_result.sources,
                top_k=max(top_k, self.settings.quality_min_results),
            )
            if merge_result.attempt:
                attempts.append(ProviderAttempt(**merge_result.attempt.__dict__))
            merged_sources = merge_result.kept_sources
            await send("fallback_single_query_done", source_count=len(merged_sources))

        need_extra_round = (
            self.settings.pipeline_mode != "classic"
            and self.settings.quality_gate_max_extra_rounds > 0
            and len(merged_sources) < max(1, self.settings.quality_gate_min_coverage_sources)
            and len(fallback_queries) > 0
        )

        if need_extra_round:
            await send("quality_gate_extra_round_started", current_source_count=len(merged_sources))
            attempts.append(
                ProviderAttempt(
                    provider="quality_gate",
                    status="retry",
                    reason="coverage_low_trigger_extra_round",
                    latency_ms=0,
                    result_count=len(merged_sources),
                )
            )
            extra_queries = fallback_queries[: max(1, self.settings.planner_simple_budget)]
            total_subquery_count += len(extra_queries)
            extra_results, extra_attempts, extra_cache_hits = await self._run_multi_query(
                queries=extra_queries,
                top_k=top_k,
                force_searxng=force_searxng,
            )
            cache_hits += extra_cache_hits
            attempts.extend(extra_attempts)
            multi_results.extend(extra_results)

            merge_result = self.evidence_merge_service.merge(
                all_sources=[src for item in multi_results for src in item.sources],
                top_k=max(top_k, self.settings.quality_min_results),
            )
            if merge_result.attempt:
                attempts.append(ProviderAttempt(**merge_result.attempt.__dict__))
            merged_sources = merge_result.kept_sources
            await send("quality_gate_extra_round_done", source_count=len(merged_sources))
        else:
            attempts.append(
                ProviderAttempt(
                    provider="quality_gate",
                    status="passed",
                    reason="coverage_ok_or_no_extra_round",
                    latency_ms=0,
                    result_count=len(merged_sources),
                )
            )
            await send("quality_gate_passed", source_count=len(merged_sources))

        if merged_sources:
            providers = [item.provider_used for item in multi_results]
            if providers and all(p in {"tavily", "tavily_low_quality"} for p in providers):
                final_provider = "tavily"
            elif any(p == "searxng_fallback" for p in providers):
                final_provider = "searxng_fallback"
            elif all(p == "none" for p in providers):
                final_provider = "none"
            else:
                final_provider = "multi_query_tavily_first"
            await send("llm_summary_started", source_count=len(merged_sources))
            summary = await self._resolve_summary(
                query=query,
                sources=merged_sources,
                attempts=attempts,
            )
            await send("llm_summary_done", summary_length=len(summary))
            data = SearchResultData(
                query=query,
                provider_used=final_provider,
                summary=summary,
                confidence=compute_confidence(merged_sources),
                sources=merged_sources,
                attempts=attempts,
            )
        else:
            data = SearchResultData(
                query=query,
                provider_used="none",
                summary="Khong tim thay ket qua phu hop tu Tavily hoac SearXNG.",
                confidence=0.0,
                sources=[],
                attempts=attempts,
            )
            await send("no_sources_found")

        if analysis is not None and plan is not None:
            data.query_analysis = QueryAnalysisInfo(
                original_query=analysis.original_query,
                normalized_query=analysis.normalized_query,
                intent=analysis.intent,
                expanded_sub_queries=analysis.sub_queries,
                planned_sub_queries=plan.planned_sub_queries,
                complexity=plan.complexity,
                retrieval_budget=plan.retrieval_budget,
                evidence_kept_count=len(merged_sources),
                evidence_dropped_count=merge_result.dropped_count,
                evidence_dropped_reason_summary=merge_result.dropped_reason_summary,
                query_expansion_count=len(analysis.sub_queries),
                subquery_cache_hit_rate=(
                    float(cache_hits) / float(max(total_subquery_count, 1))
                ),
                retrieval_coverage=(
                    float(len(merged_sources)) / float(max(plan.retrieval_budget, 1))
                ),
                analysis_reasoning_short=analysis.analysis_reasoning_short,
            )

        self.query_cache.set(query=query, top_k=top_k, payload=data, scope=cache_scope)
        return data
