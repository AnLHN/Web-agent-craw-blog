from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import ChatMessageRow, ChatSessionRow, PipelineAttemptRow, SearchRunRow, SearchSourceRow
from src.models.schemas import ChatMessage, ChatSession


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresChatSessionStore:
    def __init__(self, database_url: str, retention_days: int = 30):
        self.retention_days = max(retention_days, 1)
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        Base.metadata.create_all(self.engine)

    def _cleanup_expired(self, db: Session) -> None:
        cutoff = _utc_now() - timedelta(days=self.retention_days)
        stale_session_ids = db.scalars(
            select(ChatSessionRow.id).where(ChatSessionRow.updated_at < cutoff)
        ).all()
        if not stale_session_ids:
            return
        db.execute(delete(ChatMessageRow).where(ChatMessageRow.session_id.in_(stale_session_ids)))
        db.execute(delete(ChatSessionRow).where(ChatSessionRow.id.in_(stale_session_ids)))

    def _to_session(self, db: Session, row: ChatSessionRow) -> ChatSession:
        messages = db.scalars(
            select(ChatMessageRow)
            .where(ChatMessageRow.session_id == row.id)
            .order_by(ChatMessageRow.created_at.asc())
        ).all()
        payload = {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "last_message_at": row.last_message_at.isoformat(),
            "message_count": row.message_count,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                    "metadata": msg.metadata_json,
                }
                for msg in messages
            ],
            "metadata": row.metadata_json,
        }
        return ChatSession.model_validate(payload)

    def create_session(self, title: str | None = None) -> ChatSession:
        now = _utc_now()
        row = ChatSessionRow(
            id=str(uuid.uuid4()),
            title=(title or "New Session").strip() or "New Session",
            status="active",
            created_at=now,
            updated_at=now,
            last_message_at=now,
            message_count=0,
            metadata_json={},
        )
        with self.session_factory() as db:
            self._cleanup_expired(db)
            db.add(row)
            db.commit()
            return self._to_session(db, row)

    def list_sessions(self, q: str | None = None, limit: int = 50) -> list[ChatSession]:
        with self.session_factory() as db:
            self._cleanup_expired(db)
            stmt = select(ChatSessionRow)
            if q:
                stmt = stmt.where(ChatSessionRow.title.ilike(f"%{q.strip()}%"))
            rows = db.scalars(
                stmt.order_by(ChatSessionRow.last_message_at.desc()).limit(max(1, limit))
            ).all()
            db.commit()
            return [self._to_session(db, row) for row in rows]

    def get_session(self, session_id: str) -> ChatSession | None:
        with self.session_factory() as db:
            self._cleanup_expired(db)
            row = db.get(ChatSessionRow, session_id)
            db.commit()
            if row is None:
                return None
            return self._to_session(db, row)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession | None:
        now = _utc_now()
        with self.session_factory() as db:
            self._cleanup_expired(db)
            session_row = db.get(ChatSessionRow, session_id)
            if session_row is None:
                db.commit()
                return None
            message = ChatMessageRow(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=role.strip() or "user",
                content=content.strip(),
                created_at=now,
                metadata_json=metadata,
            )
            db.add(message)
            session_row.message_count = (session_row.message_count or 0) + 1
            session_row.updated_at = now
            session_row.last_message_at = now
            db.commit()
            return self._to_session(db, session_row)

    def replay_session(self, session_id: str) -> ChatSession | None:
        with self.session_factory() as db:
            self._cleanup_expired(db)
            source = db.get(ChatSessionRow, session_id)
            if source is None:
                db.commit()
                return None
            source_messages = db.scalars(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.created_at.asc())
            ).all()
            now = _utc_now()
            new_session = ChatSessionRow(
                id=str(uuid.uuid4()),
                title=f"Replay: {source.title}",
                status="active",
                created_at=now,
                updated_at=now,
                last_message_at=now,
                message_count=len(source_messages),
                metadata_json={"replayed_from_session_id": source.id},
            )
            db.add(new_session)
            for msg in source_messages:
                db.add(
                    ChatMessageRow(
                        id=str(uuid.uuid4()),
                        session_id=new_session.id,
                        role=msg.role,
                        content=msg.content,
                        created_at=now,
                        metadata_json={
                            **(msg.metadata_json or {}),
                            "replayed_from_message_id": msg.id,
                        },
                    )
                )
            db.commit()
            return self._to_session(db, new_session)

    def delete_session(self, session_id: str) -> bool:
        with self.session_factory() as db:
            self._cleanup_expired(db)
            row = db.get(ChatSessionRow, session_id)
            if row is None:
                db.commit()
                return False
            db.execute(delete(ChatMessageRow).where(ChatMessageRow.session_id == session_id))
            db.delete(row)
            db.commit()
            return True

    def clear_sessions(self) -> int:
        with self.session_factory() as db:
            self._cleanup_expired(db)
            total = db.query(ChatSessionRow).count()
            db.execute(delete(ChatMessageRow))
            db.execute(delete(ChatSessionRow))
            db.commit()
            return total

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
        run_id = str(uuid.uuid4())
        with self.session_factory() as db:
            run = SearchRunRow(
                id=run_id,
                session_id=session_id,
                query=query,
                provider_used=provider_used,
                summary=summary,
                confidence=confidence,
                query_analysis=query_analysis,
                debug_trace=debug_trace,
                created_at=_utc_now(),
            )
            db.add(run)
            db.commit()

        with self.session_factory() as db:
            for source in sources:
                db.add(
                    SearchSourceRow(
                        search_run_id=run_id,
                        title=str(source.get("title", "")),
                        url=str(source.get("url", "")),
                        domain=str(source.get("domain", "")),
                        snippet=str(source.get("snippet", "")),
                        score=float(source.get("score", 0.0) or 0.0),
                        published_date=source.get("published_date"),
                        raw=source,
                    )
                )
            for attempt in attempts:
                db.add(
                    PipelineAttemptRow(
                        search_run_id=run_id,
                        provider=str(attempt.get("provider", "")),
                        status=str(attempt.get("status", "")),
                        reason=str(attempt.get("reason", "")),
                        latency_ms=int(attempt.get("latency_ms", 0) or 0),
                        result_count=int(attempt.get("result_count", 0) or 0),
                        sub_query=attempt.get("sub_query"),
                        raw=attempt,
                    )
                )
            db.commit()
