import re
from typing import Any

import httpx

from src.config.settings import Settings
from src.models.schemas import ChatMessage
from src.services.llm_runtime_store import LlmRuntimeStore


class ContextQueryRewriterService:
    def __init__(self, settings: Settings, runtime_store: LlmRuntimeStore):
        self.settings = settings
        self.runtime_store = runtime_store

    @staticmethod
    def _extract_message_content(raw_content: Any) -> str:
        if isinstance(raw_content, str):
            return raw_content.strip()
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()
        return str(raw_content or "").strip()

    @staticmethod
    def _clean_rewritten_query(text: str) -> str:
        cleaned = re.sub(r"^```(?:text)?|```$", "", text.strip(), flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip("\"'` ")
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        if not lines:
            return ""
        return " ".join(lines)[:400]

    @staticmethod
    def _compact(text: str, max_chars: int) -> str:
        return re.sub(r"\s+", " ", text or "").strip()[:max_chars]

    @staticmethod
    def _history_lines(messages: list[ChatMessage], max_messages: int = 12) -> str:
        relevant = messages[-max(1, max_messages) :]
        lines: list[str] = []
        for item in relevant:
            content = ContextQueryRewriterService._compact(item.content, 500 if item.role == "user" else 350)
            if not content:
                continue
            role = "User" if item.role == "user" else "Assistant"
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _looks_context_dependent(query: str) -> bool:
        q = query.lower()
        ambiguous_terms = [
            "nó",
            "no",
            "họ",
            "ho",
            "đó",
            "do",
            "này",
            "nay",
            "cái này",
            "cai nay",
            "người đó",
            "nguoi do",
            "công ty",
            "cong ty",
            "người đứng đầu",
            "nguoi dung dau",
            "ceo",
            "giám đốc",
            "giam doc",
            "lãnh đạo",
            "lanh dao",
        ]
        return any(term in q for term in ambiguous_terms)

    @staticmethod
    def _extract_focus_from_history(messages: list[ChatMessage]) -> str:
        user_messages = [item.content for item in messages if item.role == "user"]
        for content in reversed(user_messages):
            text = ContextQueryRewriterService._compact(content, 260)
            patterns = [
                r"(?:về|ve|công ty|cong ty|chủ đề|chu de)\s+([A-ZÀ-ỴĐ][\wÀ-Ỵà-ỵĐđ]*(?:\s+[A-ZÀ-ỴĐ][\wÀ-Ỵà-ỵĐđ]*){0,7})",
                r"\b([A-ZÀ-ỴĐ][\wÀ-Ỵà-ỵĐđ]*(?:\s+[A-ZÀ-ỴĐ][\wÀ-Ỵà-ỵĐđ]*){1,7})\b",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if not match:
                    continue
                focus = match.group(1).strip(" .,;:!?")
                if len(focus) < 3:
                    continue
                if focus.lower() in {"người đứng đầu", "google search"}:
                    continue
                return focus
        return ""

    @staticmethod
    def _fallback_rewrite(query: str, messages: list[ChatMessage]) -> str:
        if not ContextQueryRewriterService._looks_context_dependent(query):
            return query
        focus = ContextQueryRewriterService._extract_focus_from_history(messages)
        if not focus or focus.lower() in query.lower():
            return query
        return f"{query} về {focus}"[:400]

    async def rewrite(self, query: str, messages: list[ChatMessage]) -> str:
        history = self._history_lines(messages)
        if not history:
            return query
        if not self.settings.llm_enabled:
            return self._fallback_rewrite(query=query, messages=messages)

        runtime = self.runtime_store.get()
        base_url = str(runtime["base_url"]).rstrip("/")
        max_tokens = runtime.get("max_tokens")
        payload: dict[str, Any] = {
            "model": str(runtime["model"]),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ban la bo viet lai cau hoi cho web search trong mot phien chat co ngu canh. "
                        "Hay hieu chu the dang duoc noi toi trong cung phien chat, dac biet la cac luot gan nhat. "
                        "Neu cau hoi hien tai co dai tu/cum mo ho nhu 'no', 'ho', 'cong ty', 'nguoi dung dau', "
                        "hay thay bang chu the cu the tu ngu canh phien chat. "
                        "Khong duoc doi sang chu de khac neu phien chat dang noi ve mot nguoi, cong ty, san pham, su kien cu the. "
                        "Neu cau hoi da doc lap, giu nguyen. "
                        "Chi tra ve dung mot truy van tim kiem doc lap, khong markdown, khong giai thich."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Ngu canh phien chat gan day:\n{history}\n\n"
                        f"Cau hoi hien tai: {query}\n\n"
                        "Truy van tim web doc lap:"
                    ),
                },
            ],
            "temperature": 0.0,
            "max_tokens": 140,
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = min(140, max_tokens)

        try:
            timeout = max(self.settings.request_timeout_seconds, 20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{base_url}/chat/completions", json=payload)
            if response.status_code >= 400:
                return self._fallback_rewrite(query=query, messages=messages)
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return self._fallback_rewrite(query=query, messages=messages)
            message = (choices[0] or {}).get("message") or {}
            rewritten = self._clean_rewritten_query(self._extract_message_content(message.get("content")))
            if not rewritten:
                return self._fallback_rewrite(query=query, messages=messages)
            return rewritten
        except (httpx.HTTPError, ValueError):
            return self._fallback_rewrite(query=query, messages=messages)
