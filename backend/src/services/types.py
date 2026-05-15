from dataclasses import dataclass, field

from src.models.schemas import SourceItem


@dataclass
class ProviderAttemptData:
    provider: str
    status: str
    reason: str
    latency_ms: int
    result_count: int
    sub_query: str | None = None


@dataclass
class ProviderSearchResult:
    provider: str
    sources: list[SourceItem] = field(default_factory=list)
    attempts: list[ProviderAttemptData] = field(default_factory=list)


@dataclass
class SummaryResult:
    summary: str
    attempt: ProviderAttemptData


@dataclass
class QueryAnalysisResult:
    original_query: str
    normalized_query: str
    intent: str
    sub_queries: list[str] = field(default_factory=list)
    analysis_reasoning_short: str = ""
    attempt: ProviderAttemptData | None = None


@dataclass
class QueryPlanResult:
    complexity: str
    retrieval_budget: int
    planned_sub_queries: list[str] = field(default_factory=list)
    attempt: ProviderAttemptData | None = None


@dataclass
class EvidenceMergeResult:
    kept_sources: list[SourceItem] = field(default_factory=list)
    dropped_count: int = 0
    dropped_reason_summary: str = ""
    attempt: ProviderAttemptData | None = None
