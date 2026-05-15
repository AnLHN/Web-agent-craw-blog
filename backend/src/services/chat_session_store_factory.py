from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.services.chat_session_store import ChatSessionStore
from src.services.postgres_chat_session_store import PostgresChatSessionStore


class DualWriteChatSessionStore:
    def __init__(self, primary_store: Any, secondary_store: Any):
        self.primary_store = primary_store
        self.secondary_store = secondary_store

    def create_session(self, title: str | None = None):
        session = self.primary_store.create_session(title=title)
        return session

    def list_sessions(self, q: str | None = None, limit: int = 50):
        return self.primary_store.list_sessions(q=q, limit=limit)

    def get_session(self, session_id: str):
        return self.primary_store.get_session(session_id=session_id)

    def add_message(self, session_id: str, role: str, content: str, metadata=None):
        session = self.primary_store.add_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        return session

    def replay_session(self, session_id: str):
        session = self.primary_store.replay_session(session_id=session_id)
        return session

    def delete_session(self, session_id: str) -> bool:
        deleted = self.primary_store.delete_session(session_id=session_id)
        try:
            self.secondary_store.delete_session(session_id=session_id)
        except Exception:
            pass
        return deleted

    def clear_sessions(self) -> int:
        count = self.primary_store.clear_sessions()
        try:
            self.secondary_store.clear_sessions()
        except Exception:
            pass
        return count

    def save_search_run(
        self,
        *,
        session_id: str | None,
        query: str,
        provider_used: str,
        summary: str,
        confidence: float,
        query_analysis: dict | None,
        attempts: list[dict],
        sources: list[dict],
        debug_trace: dict | None,
    ) -> None:
        self.primary_store.save_search_run(
            session_id=session_id,
            query=query,
            provider_used=provider_used,
            summary=summary,
            confidence=confidence,
            query_analysis=query_analysis,
            attempts=attempts,
            sources=sources,
            debug_trace=debug_trace,
        )
        try:
            self.secondary_store.save_search_run(
                session_id=session_id,
                query=query,
                provider_used=provider_used,
                summary=summary,
                confidence=confidence,
                query_analysis=query_analysis,
                attempts=attempts,
                sources=sources,
                debug_trace=debug_trace,
            )
        except Exception:
            pass


def build_chat_session_store(settings: Settings):
    local_store = ChatSessionStore(
        file_path=settings.chat_session_store_path,
        retention_days=settings.chat_session_retention_days,
    )
    backend = (settings.session_store_backend or "auto").strip().lower()
    db_url = (settings.database_url or "").strip()

    can_use_postgres = bool(db_url and db_url.startswith("postgres"))
    if backend == "local":
        return local_store
    if backend == "postgres":
        if not can_use_postgres:
            raise ValueError("APP_SESSION_STORE_BACKEND=postgres nhung APP_DATABASE_URL chua hop le.")
        return PostgresChatSessionStore(
            database_url=db_url,
            retention_days=settings.chat_session_retention_days,
        )
    if backend == "auto":
        if not can_use_postgres:
            return local_store
        postgres_store = PostgresChatSessionStore(
            database_url=db_url,
            retention_days=settings.chat_session_retention_days,
        )
        if settings.session_store_dual_write:
            return DualWriteChatSessionStore(
                primary_store=postgres_store,
                secondary_store=local_store,
            )
        return postgres_store

    return local_store
