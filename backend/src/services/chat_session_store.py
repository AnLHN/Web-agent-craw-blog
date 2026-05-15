from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.models.schemas import ChatMessage, ChatSession


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatSessionStore:
    def __init__(self, file_path: str, retention_days: int = 30):
        self.file_path = Path(file_path)
        self.retention_days = max(retention_days, 1)
        self._lock = threading.Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def _read_all(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_all(self, sessions: list[dict[str, Any]]) -> None:
        self.file_path.write_text(
            json.dumps(sessions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _cleanup_expired(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cutoff = _utc_now() - timedelta(days=self.retention_days)
        kept: list[dict[str, Any]] = []
        for item in sessions:
            updated_at = item.get("updated_at")
            try:
                dt = datetime.fromisoformat(str(updated_at))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = _utc_now()
            if dt >= cutoff:
                kept.append(item)
        return kept

    def create_session(self, title: str | None = None) -> ChatSession:
        now = _utc_now()
        session_id = str(uuid.uuid4())
        payload = {
            "id": session_id,
            "title": (title or "New Session").strip() or "New Session",
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_message_at": now.isoformat(),
            "message_count": 0,
            "messages": [],
            "metadata": {},
        }
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            sessions.append(payload)
            self._write_all(sessions)
        return ChatSession.model_validate(payload)

    def list_sessions(self, q: str | None = None, limit: int = 50) -> list[ChatSession]:
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            self._write_all(sessions)

        filtered = sessions
        if q:
            needle = q.strip().lower()
            filtered = [
                item for item in sessions if needle in str(item.get("title", "")).lower()
            ]
        filtered.sort(key=lambda x: str(x.get("last_message_at", "")), reverse=True)
        return [ChatSession.model_validate(item) for item in filtered[: max(1, limit)]]

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            self._write_all(sessions)
        for item in sessions:
            if item.get("id") == session_id:
                return ChatSession.model_validate(item)
        return None

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession | None:
        now = _utc_now()
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role=role.strip() or "user",
            content=content.strip(),
            created_at=now,
            metadata=metadata,
        )
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            updated = None
            for item in sessions:
                if item.get("id") != session_id:
                    continue
                messages = item.get("messages") or []
                messages.append(message.model_dump(mode="json"))
                item["messages"] = messages
                item["message_count"] = len(messages)
                item["updated_at"] = now.isoformat()
                item["last_message_at"] = now.isoformat()
                updated = item
                break
            self._write_all(sessions)
        if updated is None:
            return None
        return ChatSession.model_validate(updated)

    def replay_session(self, session_id: str) -> ChatSession | None:
        source = self.get_session(session_id=session_id)
        if source is None:
            return None

        now = _utc_now()
        new_id = str(uuid.uuid4())
        messages = [
            {
                **message.model_dump(mode="json"),
                "id": str(uuid.uuid4()),
                "metadata": {
                    **(message.metadata or {}),
                    "replayed_from_message_id": message.id,
                },
            }
            for message in source.messages
        ]
        payload = {
            "id": new_id,
            "title": f"Replay: {source.title}",
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_message_at": now.isoformat(),
            "message_count": len(messages),
            "messages": messages,
            "metadata": {"replayed_from_session_id": source.id},
        }
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            sessions.append(payload)
            self._write_all(sessions)
        return ChatSession.model_validate(payload)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            kept = [item for item in sessions if item.get("id") != session_id]
            deleted = len(kept) != len(sessions)
            if deleted:
                self._write_all(kept)
            else:
                self._write_all(sessions)
        return deleted

    def clear_sessions(self) -> int:
        with self._lock:
            sessions = self._cleanup_expired(self._read_all())
            count = len(sessions)
            self._write_all([])
        return count

    def save_search_run(
        self,
        *,
        session_id: str | None,
        query: str,
        provider_used: str,
        summary: str,
        confidence: float,
        query_analysis: dict[str, Any] | None,
        attempts: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        debug_trace: dict[str, Any] | None,
    ) -> None:
        # Local JSON mode hien tai chua luu search_runs.
        # Ham duoc de san cho interface dong nhat voi Postgres store.
        _ = (
            session_id,
            query,
            provider_used,
            summary,
            confidence,
            query_analysis,
            attempts,
            sources,
            debug_trace,
        )
        return None
