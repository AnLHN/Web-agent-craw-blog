import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import httpx

from src.config.settings import Settings


class LlmRuntimeStore:
    _UNSET = object()

    def __init__(self, settings: Settings, file_path: str):
        self.settings = settings
        self.path = Path(file_path)
        if not self.path.is_absolute():
            self.path = Path(__file__).resolve().parents[2] / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "base_url": self.settings.llm_base_url,
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "max_tokens": self.settings.llm_max_tokens,
                "summary_max_tokens": self.settings.llm_summary_max_tokens,
                "summary_max_chars": self.settings.llm_summary_max_chars,
                "summary_system_prompt": self.settings.llm_summary_system_prompt,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            summary_max_chars = self._validate_summary_max_chars(raw.get("summary_max_chars"))
            summary_max_tokens = self._validate_summary_max_tokens(
                raw.get("summary_max_tokens", self.settings.llm_summary_max_tokens)
            )
            summary_system_prompt = self._validate_summary_system_prompt(
                raw.get("summary_system_prompt", self.settings.llm_summary_system_prompt)
            )
            return {
                "base_url": str(raw.get("base_url") or self.settings.llm_base_url),
                "model": str(raw.get("model") or self.settings.llm_model),
                "temperature": float(raw.get("temperature", self.settings.llm_temperature)),
                "max_tokens": raw.get("max_tokens", self.settings.llm_max_tokens),
                "summary_max_tokens": summary_max_tokens,
                "summary_max_chars": summary_max_chars,
                "summary_system_prompt": summary_system_prompt,
                "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            return {
                "base_url": self.settings.llm_base_url,
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "max_tokens": self.settings.llm_max_tokens,
                "summary_max_tokens": self.settings.llm_summary_max_tokens,
                "summary_max_chars": self.settings.llm_summary_max_chars,
                "summary_system_prompt": self.settings.llm_summary_system_prompt,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    def _persist(self) -> None:
        self.path.write_text(json.dumps(self._state, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid http/https URL")
        return base_url.rstrip("/")

    @staticmethod
    def _validate_temperature(value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("temperature must be in range [0.0, 2.0]")
        return value

    @staticmethod
    def _validate_max_tokens(value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0 or value > 16384:
            raise ValueError("max_tokens must be in range [1, 16384] or null")
        return value

    @staticmethod
    def _validate_summary_max_chars(value: int | None) -> int:
        if value is None:
            return 512
        if value < 120 or value > 4000:
            raise ValueError("summary_max_chars must be in range [120, 4000]")
        return value

    @staticmethod
    def _validate_summary_max_tokens(value: int | None) -> int:
        if value is None:
            return 512
        if value < 32 or value > 16384:
            raise ValueError("summary_max_tokens must be in range [32, 16384]")
        return value

    @staticmethod
    def _validate_summary_system_prompt(value: Any) -> str:
        prompt = str(value or "").strip()
        if len(prompt) < 20 or len(prompt) > 8000:
            raise ValueError("summary_system_prompt length must be in range [20, 8000]")
        return prompt

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def update(
        self,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None | object = _UNSET,
        summary_max_tokens: int | None | object = _UNSET,
        summary_max_chars: int | None | object = _UNSET,
        summary_system_prompt: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        with self._lock:
            if base_url is not None:
                self._state["base_url"] = self._validate_base_url(base_url)
            if model is not None:
                model_value = model.strip()
                if not model_value:
                    raise ValueError("model must not be empty")
                self._state["model"] = model_value
            if temperature is not None:
                self._state["temperature"] = self._validate_temperature(float(temperature))
            if max_tokens is not self._UNSET:
                self._state["max_tokens"] = self._validate_max_tokens(max_tokens)  # type: ignore[arg-type]
            if summary_max_tokens is not self._UNSET:
                self._state["summary_max_tokens"] = self._validate_summary_max_tokens(summary_max_tokens)  # type: ignore[arg-type]
            if summary_max_chars is not self._UNSET:
                self._state["summary_max_chars"] = self._validate_summary_max_chars(summary_max_chars)  # type: ignore[arg-type]
            if summary_system_prompt is not self._UNSET:
                self._state["summary_system_prompt"] = self._validate_summary_system_prompt(summary_system_prompt)
            self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._persist()
            return dict(self._state)

    async def health(self, timeout_seconds: float) -> dict[str, Any]:
        config = self.get()
        base_url = str(config["base_url"]).rstrip("/")
        started_at = datetime.now(timezone.utc)
        ok = False
        message = "unreachable"
        try:
            async with httpx.AsyncClient(timeout=max(timeout_seconds, 10.0)) as client:
                response = await client.get(f"{base_url}/models")
            ok = response.status_code < 400
            message = "ok" if ok else f"http_{response.status_code}"
        except httpx.HTTPError:
            ok = False
            message = "network_error"
        ended_at = datetime.now(timezone.utc)
        latency_ms = int((ended_at - started_at).total_seconds() * 1000)
        return {
            "ok": ok,
            "message": message,
            "latency_ms": latency_ms,
            "base_url": base_url,
            "checked_at": ended_at.isoformat(),
        }

    async def dry_run(self, prompt: str, timeout_seconds: float) -> dict[str, Any]:
        config = self.get()
        base_url = str(config["base_url"]).rstrip("/")
        payload: dict[str, Any] = {
            "model": str(config["model"]),
            "messages": [
                {"role": "system", "content": "Return concise answer only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": float(config["temperature"]),
        }
        if config.get("max_tokens") is not None:
            payload["max_tokens"] = int(config["max_tokens"])

        started_at = datetime.now(timezone.utc)
        response_text = ""
        finish_reason = "unknown"
        status = "failed"
        try:
            async with httpx.AsyncClient(timeout=max(timeout_seconds, 20.0)) as client:
                response = await client.post(f"{base_url}/chat/completions", json=payload)
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            if response.status_code >= 400:
                return {
                    "status": "failed",
                    "finish_reason": f"http_{response.status_code}",
                    "latency_ms": latency_ms,
                    "response_preview": "",
                }
            data = response.json()
            choices = data.get("choices") or []
            if choices:
                choice = choices[0] or {}
                finish_reason = str(choice.get("finish_reason") or "stop")
                message = choice.get("message") or {}
                raw_content = message.get("content")
                if isinstance(raw_content, str):
                    response_text = raw_content
                elif isinstance(raw_content, list):
                    chunks: list[str] = []
                    for item in raw_content:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            chunks.append(item["text"])
                    response_text = "\n".join(chunks).strip()
            status = "success"
            return {
                "status": status,
                "finish_reason": finish_reason,
                "latency_ms": latency_ms,
                "response_preview": response_text[:500],
            }
        except httpx.HTTPError:
            latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
            return {
                "status": "failed",
                "finish_reason": "network_error",
                "latency_ms": latency_ms,
                "response_preview": "",
            }
