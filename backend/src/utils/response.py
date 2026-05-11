from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def response_meta(request_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc),
        "request_id": request_id,
    }
