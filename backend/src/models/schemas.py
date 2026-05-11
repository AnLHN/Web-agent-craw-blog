from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ResponseMeta(BaseModel):
    timestamp: datetime
    request_id: Optional[str] = None


class SourceItem(BaseModel):
    title: str
    url: str
    snippet: str
    domain: str
    score: float = 0.0
    published_date: Optional[str] = None


class ProviderAttempt(BaseModel):
    provider: str
    status: str
    reason: str
    latency_ms: int
    result_count: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    top_k: int = Field(default=5, ge=1, le=10)


class SearchResultData(BaseModel):
    query: str
    provider_used: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: List[SourceItem]
    attempts: List[ProviderAttempt]


class SearchResponse(BaseModel):
    success: bool
    data: Optional[SearchResultData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class KeyCreateRequest(BaseModel):
    api_key: str = Field(min_length=8)
    label: Optional[str] = None


class KeyInfo(BaseModel):
    id: str
    label: str
    masked_key: str
    status: str
    success_rate_5m: float
    last_used_at: Optional[str]
    cooldown_until: Optional[str]


class TavilyKeysData(BaseModel):
    keys: List[KeyInfo]


class TavilyKeysResponse(BaseModel):
    success: bool
    data: Optional[TavilyKeysData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class HealthData(BaseModel):
    status: str
    service: str
    version: str


class HealthResponse(BaseModel):
    success: bool
    data: HealthData
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta
