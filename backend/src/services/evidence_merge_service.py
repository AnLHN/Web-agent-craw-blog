import time

from src.models.schemas import SourceItem
from src.services.types import EvidenceMergeResult, ProviderAttemptData


class EvidenceMergeService:
    def merge(self, all_sources: list[SourceItem], top_k: int) -> EvidenceMergeResult:
        started_at = time.perf_counter()
        by_url: dict[str, SourceItem] = {}
        by_domain_count: dict[str, int] = {}
        dropped = 0

        for src in all_sources:
            if not src.url:
                dropped += 1
                continue
            prev = by_url.get(src.url)
            if prev is None or src.score > prev.score:
                by_url[src.url] = src
            else:
                dropped += 1

        ranked = sorted(by_url.values(), key=lambda item: item.score, reverse=True)

        kept: list[SourceItem] = []
        for src in ranked:
            domain_seen = by_domain_count.get(src.domain, 0)
            if domain_seen >= 2 and len(ranked) > top_k:
                dropped += 1
                continue
            kept.append(src)
            by_domain_count[src.domain] = domain_seen + 1
            if len(kept) >= top_k:
                break

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return EvidenceMergeResult(
            kept_sources=kept,
            dropped_count=dropped,
            dropped_reason_summary="deduplicated_by_url_and_limited_domain_repetition",
            attempt=ProviderAttemptData(
                provider="evidence_merge",
                status="success",
                reason="merged",
                latency_ms=latency_ms,
                result_count=len(kept),
            ),
        )
