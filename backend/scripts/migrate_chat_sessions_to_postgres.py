from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import ChatMessageRow, ChatSessionRow


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> None:
    db_url = os.getenv("APP_DATABASE_URL", "").strip()
    if not db_url:
        raise SystemExit("APP_DATABASE_URL is required.")

    source_path = Path(os.getenv("APP_CHAT_SESSION_STORE_PATH", "config/chat_sessions.json"))
    if not source_path.exists():
        raise SystemExit(f"Source file not found: {source_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("Invalid source format, expected list.")

    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)

    inserted_sessions = 0
    inserted_messages = 0
    with Session(engine) as db:
        for item in payload:
            session_id = str(item.get("id", "")).strip()
            if not session_id:
                continue
            exists = db.get(ChatSessionRow, session_id)
            if exists is not None:
                continue
            row = ChatSessionRow(
                id=session_id,
                title=str(item.get("title", "New Session")),
                status=str(item.get("status", "active")),
                created_at=parse_dt(item.get("created_at")),
                updated_at=parse_dt(item.get("updated_at")),
                last_message_at=parse_dt(item.get("last_message_at")),
                message_count=int(item.get("message_count", 0) or 0),
                metadata_json=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
            db.add(row)
            inserted_sessions += 1
            for msg in item.get("messages") or []:
                message_id = str(msg.get("id", "")).strip()
                if not message_id:
                    continue
                db.add(
                    ChatMessageRow(
                        id=message_id,
                        session_id=session_id,
                        role=str(msg.get("role", "user")),
                        content=str(msg.get("content", "")),
                        created_at=parse_dt(msg.get("created_at")),
                        metadata_json=msg.get("metadata") if isinstance(msg.get("metadata"), dict) else None,
                    )
                )
                inserted_messages += 1
        db.commit()

    print(f"Done. inserted_sessions={inserted_sessions}, inserted_messages={inserted_messages}")


if __name__ == "__main__":
    main()

