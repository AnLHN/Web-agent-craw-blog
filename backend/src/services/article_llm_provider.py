from dataclasses import dataclass, field
from typing import Any, Protocol

from src.models.article_schemas import ArticleBlock, ArticleSourceInfo


@dataclass(frozen=True)
class ArticleTranslationRequest:
    source: ArticleSourceInfo
    blocks: list[ArticleBlock]
    target_language: str
    glossary: list[dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""


@dataclass(frozen=True)
class ArticleTranslationResult:
    payload: dict[str, Any]
    provider: str
    model: str


class ArticleLlmProvider(Protocol):
    async def translate_blocks(self, request: ArticleTranslationRequest) -> ArticleTranslationResult:
        ...
