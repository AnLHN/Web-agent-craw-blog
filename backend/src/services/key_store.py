import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class TavilyKeyRecord:
    id: str
    api_key: str
    label: str
    status: str = "active"
    success_count: int = 0
    failure_count: int = 0
    last_used_at: str | None = None
    cooldown_until: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success_rate_5m(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return round(self.success_count / total, 2)


class TavilyKeyStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
        self._records: list[TavilyKeyRecord] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.file_path.exists():
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self.file_path.write_text("[]", encoding="utf-8")
                self._records = []
                return

            raw = self.file_path.read_text(encoding="utf-8").strip() or "[]"
            data = json.loads(raw)
            self._records = [TavilyKeyRecord(**item) for item in data]

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        data = [record.__dict__ for record in self._records]
        tmp_file = self.file_path.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp_file, self.file_path)

    def list_records(self) -> list[TavilyKeyRecord]:
        with self._lock:
            return [TavilyKeyRecord(**record.__dict__) for record in self._records]

    def add_key(self, api_key: str, label: str | None = None) -> TavilyKeyRecord:
        cleaned_key = api_key.strip()
        if not cleaned_key:
            raise ValueError("API key is empty")

        with self._lock:
            for record in self._records:
                if record.api_key == cleaned_key:
                    return TavilyKeyRecord(**record.__dict__)

            record = TavilyKeyRecord(
                id=str(uuid.uuid4()),
                api_key=cleaned_key,
                label=label.strip() if label else "Default key",
            )
            self._records.append(record)
            self._save()
            return TavilyKeyRecord(**record.__dict__)

    def delete_key(self, key_id: str) -> bool:
        with self._lock:
            before = len(self._records)
            self._records = [record for record in self._records if record.id != key_id]
            removed = len(self._records) < before
            if removed:
                self._save()
            return removed

    def has_keys(self) -> bool:
        with self._lock:
            return len(self._records) > 0

    def get_next_active_key(self) -> TavilyKeyRecord | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            candidates: list[TavilyKeyRecord] = []
            for record in self._records:
                if record.status not in {"active", "cooling_down"}:
                    continue

                if record.cooldown_until:
                    try:
                        cooldown_until = datetime.fromisoformat(record.cooldown_until)
                    except ValueError:
                        cooldown_until = now

                    if cooldown_until > now:
                        continue

                candidates.append(record)

            if not candidates:
                return None

            candidates.sort(key=lambda item: (item.last_used_at or "", -item.success_rate_5m))
            selected = candidates[0]
            selected.last_used_at = now.isoformat()
            selected.status = "active"
            selected.updated_at = now.isoformat()
            self._save()
            return TavilyKeyRecord(**selected.__dict__)

    def mark_success(self, key_id: str) -> None:
        self._update_stats(key_id=key_id, ok=True)

    def mark_failure(self, key_id: str) -> None:
        self._update_stats(key_id=key_id, ok=False)

    def mark_rate_limited(self, key_id: str, cooldown_seconds: int) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            for record in self._records:
                if record.id != key_id:
                    continue
                record.failure_count += 1
                record.status = "cooling_down"
                record.cooldown_until = (now + timedelta(seconds=cooldown_seconds)).isoformat()
                record.updated_at = now.isoformat()
                self._save()
                return

    def _update_stats(self, key_id: str, ok: bool) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            for record in self._records:
                if record.id != key_id:
                    continue
                if ok:
                    record.success_count += 1
                    record.status = "active"
                    record.cooldown_until = None
                else:
                    record.failure_count += 1
                record.updated_at = now.isoformat()
                self._save()
                return


def mask_key(api_key: str) -> str:
    if len(api_key) < 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"
