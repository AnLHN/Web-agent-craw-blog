import asyncio
import json
import re
import time
from typing import Any

import httpx

from src.config.settings import Settings
from src.models.article_schemas import ArticleBlockType
from src.services.article_llm_provider import ArticleTranslationRequest, ArticleTranslationResult


class NineRouterOpenAIArticleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.ninerouter_base_url.strip())

    async def check_health(self) -> dict[str, Any]:
        base_url = self.settings.ninerouter_base_url.rstrip("/")
        if not base_url:
            return {
                "ok": False,
                "configured": False,
                "status": "not_configured",
                "message": "9router base URL is not configured.",
                "latency_ms": 0,
                "base_url": "",
                "model": self.settings.article_openai_model,
                "has_api_key": bool(self.settings.ninerouter_api_key),
            }

        payload = {
            "model": self.settings.article_openai_model,
            "messages": [
                {"role": "system", "content": "Reply with only: ok"},
                {"role": "user", "content": "health check"},
            ],
            "temperature": 0,
            "max_tokens": 8,
            "stream": False,
        }
        headers: dict[str, str] = {}
        if self.settings.ninerouter_api_key:
            headers["Authorization"] = f"Bearer {self.settings.ninerouter_api_key}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=min(max(self.settings.request_timeout_seconds, 10.0), 30.0)) as client:
                response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                return {
                    "ok": False,
                    "configured": True,
                    "status": f"http_{response.status_code}",
                    "message": response.text[:240] or f"9router returned HTTP {response.status_code}.",
                    "latency_ms": latency_ms,
                    "base_url": base_url,
                    "model": self.settings.article_openai_model,
                    "has_api_key": bool(self.settings.ninerouter_api_key),
                }
            data = response.json()
            choices = data.get("choices") or []
            return {
                "ok": bool(choices),
                "configured": True,
                "status": "ready" if choices else "empty_response",
                "message": "9router/OpenAI responded." if choices else "9router returned no choices.",
                "latency_ms": latency_ms,
                "base_url": base_url,
                "model": self.settings.article_openai_model,
                "has_api_key": bool(self.settings.ninerouter_api_key),
            }
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": False,
                "configured": True,
                "status": "request_failed",
                "message": str(exc),
                "latency_ms": latency_ms,
                "base_url": base_url,
                "model": self.settings.article_openai_model,
                "has_api_key": bool(self.settings.ninerouter_api_key),
            }

    async def translate_blocks(self, request: ArticleTranslationRequest) -> ArticleTranslationResult:
        base_url = self.settings.ninerouter_base_url.rstrip("/")
        if not base_url:
            raise ValueError("ninerouter_base_url_not_configured")

        payload = {
            "model": self.settings.article_openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        request.system_prompt
                        + "\n\nReturn only valid JSON. Do not wrap JSON in markdown. "
                        "For code blocks, copy source_text exactly into text_vi. "
                        "Do not split inline code, API names, symbols, or technical identifiers into separate blocks. "
                        "Preserve them inline inside the translated sentence. "
                        "Keep link placeholders in the format [LINK_n:label]. Do not change LINK_n, but translate label when natural."
                    ),
                },
                {"role": "user", "content": json.dumps(self._request_payload(request), ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "max_tokens": self.settings.article_translation_max_output_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers: dict[str, str] = {}
        if self.settings.ninerouter_api_key:
            headers["Authorization"] = f"Bearer {self.settings.ninerouter_api_key}"

        response: httpx.Response | None = None
        retry_statuses = {429, 500, 502, 503, 504}
        retry_delays = (5, 15, 30)
        async with httpx.AsyncClient(timeout=max(self.settings.request_timeout_seconds, 180.0)) as client:
            for attempt in range(len(retry_delays) + 1):
                try:
                    response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt == len(retry_delays):
                        raise ValueError(f"ninerouter_request_failed:{exc}") from exc
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                if response.status_code not in retry_statuses or attempt == len(retry_delays):
                    break
                await asyncio.sleep(retry_delays[attempt])
        if response is None:
            raise ValueError("ninerouter_request_failed:no_response")
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise ValueError(f"ninerouter_http_{response.status_code}:{detail}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("ninerouter_empty_choices")
        choice = choices[0] or {}
        message = (choices[0] or {}).get("message") or {}
        content = self._extract_content(message.get("content"))
        if not content:
            raise ValueError("ninerouter_empty_content")
        try:
            parsed = json.loads(self._clean_json(content))
        except json.JSONDecodeError as exc:
            finish_reason = choice.get("finish_reason") or "unknown"
            raise ValueError(f"translation_json_invalid:finish_reason={finish_reason}:error={exc}") from exc
        return ArticleTranslationResult(
            payload=parsed,
            provider="9router_openai",
            model=self.settings.article_openai_model,
        )

    @staticmethod
    def _request_payload(request: ArticleTranslationRequest) -> dict[str, Any]:
        return {
            "target_language": request.target_language,
            "source": request.source.model_dump(mode="json"),
            "glossary": request.glossary,
            "required_schema": {
                "title_vi": "string",
                "excerpt_vi": "string",
                "slug": "string",
                "tags": ["string"],
                "categories": ["string"],
                "translated_blocks": [
                    {"block_id": "string", "type": "string", "text_vi": "string"}
                ],
                "warnings": ["string"],
            },
            "blocks": [
                {
                    "id": block.id,
                    "type": block.block_type.value,
                    "source_text": block.source_text,
                    "instruction": "keep_exactly" if block.block_type == ArticleBlockType.CODE else "translate_or_caption",
                    "language_hint": block.language_hint,
                    "metadata": block.metadata,
                }
                for block in request.blocks
            ],
        }

    @staticmethod
    def _extract_content(raw_content: Any) -> str:
        if isinstance(raw_content, str):
            return raw_content.strip()
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(part.strip() for part in parts if part.strip())
        return str(raw_content or "").strip()

    @staticmethod
    def _clean_json(raw: str) -> str:
        text = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text
