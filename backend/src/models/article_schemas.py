from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl

from src.models.schemas import ErrorInfo, ResponseMeta


class ArticleImportStatus(StrEnum):
    QUEUED = "queued"
    FETCHED = "fetched"
    EXTRACTED = "extracted"
    TRANSLATED = "translated"
    DRAFT_READY = "draft_ready"
    PASTED = "pasted"
    FAILED = "failed"


class ArticleImportMode(StrEnum):
    DRAFT = "draft"
    PREVIEW = "preview"


class ArticleBlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    IMAGE = "image"
    CODE = "code"
    TABLE = "table"
    LIST = "list"
    QUOTE = "quote"
    EMBED = "embed"
    UNKNOWN = "unknown"


class ArticleAssetDownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    FAILED = "failed"


class ArticleImportRequest(BaseModel):
    url: HttpUrl
    mode: ArticleImportMode = ArticleImportMode.DRAFT
    target_language: str = Field(default="vi", min_length=2, max_length=12)
    glossary_key: Optional[str] = Field(default=None, max_length=80)
    wordpress_target_url: Optional[HttpUrl] = None
    async_mode: bool = False


class ArticleSourceInfo(BaseModel):
    url: str
    domain: str
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None


class ArticleStorageManifest(BaseModel):
    run_dir: str
    raw_snapshot_path: str
    extracted_json_path: str
    draft_json_path: str
    assets_dir: str


class ArticleAsset(BaseModel):
    id: str
    source_url: str
    local_path: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    checksum: Optional[str] = None
    download_status: ArticleAssetDownloadStatus = ArticleAssetDownloadStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArticleBlock(BaseModel):
    id: str
    order_index: int = Field(ge=0)
    block_type: ArticleBlockType
    source_text: Optional[str] = None
    translated_text: Optional[str] = None
    language_hint: Optional[str] = None
    asset_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArticleDraftAttribution(BaseModel):
    url: str
    title: Optional[str] = None
    domain: str


class ArticleDraftPreview(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content_format: str = "html"
    content: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    source_attribution: Optional[ArticleDraftAttribution] = None


class ArticlePromptUsage(BaseModel):
    prompt_key: str
    version: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None


class ArticleImportRun(BaseModel):
    id: str
    status: ArticleImportStatus
    mode: ArticleImportMode
    target_language: str
    source: ArticleSourceInfo
    storage: ArticleStorageManifest
    blocks: List[ArticleBlock] = Field(default_factory=list)
    assets: List[ArticleAsset] = Field(default_factory=list)
    draft: Optional[ArticleDraftPreview] = None
    prompt_usage: List[ArticlePromptUsage] = Field(default_factory=list)
    wordpress_post_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArticleImportData(BaseModel):
    run: ArticleImportRun


class ArticleLlmHealthData(BaseModel):
    ok: bool
    configured: bool
    status: str
    message: str
    latency_ms: int
    base_url: str
    model: str
    has_api_key: bool


class ArticleLlmHealthResponse(BaseModel):
    success: bool
    data: Optional[ArticleLlmHealthData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class ArticleImportResponse(BaseModel):
    success: bool
    data: Optional[ArticleImportData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class ArticleImportListData(BaseModel):
    runs: List[ArticleImportRun]
    total: int


class ArticleImportListResponse(BaseModel):
    success: bool
    data: Optional[ArticleImportListData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta
