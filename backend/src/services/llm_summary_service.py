import time
import re

import httpx

from src.config.settings import Settings
from src.models.schemas import SourceItem
from src.services.llm_runtime_store import LlmRuntimeStore
from src.services.types import ProviderAttemptData, SummaryResult
from src.utils.text import build_summary


class LlmSummaryService:
    def __init__(self, settings: Settings, runtime_store: LlmRuntimeStore):
        self.settings = settings
        self.runtime_store = runtime_store

    @staticmethod
    def _detect_answer_style(query: str) -> str:
        q = query.strip().lower()
        if any(k in q for k in ["la gi", "what is", "khai niem", "định nghĩa", "dinh nghia"]):
            return "definition"
        if any(k in q for k in ["cong ty", "company", "profile", "ceo", "founder", "ban lanh dao"]):
            return "company_profile"
        if any(k in q for k in ["so sanh", "compare", "vs ", "versus", "khac nhau"]):
            return "comparison"
        if any(k in q for k in ["huong dan", "how to", "cach", "steps", "tutorial"]):
            return "how_to"
        if any(k in q for k in ["news", "tin", "su kien", "sự kiện", "latest", "moi nhat", "mới nhất"]):
            return "news_event"
        return "general"

    @staticmethod
    def _outline_for_style(style: str) -> str:
        mapping = {
            "definition": (
                "Cau truc goi y: Khai niem -> Cach hoat dong -> Vi du ngan -> Diem can nho."
            ),
            "company_profile": (
                "Cau truc goi y: Tong quan doanh nghiep -> San pham/Dich vu -> Doi tac/He sinh thai "
                "-> Nhan su lanh dao (neu co) -> Thong tin xac minh duoc."
            ),
            "comparison": (
                "Cau truc goi y: Diem giong -> Diem khac (bang y chinh) -> Khi nao nen chon A/B -> Ket luan ngan."
            ),
            "how_to": (
                "Cau truc goi y: Cac buoc thuc hien -> Luu y quan trong -> Loi thuong gap -> Checklist ngan."
            ),
            "news_event": (
                "Cau truc goi y: Dieu gi da xay ra -> Moc thoi gian/dia diem -> Ben lien quan -> Tac dong/chu y."
            ),
            "general": (
                "Cau truc goi y: Tong quan -> Chi tiet quan trong -> Diem can chu y -> Ket luan."
            ),
        }
        return mapping.get(style, mapping["general"])

    @staticmethod
    def _build_user_prompt(query: str, sources: list[SourceItem], max_chars: int) -> str:
        lines = []
        for index, source in enumerate(sources[:5], start=1):
            snippet = source.snippet.strip().replace("\n", " ")
            lines.append(
                f"{index}. title={source.title}; domain={source.domain}; snippet={snippet}; url={source.url}"
            )

        style = LlmSummaryService._detect_answer_style(query)
        outline = LlmSummaryService._outline_for_style(style)
        joined_sources = "\n".join(lines)
        target_chars = max(120, int(max_chars * 0.9))
        return (
            "Hay viet ban tong hop day du, de doc, ro y bang tieng Viet. "
            "Khong markdown (**), khong mo dau bang cau khuon mau. "
            "Khong ep so muc co dinh; chon bo cuc linh hoat theo loai cau hoi.\n"
            f"{outline}\n"
            "Moi phan viet ngan gon, nhieu thong tin cu the, tranh lap y. "
            "Neu co thong tin tu nguon, chen '(Nguon: <domain>)' o cuoi cau/phan phu hop. "
            "Khong bịa thêm ngoài nguồn. Neu thieu du lieu thi ghi ro phan thieu du lieu. "
            f"Quan trong: tu lap ke hoach de cau tra loi hoan chinh trong khoang {target_chars}-{max_chars} ky tu. "
            "Khong viet vuot ngan sach roi trong cho he thong cat bot. "
            "Neu can rut gon, uu tien giu cau tra loi tron y hon la liet ke nhieu muc. "
            "Ket thuc bang cau tron ven, khong bo do, khong dung dau ba cham de ket thuc.\n"
            f"AnswerStyle: {style}\n"
            f"Query: {query}\n"
            f"Sources:\n{joined_sources}"
        )

    @staticmethod
    def _cap_summary_length(text: str, max_chars: int) -> str:
        cleaned = text.strip()
        if max_chars <= 0 or len(cleaned) <= max_chars:
            return cleaned
        candidate = cleaned[:max_chars].rstrip()
        last_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
        if last_end >= int(max_chars * 0.6):
            return candidate[: last_end + 1].strip()
        return candidate.rstrip(" ,;:-") + "..."

    @staticmethod
    def _is_within_length_budget(text: str, max_chars: int) -> bool:
        if max_chars <= 0:
            return True
        return len(text.strip()) <= max_chars

    @staticmethod
    def _safe_complete_fallback(query: str, sources: list[SourceItem], max_chars: int) -> str:
        pieces: list[str] = []
        if sources:
            first = sources[0]
            snippet = (first.snippet or first.title or "").replace("\n", " ").strip()
            if snippet:
                pieces.append(f"{snippet.rstrip(' .!?')}.")
            pieces.append(f"Nguon chinh: {first.domain}.")
        else:
            pieces.append(f"Chua du du lieu tu nguon de tra loi day du cho truy van: {query}.")

        answer = " ".join(pieces).strip()
        if max_chars > 0 and len(answer) > max_chars:
            answer = LlmSummaryService._cap_summary_length(answer, max_chars)
        return answer

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

        runtime = self.runtime_store.get()
        base_url = str(runtime["base_url"]).rstrip("/")
        model = str(runtime["model"])
        temperature = float(runtime["temperature"])
        max_tokens = runtime.get("max_tokens")
        summary_max_chars = int(runtime.get("summary_max_chars") or self.settings.llm_summary_max_chars or 512)
        summary_system_prompt = str(
            runtime.get("summary_system_prompt") or self.settings.llm_summary_system_prompt
        ).strip()
        started_at = time.perf_counter()

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": summary_system_prompt,
                },
                {
                    "role": "user",
                    "content": self._build_user_prompt(
                        query=query,
                        sources=sources,
                        max_chars=summary_max_chars,
                    ),
                },
            ],
            "temperature": temperature,
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = max_tokens

        try:
            content, finish_reason = await self._call_completion(base_url=base_url, payload=payload)
            rounds = 0
            while rounds < 5 and finish_reason == "length":
                continuation, continuation_reason = await self._continue_summary(
                    base_url=base_url,
                    original_summary=content,
                )
                if not continuation:
                    break
                content = f"{content.rstrip()} {continuation.lstrip()}".strip()
                finish_reason = continuation_reason
                rounds += 1
                if finish_reason != "length":
                    break

            if not content:
                latency_ms = int((time.perf_counter() - started_at) * 1000)
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

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            finalized_summary = self._ensure_complete_response(
                text=content,
                query=query,
                sources=sources,
            )
            if not finalized_summary:
                finalized_summary = build_summary(query=query, sources=sources)
            if not self._is_within_length_budget(finalized_summary, summary_max_chars):
                compact_summary = await self._rewrite_compact_complete(
                    base_url=base_url,
                    original_summary=finalized_summary,
                    query=query,
                    sources=sources,
                    max_chars=summary_max_chars,
                )
                compact_summary = self._ensure_complete_response(
                    text=compact_summary,
                    query=query,
                    sources=sources,
                )
                if compact_summary and self._is_within_length_budget(compact_summary, summary_max_chars):
                    finalized_summary = compact_summary
                else:
                    finalized_summary = self._safe_complete_fallback(
                        query=query,
                        sources=sources,
                        max_chars=summary_max_chars,
                    )
            return SummaryResult(
                summary=finalized_summary,
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

    @staticmethod
    def _has_dangling_list_tail(text: str) -> bool:
        stripped = text.rstrip()
        if not stripped:
            return False
        if re.search(r"(?:^|\n)\s*(?:\d{1,3}[.)]?|[-*])\s*$", stripped):
            return True
        if re.search(r"\b\d{1,3}\.\s*$", stripped):
            return True
        return False

    @staticmethod
    def _looks_truncated(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if "\n" not in stripped and len(stripped) <= 120 and not LlmSummaryService._has_dangling_list_tail(stripped):
            # Short one-line responses are often complete even without terminal punctuation.
            return False
        if LlmSummaryService._has_dangling_list_tail(stripped):
            return True
        if stripped.endswith((".", "!", "?", "…", "\"", "”")):
            return False
        if stripped.endswith(("*", "(", ":", ";", ",")):
            return True
        return True

    @staticmethod
    def _sanitize_summary(text: str) -> str:
        cleaned = text.replace("**", "").replace("\r", "").strip()
        cleaned = re.sub(r"^[ \t]*[-*][ \t]+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(
            r"^\s*(dưới đây|duoi day)[^:\n]{0,220}:\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        lines = [line.rstrip() for line in cleaned.splitlines()]
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            tail = lines[-1].strip()
            if tail in {"*", "-", "•"} or tail.endswith(("(", ":", ";", ",")):
                lines.pop()
        merged = "\n".join(lines).strip()
        if LlmSummaryService._has_dangling_list_tail(merged):
            merged = re.sub(r"(?:\n\s*(?:\d{1,3}[.)]?|[-*])\s*)+$", "", merged).strip()
        return merged

    @staticmethod
    def _finalize_or_fallback(content: str, query: str, sources: list[SourceItem]) -> str:
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        while lines:
            tail = lines[-1].strip()
            if tail.endswith((".", "!", "?", "…", "\"", "”")):
                break
            lines.pop()
        finalized = "\n".join(lines).strip()
        if finalized and len(finalized) >= 180:
            return finalized

        # Deterministic fallback to avoid returning a cut-off answer.
        return (
            f"Tong hop nhanh cho truy van: {query}.\n\n"
            f"{build_summary(query=query, sources=sources)}\n\n"
            "Luu y: Cau tra loi da duoc rut gon theo nguon de tranh hien thi noi dung bi cat giua chung."
        )

    @staticmethod
    def _ensure_complete_response(text: str, query: str, sources: list[SourceItem]) -> str:
        cleaned = LlmSummaryService._sanitize_summary(text).strip()
        if not cleaned:
            return (
                f"Tong hop nhanh cho truy van: {query}.\n\n"
                f"{build_summary(query=query, sources=sources)}"
            )

        if LlmSummaryService._has_dangling_list_tail(cleaned):
            cleaned = re.sub(r"(?:\n\s*(?:\d{1,3}[.)]?|[-*])\s*)+$", "", cleaned).strip()

        if cleaned.endswith((".", "!", "?", "…", "\"", "”")):
            return cleaned

        if "\n" not in cleaned and len(cleaned) <= 200 and not LlmSummaryService._has_dangling_list_tail(cleaned):
            return f"{cleaned}."

        # If text still looks cut, prefer deterministic fallback over returning partial output.
        if LlmSummaryService._looks_truncated(cleaned):
            last_end = max(cleaned.rfind("."), cleaned.rfind("!"), cleaned.rfind("?"), cleaned.rfind("…"))
            if last_end != -1 and last_end >= int(len(cleaned) * 0.65):
                candidate = cleaned[: last_end + 1].strip()
                if candidate and candidate.endswith((".", "!", "?", "…", "\"", "”")):
                    return candidate

            return LlmSummaryService._finalize_or_fallback(
                content=cleaned,
                query=query,
                sources=sources,
            )

        # Cut to the last complete sentence-ending punctuation.
        last_end = max(cleaned.rfind("."), cleaned.rfind("!"), cleaned.rfind("?"), cleaned.rfind("…"))
        if last_end != -1 and last_end >= int(len(cleaned) * 0.35):
            return cleaned[: last_end + 1].strip()

        # Deterministic complete fallback.
        bullet_lines: list[str] = []
        for idx, src in enumerate(sources[:5], start=1):
            snippet = (src.snippet or src.title or "").replace("\n", " ").strip()
            if not snippet:
                continue
            if snippet[-1] not in ".!?":
                snippet = f"{snippet}."
            bullet_lines.append(f"{idx}. {snippet} (nguon: {src.domain}).")
        if bullet_lines:
            return (
                f"Tong hop nhanh cho truy van: {query}.\n\n"
                + "\n".join(bullet_lines)
            )
        return f"Chua du du lieu tu nguon de tra loi day du cho truy van: {query}."

    async def _continue_summary(self, base_url: str, original_summary: str) -> tuple[str, str]:
        runtime = self.runtime_store.get()
        payload = {
            "model": str(runtime["model"]),
            "messages": [
                {
                    "role": "system",
                    "content": "Ban la tro ly hoan thien doan tom tat dang bi cat do.",
                },
                {
                    "role": "user",
                    "content": (
                        "Doan sau dang bi cat do. Hay viet tiep 2-4 cau de ket thuc tron y, "
                        "khong lap lai phan da co, khong markdown.\n\n"
                        f"Doan hien tai:\n{original_summary}"
                    ),
                },
            ],
            "temperature": float(runtime["temperature"]),
        }
        max_tokens = runtime.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = max_tokens

        return await self._call_completion(base_url=base_url, payload=payload)

    async def _call_completion(self, base_url: str, payload: dict) -> tuple[str, str]:
        llm_timeout = max(self.settings.request_timeout_seconds, 40.0)
        async with httpx.AsyncClient(timeout=llm_timeout) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload)
        if response.status_code >= 400:
            return "", "error"
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return "", "empty"
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = self._extract_message_content(message.get("content"))
        finish_reason = str(choice.get("finish_reason") or "")
        return content, finish_reason

    @staticmethod
    def _extract_message_content(raw_content) -> str:
        if isinstance(raw_content, str):
            return raw_content.strip()
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if isinstance(item, str):
                    if item.strip():
                        parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
            return "\n".join(parts).strip()
        if raw_content is None:
            return ""
        return str(raw_content).strip()

    async def _rewrite_compact_complete(
        self,
        base_url: str,
        original_summary: str,
        query: str,
        sources: list[SourceItem],
        max_chars: int,
    ) -> str:
        runtime = self.runtime_store.get()
        source_lines = []
        for index, source in enumerate(sources[:5], start=1):
            snippet = (source.snippet or source.title or "").replace("\n", " ").strip()
            source_lines.append(f"{index}. domain={source.domain}; snippet={snippet}")
        payload = {
            "model": str(runtime["model"]),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ban la tro ly bien tap noi dung. "
                        "Nhiem vu: viet lai cau tra loi ngan gon, hoan chinh, de agent khac doc lai van hieu."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Hay viet lai cau tra loi cho query trong toi da {max_chars} ky tu. "
                        "Bat buoc tu rut gon y truoc khi viet, khong de he thong cat bot. "
                        "Giu cac y quan trong nhat, uu tien cau tron ven, khong markdown, khong ky hieu **, "
                        "khong dung dau ba cham de ket thuc. Neu can dan nguon, dung domain ngan gon trong ngoac.\n\n"
                        f"Query: {query}\n"
                        f"Nguon:\n{chr(10).join(source_lines)}\n\n"
                        f"Ban can rut gon:\n{original_summary}"
                    ),
                },
            ],
            "temperature": float(runtime["temperature"]),
        }
        max_tokens = runtime.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = max_tokens
        content, _ = await self._call_completion(base_url=base_url, payload=payload)
        return content.strip()
