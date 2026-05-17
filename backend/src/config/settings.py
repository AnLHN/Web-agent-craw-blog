from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    app_name: str = "Web Search API"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    request_timeout_seconds: float = 12.0
    quality_min_results: int = 3
    quality_min_unique_domains: int = 2
    result_cache_ttl_seconds: int = 300

    searxng_base_url: str = "https://searx.be"
    searxng_backup_base_urls: str = "https://search.bus-hit.me,https://searx.tiekoetter.com"
    searxng_categories: str = "general"
    searxng_max_qps: float = 1.5
    searxng_circuit_fail_threshold: int = 3
    searxng_circuit_open_seconds: int = 120
    force_searxng_test_mode: bool = False

    tavily_search_depth: str = "advanced"
    tavily_max_cooldown_seconds: int = 600

    llm_enabled: bool = True
    llm_base_url: str = "http://localhost:8007/v1"
    llm_model: str = "google/gemma-4-E4B-it"
    llm_temperature: float = 0.2
    llm_max_tokens: Optional[int] = None
    llm_summary_max_chars: int = 512
    llm_summary_system_prompt: str = (
        "Ban la tro ly tong hop thong tin web chinh xac. "
        "Tra loi ngan gon, ro y, dung du lieu tu nguon. "
        "Khong bịa them thong tin ngoai nguon; neu thieu du lieu thi noi ro."
    )
    query_analyst_mode: str = "rule"

    tavily_key_store_path: str = "config/tavily_keys.json"
    chat_session_store_path: str = "config/chat_sessions.json"
    database_url: str = ""
    session_store_backend: str = "auto"
    session_store_dual_write: bool = False
    llm_runtime_store_path: str = "config/llm_runtime.json"
    audit_log_store_path: str = "config/audit_logs.jsonl"
    chat_session_retention_days: int = 30
    rbac_enabled: bool = False
    rbac_admin_token: str = ""
    feature_session_history: bool = True
    feature_ops_dashboard: bool = True
    feature_llm_runtime_config: bool = True
    pipeline_mode: str = "multi_agent_balanced"
    max_sub_queries: int = 4
    planner_simple_budget: int = 2
    planner_medium_budget: int = 3
    planner_complex_budget: int = 4
    max_parallel_subquery: int = 2
    subquery_timeout_seconds: float = 2.2
    quality_gate_min_coverage_sources: int = 2
    quality_gate_max_extra_rounds: int = 1

    @field_validator("llm_max_tokens", mode="before")
    @classmethod
    def empty_llm_max_tokens_uses_default(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
