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
    sub_query: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    top_k: int = Field(default=5, ge=1, le=10)
    session_id: Optional[str] = None


class QueryAnalysisInfo(BaseModel):
    original_query: str
    normalized_query: str
    intent: str
    expanded_sub_queries: List[str]
    planned_sub_queries: List[str] = Field(default_factory=list)
    complexity: str = "simple"
    retrieval_budget: int = 1
    evidence_kept_count: int = 0
    evidence_dropped_count: int = 0
    evidence_dropped_reason_summary: str = ""
    query_expansion_count: int = 0
    subquery_cache_hit_rate: float = 0.0
    retrieval_coverage: float = 0.0
    analysis_reasoning_short: str


class SearchResultData(BaseModel):
    query: str
    provider_used: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: List[SourceItem]
    attempts: List[ProviderAttempt]
    query_analysis: Optional[QueryAnalysisInfo] = None


class SearchResponse(BaseModel):
    success: bool
    data: Optional[SearchResultData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class KeyCreateRequest(BaseModel):
    api_key: str = Field(min_length=8)
    label: Optional[str] = None


class KeyUpdateRequest(BaseModel):
    label: Optional[str] = None
    status: Optional[str] = None


class KeyInfo(BaseModel):
    id: str
    label: str
    masked_key: str
    status: str
    success_rate_5m: float
    last_used_at: Optional[str]
    cooldown_until: Optional[str]
    success_count: int = 0
    failure_count: int = 0


class TavilyKeysData(BaseModel):
    keys: List[KeyInfo]


class TavilyKeyMetricsData(BaseModel):
    total_keys: int
    active_keys: int
    cooling_down_keys: int
    unhealthy_keys: int
    exhausted_keys: int
    total_success_count: int
    total_failure_count: int
    average_success_rate: float
    keys: List[KeyInfo]


class TavilyKeysResponse(BaseModel):
    success: bool
    data: Optional[TavilyKeysData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class TavilyKeyMetricsResponse(BaseModel):
    success: bool
    data: Optional[TavilyKeyMetricsData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    llm_enabled: bool = True
    llm_base_url: str = ""


class HealthResponse(BaseModel):
    success: bool
    data: HealthData
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class ChatSession(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    message_count: int = 0
    messages: List[ChatMessage] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None


class ChatSessionCreateRequest(BaseModel):
    title: Optional[str] = None


class ChatMessageCreateRequest(BaseModel):
    role: str = Field(default="user")
    content: str = Field(min_length=1, max_length=4000)
    metadata: Optional[Dict[str, Any]] = None


class ChatSessionData(BaseModel):
    session: ChatSession


class ChatSessionListData(BaseModel):
    sessions: List[ChatSession]
    total: int


class ChatSessionResponse(BaseModel):
    success: bool
    data: Optional[ChatSessionData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class ChatSessionListResponse(BaseModel):
    success: bool
    data: Optional[ChatSessionListData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class LlmRuntimeConfig(BaseModel):
    base_url: str
    model: str
    temperature: float
    max_tokens: Optional[int] = None
    summary_max_tokens: int = 512
    summary_max_chars: int = 512
    summary_system_prompt: str
    updated_at: str


class LlmRuntimeConfigPatchRequest(BaseModel):
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=16384)
    summary_max_tokens: Optional[int] = Field(default=None, ge=32, le=16384)
    summary_max_chars: Optional[int] = Field(default=None, ge=120, le=4000)
    summary_system_prompt: Optional[str] = Field(default=None, min_length=20, max_length=8000)


class LlmTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class LlmHealthData(BaseModel):
    ok: bool
    message: str
    latency_ms: int
    base_url: str
    checked_at: str


class LlmTestData(BaseModel):
    status: str
    finish_reason: str
    latency_ms: int
    response_preview: str


class LlmRuntimeConfigData(BaseModel):
    config: LlmRuntimeConfig


class LlmRuntimeConfigResponse(BaseModel):
    success: bool
    data: Optional[LlmRuntimeConfigData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class LlmHealthResponse(BaseModel):
    success: bool
    data: Optional[LlmHealthData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class LlmTestResponse(BaseModel):
    success: bool
    data: Optional[LlmTestData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class AuditLogItem(BaseModel):
    timestamp: str
    actor_role: str = "unknown"
    action: str = "unknown"
    path: str = ""
    method: str = ""
    status: str = "unknown"
    details: Optional[Dict[str, Any]] = None


class AuditLogData(BaseModel):
    events: List[AuditLogItem]
    total: int


class AuditLogResponse(BaseModel):
    success: bool
    data: Optional[AuditLogData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta
