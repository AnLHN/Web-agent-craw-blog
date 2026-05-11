from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    tavily_search_depth: str = "advanced"
    tavily_max_cooldown_seconds: int = 600

    tavily_key_store_path: str = "config/tavily_keys.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
