import json
import re
import time

import httpx

from src.config.settings import Settings
from src.services.types import ProviderAttemptData, QueryAnalysisResult


class QueryAnalystService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _normalize_query(self, query: str) -> str:
        compact = re.sub(r"\s+", " ", query.strip())
        return compact

    def _detect_intent(self, query_lower: str) -> str:
        if any(token in query_lower for token in ["la gi", "là gì", "what is", "khái niệm"]):
            return "definition"
        if any(token in query_lower for token in ["kien truc", "kiến trúc", "architecture"]):
            return "architecture"
        if any(token in query_lower for token in ["so sanh", "compare", "khac nhau"]):
            return "comparison"
        return "general_exploration"

    def _expand_sub_queries(self, normalized_query: str, intent: str) -> list[str]:
        q = normalized_query
        ql = q.lower()
        candidates = [q]

        if "rag" in ql:
            candidates.extend(
                [
                    "RAG architecture overview",
                    "RAG in machine learning",
                    "RAG components retriever generator vector database",
                    "RAG workflow indexing retrieval generation",
                ]
            )
        else:
            candidates.extend(
                [
                    f"{q} overview",
                    f"{q} in machine learning",
                    f"{q} use cases and limitations",
                ]
            )

        if intent == "definition":
            candidates.append(f"definition of {q}")
        elif intent == "architecture":
            candidates.append(f"{q} components and architecture")
        elif intent == "comparison":
            candidates.append(f"{q} comparison")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(item.strip())

        return deduped[: max(1, self.settings.max_sub_queries)]

    @staticmethod
    def _clean_llm_json(raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text

    @staticmethod
    def _dedupe_sub_queries(candidates: list[str], max_items: int) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            value = re.sub(r"\s+", " ", (item or "").strip())
            key = value.lower()
            if not value or key in seen:
                continue
            seen.add(key)
            deduped.append(value)
            if len(deduped) >= max_items:
                break
        return deduped

    async def _analyze_with_llm(self, normalized_query: str, fallback_intent: str) -> tuple[str, list[str], str]:
        base_url = self.settings.llm_base_url.rstrip("/")
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ban la Query Analyst Agent. Nhiem vu: phan tich query web search va de xuat sub-query "
                        "de truy hoi thong tin chinh xac. Tra ve DUY NHAT JSON hop le, khong markdown, khong giai thich them."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Hay phan tich query sau va tra JSON co schema: "
                        "{\"intent\": string, \"sub_queries\": string[], \"analysis_reasoning_short\": string}. "
                        f"So luong sub_queries tu 1 den {max(1, self.settings.max_sub_queries)}. "
                        "Sub-queries phai bam sat query, khong chen chu de khong lien quan. "
                        "Uu tien thong tin doanh nghiep/nhan su neu query ve cong ty. "
                        f"Fallback intent neu khong chac: {fallback_intent}.\n"
                        f"Query: {normalized_query}"
                    ),
                },
            ],
            "temperature": min(max(self.settings.llm_temperature, 0.0), 0.5),
            "max_tokens": 400,
        }

        timeout = max(self.settings.request_timeout_seconds, 20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload)
        if response.status_code >= 400:
            raise ValueError(f"llm_http_{response.status_code}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("llm_empty_choices")

        message = (choices[0] or {}).get("message") or {}
        raw_content = message.get("content")
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if isinstance(item, dict):
                    text_part = item.get("text")
                    if isinstance(text_part, str) and text_part.strip():
                        parts.append(text_part.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            content = "\n".join(parts).strip()
        else:
            content = str(raw_content or "").strip()
        if not content:
            raise ValueError("llm_empty_content")

        cleaned_json = self._clean_llm_json(content)
        parsed = json.loads(cleaned_json)
        intent = str(parsed.get("intent") or fallback_intent).strip().lower()
        if not intent:
            intent = fallback_intent
        raw_sub_queries = parsed.get("sub_queries") or []
        if not isinstance(raw_sub_queries, list):
            raw_sub_queries = []
        sub_queries = self._dedupe_sub_queries(
            [str(item) for item in raw_sub_queries],
            max_items=max(1, self.settings.max_sub_queries),
        )
        if not sub_queries:
            raise ValueError("llm_no_sub_queries")

        reasoning = str(parsed.get("analysis_reasoning_short") or "").strip()
        if not reasoning:
            reasoning = "LLM generated sub-queries based on query intent and entity focus."
        return intent, sub_queries, reasoning

    async def analyze(self, query: str) -> QueryAnalysisResult:
        started_at = time.perf_counter()
        normalized_query = self._normalize_query(query)
        fallback_intent = self._detect_intent(normalized_query.lower())

        mode = (self.settings.query_analyst_mode or "rule").strip().lower()
        use_llm = mode in {"llm", "hybrid", "agent"} and self.settings.llm_enabled

        provider_reason = "expanded_rule"
        analysis_reasoning_short = "Expanded query into focused sub-queries for retrieval coverage."
        intent = fallback_intent
        sub_queries = self._expand_sub_queries(normalized_query, intent)

        if use_llm:
            try:
                intent, sub_queries, analysis_reasoning_short = await self._analyze_with_llm(
                    normalized_query=normalized_query,
                    fallback_intent=fallback_intent,
                )
                provider_reason = "expanded_llm"
            except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                provider_reason = "expanded_rule_fallback"

        latency_ms = int((time.perf_counter() - started_at) * 1000)

        return QueryAnalysisResult(
            original_query=query,
            normalized_query=normalized_query,
            intent=intent,
            sub_queries=sub_queries,
            analysis_reasoning_short=analysis_reasoning_short,
            attempt=ProviderAttemptData(
                provider="query_analyst",
                status="success",
                reason=provider_reason,
                latency_ms=latency_ms,
                result_count=len(sub_queries),
            ),
        )
