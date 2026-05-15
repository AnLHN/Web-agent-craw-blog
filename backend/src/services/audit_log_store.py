import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class AuditLogStore:
    def __init__(self, file_path: str):
        self.path = Path(file_path)
        if not self.path.is_absolute():
            self.path = Path(__file__).resolve().parents[2] / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        recent = lines[-max(limit, 1) :]
        output: list[dict[str, Any]] = []
        for line in reversed(recent):
            try:
                output.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return output
