import time

import httpx

from src.config.settings import Settings
from src.models.schemas import SourceItem
from src.services.types import ProviderAttemptData, SummaryResult


class LlmSummaryService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _build_user_prompt(query: str, sources: list[SourceItem]) -> str:
        lines = []
        for index, source in enumerate(sources[:5], start=1):
            snippet = source.snippet.strip().replace("\n", " ")
            lines.append(
                f"{index}. title={source.title}; domain={source.domain}; snippet={snippet}; url={source.url}"
            )

        joined_sources = "\n".join(lines)
        return (
            "Tom tat ket qua web search bang tieng Viet, ngan gon va de doc. "
            "Khong du doan vuot qua du lieu nguon.\n"
            f"Query: {query}\n"
            f"Sources:\n{joined_sources}"
        )

    async def summarize(self, query: str, sources: list[SourceItem]) -> SummaryResult:
        if not self.settings.llm_enabled:
            return SummaryResult(
                summary="",
                attempt=ProviderAttemptData(
                    provider="llm",
                    status="skipped",
                    reason="disabled",
                    latency_ms=0,
                    result_count=0,
                ),
            )

        if not sources:
            return SummaryResult(
                summary="",
                attempt=ProviderAttemptData(
                    provider="llm",
                    status="skipped",
                    reason="no_sources",
                    latency_ms=0,
                    result_count=0,
                ),
            )

        base_url = self.settings.llm_base_url.rstrip("/")
        started_at = time.perf_counter()

        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ban la tro ly tom tat ket qua tim kiem web chinh xac va ngan gon.",
                },
                {
                    "role": "user",
                    "content": self._build_user_prompt(query=query, sources=sources),
                },
            ],
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                )

            latency_ms = int((time.perf_counter() - started_at) * 1000)

            if response.status_code >= 400:
                return SummaryResult(
                    summary="",
                    attempt=ProviderAttemptData(
                        provider="llm",
                        status="failed",
                        reason=f"http_{response.status_code}",
                        latency_ms=latency_ms,
                        result_count=0,
                    ),
                )

            data = response.json()
            choices = data.get("choices") or []
            content = ""
            if choices:
                message = choices[0].get("message") or {}
                content = str(message.get("content") or "").strip()

            if not content:
                return SummaryResult(
                    summary="",
                    attempt=ProviderAttemptData(
                        provider="llm",
                        status="failed",
                        reason="empty_response",
                        latency_ms=latency_ms,
                        result_count=0,
                    ),
                )

            return SummaryResult(
                summary=content,
                attempt=ProviderAttemptData(
                    provider="llm",
                    status="success",
                    reason="ok",
                    latency_ms=latency_ms,
                    result_count=len(sources),
                ),
            )
        except (httpx.HTTPError, ValueError):
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return SummaryResult(
                summary="",
                attempt=ProviderAttemptData(
                    provider="llm",
                    status="failed",
                    reason="network_error",
                    latency_ms=latency_ms,
                    result_count=0,
                ),
            )
