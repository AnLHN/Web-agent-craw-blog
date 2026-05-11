from dataclasses import dataclass, field

from src.models.schemas import SourceItem


@dataclass
class ProviderAttemptData:
    provider: str
    status: str
    reason: str
    latency_ms: int
    result_count: int


@dataclass
class ProviderSearchResult:
    provider: str
    sources: list[SourceItem] = field(default_factory=list)
    attempts: list[ProviderAttemptData] = field(default_factory=list)
