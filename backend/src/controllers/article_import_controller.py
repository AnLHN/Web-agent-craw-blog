import json
import asyncio
import ipaddress
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Request, status

from src.models.article_schemas import (
    ArticleDraftAttribution,
    ArticleDraftPreview,
    ArticleImportData,
    ArticleImportRequest,
    ArticleImportResponse,
    ArticleImportRun,
    ArticleImportStatus,
    ArticleLlmHealthData,
    ArticleLlmHealthResponse,
    ArticleSourceInfo,
    ArticleStorageManifest,
)
from src.models.schemas import ErrorInfo
from src.services.article_fetcher_service import ArticleFetchError
from src.utils.feature_flags import feature_enabled
from src.utils.response import response_meta
from src.utils.security import current_role

router = APIRouter()

RUN_ID_PATTERN = re.compile(r"^air_[a-f0-9]{32}$")


def _storage_manifest(settings, run_id: str) -> ArticleStorageManifest:
    storage_root = Path(settings.article_import_storage_path)
    run_dir = storage_root / run_id
    return ArticleStorageManifest(
        run_dir=str(run_dir),
        raw_snapshot_path=str(run_dir / "raw.html"),
        extracted_json_path=str(run_dir / "extracted.json"),
        draft_json_path=str(run_dir / "draft.json"),
        assets_dir=str(run_dir / "assets"),
    )


def _feature_disabled_response() -> ArticleImportResponse:
    return ArticleImportResponse(
        success=False,
        data=None,
        error=ErrorInfo(code="FEATURE_DISABLED", message="Article Import feature is disabled", details=None),
        meta=response_meta(),
    )


def _not_implemented_response(action: str, run_id: str) -> ArticleImportResponse:
    return ArticleImportResponse(
        success=False,
        data=None,
        error=ErrorInfo(
            code="ARTICLE_IMPORT_PHASE_NOT_IMPLEMENTED",
            message=f"Article import action '{action}' is not implemented in Phase H",
            details={"run_id": run_id, "phase": "H"},
        ),
        meta=response_meta(),
    )


def _run_json_path(run: ArticleImportRun) -> Path:
    return Path(run.storage.run_dir) / "run.json"


def _run_json_path_for_id(settings, run_id: str) -> Path:
    return Path(settings.article_import_storage_path) / run_id / "run.json"


def _persist_run(run: ArticleImportRun) -> None:
    path = _run_json_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _load_run(settings, run_id: str) -> ArticleImportRun | None:
    if not RUN_ID_PATTERN.match(run_id):
        return None
    path = _run_json_path_for_id(settings=settings, run_id=run_id)
    if not path.exists():
        return None
    return ArticleImportRun(**json.loads(path.read_text(encoding="utf-8")))


def _not_found_response(run_id: str) -> ArticleImportResponse:
    return ArticleImportResponse(
        success=False,
        data=None,
        error=ErrorInfo(
            code="ARTICLE_IMPORT_NOT_FOUND",
            message="Article import run not found",
            details={"run_id": run_id},
        ),
        meta=response_meta(),
    )


def _audit(request: Request, action: str, status_value: str, details: dict) -> None:
    audit_log_store = request.app.state.services.get("audit_log_store")
    if not audit_log_store:
        return
    audit_log_store.append(
        {
            "actor_role": current_role(request),
            "action": action,
            "path": str(request.url.path),
            "method": request.method,
            "status": status_value,
            "details": details,
        }
    )


def _blocked_url_reason(settings, url: str) -> str | None:
    if settings.article_allow_private_urls:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "unsupported_scheme"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "missing_host"
    if host == "localhost" or host.endswith(".localhost"):
        return "localhost_blocked"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        return "private_ip_blocked"
    return None


def _blocked_url_response(url: str, reason: str) -> ArticleImportResponse:
    return ArticleImportResponse(
        success=False,
        data=None,
        error=ErrorInfo(
            code="ARTICLE_URL_BLOCKED",
            message="Article URL is blocked by import safety policy",
            details={"url": url, "reason": reason},
        ),
        meta=response_meta(),
    )


def _internal_error_response(run: ArticleImportRun, code: str, message: str, exc: Exception) -> ArticleImportResponse:
    run.status = ArticleImportStatus.FAILED
    run.error_message = str(exc)
    run.updated_at = datetime.now(timezone.utc)
    return ArticleImportResponse(
        success=False,
        data=ArticleImportData(run=run),
        error=ErrorInfo(
            code=code,
            message=message,
            details={"error": str(exc), "run_id": run.id},
        ),
        meta=response_meta(),
    )


def _persist_article_artifacts(run: ArticleImportRun, html: str) -> None:
    run_dir = Path(run.storage.run_dir)
    assets_dir = Path(run.storage.assets_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    Path(run.storage.raw_snapshot_path).write_text(html, encoding="utf-8")
    extracted_payload = {
        "source": run.source.model_dump(mode="json"),
        "blocks": [block.model_dump(mode="json") for block in run.blocks],
        "assets": [asset.model_dump(mode="json") for asset in run.assets],
    }
    Path(run.storage.extracted_json_path).write_text(
        json.dumps(extracted_payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    if run.draft:
        Path(run.storage.draft_json_path).write_text(
            json.dumps(run.draft.model_dump(mode="json"), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    _persist_run(run)


def _set_progress(run: ArticleImportRun, *, pct: int, stage: str, message: str, in_progress: bool = True) -> None:
    run.metadata["import_progress_pct"] = max(0, min(100, int(pct)))
    run.metadata["import_progress_stage"] = stage
    run.metadata["import_progress_message"] = message
    run.metadata["import_in_progress"] = in_progress
    run.updated_at = datetime.now(timezone.utc)


def _translation_completion_pct(run: ArticleImportRun) -> int:
    text_blocks = [
        block for block in run.blocks if block.block_type.value not in {"image", "unknown"}
    ]
    if not text_blocks:
        return 100
    translated = [block for block in text_blocks if (block.translated_text or "").strip()]
    return int((len(translated) / len(text_blocks)) * 100)


async def _run_import_pipeline(request: Request, run_id: str, source_url: str) -> None:
    settings = request.app.state.settings
    article_fetcher = request.app.state.services["article_fetcher_service"]
    article_extractor = request.app.state.services["article_extractor_service"]
    article_asset_service = request.app.state.services["article_asset_service"]
    article_translation_service = request.app.state.services["article_translation_service"]
    wordpress_draft_builder = request.app.state.services["wordpress_draft_builder"]

    run = _load_run(settings=settings, run_id=run_id)
    if not run:
        return

    try:
        _set_progress(run, pct=8, stage="fetch", message="Fetching article HTML...")
        _persist_run(run)
        fetch_result = await article_fetcher.fetch(source_url)

        _set_progress(run, pct=26, stage="extract", message="Extracting text blocks and media...")
        _persist_run(run)
        extraction = article_extractor.extract(html=fetch_result.html, source_url=fetch_result.final_url)

        run.source = extraction.source
        if run.draft and run.draft.source_attribution:
            run.draft.source_attribution.url = extraction.source.url
            run.draft.source_attribution.title = extraction.source.title
            run.draft.source_attribution.domain = extraction.source.domain
        run.blocks = extraction.blocks

        _set_progress(run, pct=44, stage="assets", message="Downloading images/assets...")
        _persist_run(run)
        run.assets = await article_asset_service.download_assets(
            assets=extraction.assets,
            assets_dir=run.storage.assets_dir,
        )
        run.status = ArticleImportStatus.EXTRACTED
        run.metadata.update(
            {
                "fetch_status_code": fetch_result.status_code,
                "fetch_content_type": fetch_result.content_type,
                "block_count": len(run.blocks),
                "asset_count": len(run.assets),
                "asset_downloaded_count": sum(1 for asset in run.assets if asset.download_status == "downloaded"),
                "asset_failed_count": sum(1 for asset in run.assets if asset.download_status == "failed"),
                "asset_skipped_count": sum(1 for asset in run.assets if asset.download_status == "skipped"),
            }
        )
        _set_progress(run, pct=58, stage="translate", message="Translating article blocks...")
        _persist_run(run)
        base_pct = _translation_completion_pct(run)
        progress_span = max(1, 96 - base_pct)

        def on_batch_progress(done_batches: int, total_batches: int) -> None:
            if total_batches <= 0:
                return
            pct = base_pct + int((done_batches / total_batches) * progress_span)
            _set_progress(
                run,
                pct=pct,
                stage="translate",
                message=f"Translating blocks ({done_batches}/{total_batches})...",
            )
            _persist_run(run)

        translation_outcome = await article_translation_service.translate_run(
            run,
            on_batch_progress=on_batch_progress,
        )
        run.metadata["translation_status"] = translation_outcome.status
        run.metadata["translation_warning_count"] = len(translation_outcome.warnings)

        _set_progress(run, pct=94, stage="draft", message="Building WordPress draft...")
        run.draft = wordpress_draft_builder.build(run)
        run.status = ArticleImportStatus.DRAFT_READY
        run.metadata["draft_status"] = "ready"
        run.metadata["draft_content_format"] = run.draft.content_format
        _persist_article_artifacts(run=run, html=fetch_result.html)

        if translation_outcome.status == "partial":
            _set_progress(
                run,
                pct=max(_translation_completion_pct(run), 1),
                stage="paused",
                message="Translation paused. Press Translate to continue.",
                in_progress=False,
            )
        elif translation_outcome.status == "failed":
            _set_progress(
                run,
                pct=100,
                stage="failed",
                message="Translation failed. Retry after a short wait.",
                in_progress=False,
            )
        else:
            _set_progress(run, pct=100, stage="done", message="Draft ready.", in_progress=False)
        _persist_run(run)
        _audit(
            request=request,
            action="article_import_create",
            status_value="success",
            details={
                "run_id": run.id,
                "url": source_url,
                "status": run.status,
                "block_count": len(run.blocks),
                "asset_count": len(run.assets),
                "translation_status": run.metadata.get("translation_status"),
            },
        )
    except Exception as exc:
        run.status = ArticleImportStatus.FAILED
        run.error_message = str(exc)
        _set_progress(run, pct=100, stage="failed", message="Import failed.", in_progress=False)
        _persist_run(run)
        _audit(
            request=request,
            action="article_import_create",
            status_value="failed",
            details={"run_id": run.id, "url": source_url, "stage": "pipeline", "error": str(exc)},
        )


@router.post(
    "/articles/import",
    response_model=ArticleImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_article_import(payload: ArticleImportRequest, request: Request) -> ArticleImportResponse:
    if not feature_enabled(request, "feature_article_import"):
        return _feature_disabled_response()

    settings = request.app.state.settings
    article_fetcher = request.app.state.services["article_fetcher_service"]
    article_extractor = request.app.state.services["article_extractor_service"]
    article_asset_service = request.app.state.services["article_asset_service"]
    article_translation_service = request.app.state.services["article_translation_service"]
    wordpress_draft_builder = request.app.state.services["wordpress_draft_builder"]
    run_id = f"air_{uuid4().hex}"
    now = datetime.now(timezone.utc)
    source_url = str(payload.url)
    blocked_reason = _blocked_url_reason(settings=settings, url=source_url)
    if blocked_reason:
        _audit(
            request=request,
            action="article_import_create",
            status_value="blocked",
            details={"url": source_url, "reason": blocked_reason},
        )
        return _blocked_url_response(url=source_url, reason=blocked_reason)

    parsed = urlparse(source_url)
    source = ArticleSourceInfo(url=source_url, domain=parsed.netloc)
    draft = None
    if payload.mode.value == "draft":
        draft = ArticleDraftPreview(
            source_attribution=ArticleDraftAttribution(
                url=source_url,
                title=None,
                domain=parsed.netloc,
            )
        )
    run = ArticleImportRun(
        id=run_id,
        status=ArticleImportStatus.QUEUED,
        mode=payload.mode,
        target_language=payload.target_language,
        source=source,
        storage=_storage_manifest(settings=settings, run_id=run_id),
        draft=draft,
        created_at=now,
        updated_at=now,
        metadata={
            "contract_version": "article_import.phase_h",
            "glossary_key": payload.glossary_key,
            "wordpress_target_url": str(payload.wordpress_target_url) if payload.wordpress_target_url else None,
            "llm_provider": settings.article_llm_provider,
            "article_model": settings.article_openai_model,
            "import_progress_pct": 0,
            "import_progress_stage": "queued",
            "import_progress_message": "Queued",
            "import_in_progress": False,
        },
    )
    _persist_run(run)

    if payload.async_mode:
        run.status = ArticleImportStatus.QUEUED
        _set_progress(run, pct=3, stage="queued", message="Queued. Starting import...", in_progress=True)
        _persist_run(run)
        asyncio.create_task(_run_import_pipeline(request=request, run_id=run.id, source_url=source_url))
        return ArticleImportResponse(
            success=True,
            data=ArticleImportData(run=run),
            error=None,
            meta=response_meta(),
        )

    try:
        fetch_result = await article_fetcher.fetch(source_url)
        extraction = article_extractor.extract(html=fetch_result.html, source_url=fetch_result.final_url)
    except ArticleFetchError as exc:
        run.status = ArticleImportStatus.FAILED
        run.error_message = str(exc)
        run.updated_at = datetime.now(timezone.utc)
        run.metadata["import_progress_pct"] = 100
        run.metadata["import_progress_stage"] = "failed"
        run.metadata["import_progress_message"] = "Fetch failed."
        run.metadata["import_in_progress"] = False
        _audit(
            request=request,
            action="article_import_create",
            status_value="failed",
            details={"run_id": run.id, "url": source_url, "stage": "fetch", "error": str(exc)},
        )
        return ArticleImportResponse(
            success=False,
            data=ArticleImportData(run=run),
            error=ErrorInfo(
                code="ARTICLE_FETCH_FAILED",
                message="Article fetch failed",
                details={"error": str(exc), "url": source_url},
            ),
            meta=response_meta(),
        )
    except Exception as exc:
        run.status = ArticleImportStatus.FAILED
        run.error_message = str(exc)
        run.updated_at = datetime.now(timezone.utc)
        run.metadata["import_progress_pct"] = 100
        run.metadata["import_progress_stage"] = "failed"
        run.metadata["import_progress_message"] = "Extraction failed."
        run.metadata["import_in_progress"] = False
        _audit(
            request=request,
            action="article_import_create",
            status_value="failed",
            details={"run_id": run.id, "url": source_url, "stage": "extract", "error": str(exc)},
        )
        return ArticleImportResponse(
            success=False,
            data=ArticleImportData(run=run),
            error=ErrorInfo(
                code="ARTICLE_EXTRACT_FAILED",
                message="Article extraction failed",
                details={"error": str(exc), "url": source_url},
            ),
            meta=response_meta(),
        )

    try:
        run.source = extraction.source
        if run.draft and run.draft.source_attribution:
            run.draft.source_attribution.url = extraction.source.url
            run.draft.source_attribution.title = extraction.source.title
            run.draft.source_attribution.domain = extraction.source.domain
        run.blocks = extraction.blocks
        run.assets = await article_asset_service.download_assets(
            assets=extraction.assets,
            assets_dir=run.storage.assets_dir,
        )
        run.status = ArticleImportStatus.EXTRACTED
        run.updated_at = datetime.now(timezone.utc)
        run.metadata["import_progress_pct"] = 62
        run.metadata["import_progress_stage"] = "translate"
        run.metadata["import_progress_message"] = "Translating article blocks..."
        run.metadata["import_in_progress"] = True
        run.metadata.update(
            {
                "fetch_status_code": fetch_result.status_code,
                "fetch_content_type": fetch_result.content_type,
                "block_count": len(run.blocks),
                "asset_count": len(run.assets),
                "asset_downloaded_count": sum(1 for asset in run.assets if asset.download_status == "downloaded"),
                "asset_failed_count": sum(1 for asset in run.assets if asset.download_status == "failed"),
                "asset_skipped_count": sum(1 for asset in run.assets if asset.download_status == "skipped"),
            }
        )
        translation_outcome = await article_translation_service.translate_run(run)
        run.metadata["translation_status"] = translation_outcome.status
        run.metadata["translation_warning_count"] = len(translation_outcome.warnings)
        run.draft = wordpress_draft_builder.build(run)
        run.status = ArticleImportStatus.DRAFT_READY
        run.metadata["draft_status"] = "ready"
        run.metadata["draft_content_format"] = run.draft.content_format
        run.metadata["import_progress_pct"] = 100
        if translation_outcome.status == "partial":
            run.metadata["import_progress_stage"] = "paused"
            run.metadata["import_progress_message"] = "Translation paused. Press Translate to continue."
        elif translation_outcome.status == "failed":
            run.metadata["import_progress_stage"] = "failed"
            run.metadata["import_progress_message"] = "Translation failed. Retry after a short wait."
        else:
            run.metadata["import_progress_stage"] = "done"
            run.metadata["import_progress_message"] = "Draft ready."
        run.metadata["import_in_progress"] = False
        run.updated_at = datetime.now(timezone.utc)
        _persist_article_artifacts(run=run, html=fetch_result.html)
    except Exception as exc:
        _audit(
            request=request,
            action="article_import_create",
            status_value="failed",
            details={"run_id": run.id, "url": source_url, "stage": "pipeline", "error": str(exc)},
        )
        return _internal_error_response(
            run=run,
            code="ARTICLE_IMPORT_PIPELINE_FAILED",
            message="Article import pipeline failed",
            exc=exc,
        )
    _audit(
        request=request,
        action="article_import_create",
        status_value="success",
        details={
            "run_id": run.id,
            "url": source_url,
            "status": run.status,
            "block_count": len(run.blocks),
            "asset_count": len(run.assets),
            "translation_status": run.metadata.get("translation_status"),
        },
    )
    return ArticleImportResponse(
        success=True,
        data=ArticleImportData(run=run),
        error=None,
        meta=response_meta(),
    )


@router.post("/articles/import/llm/health", response_model=ArticleLlmHealthResponse)
async def check_article_import_llm_health(request: Request) -> ArticleLlmHealthResponse:
    if not feature_enabled(request, "feature_article_import"):
        return ArticleLlmHealthResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Article Import feature is disabled", details=None),
            meta=response_meta(),
        )
    provider = request.app.state.services["article_llm_provider"]
    health = await provider.check_health()
    return ArticleLlmHealthResponse(
        success=bool(health.get("ok")),
        data=ArticleLlmHealthData(**health),
        error=None
        if health.get("ok")
        else ErrorInfo(
            code="ARTICLE_LLM_HEALTH_FAILED",
            message=str(health.get("message") or "Article LLM health check failed"),
            details={"status": health.get("status"), "configured": health.get("configured")},
        ),
        meta=response_meta(),
    )


@router.get("/articles/import/{run_id}", response_model=ArticleImportResponse)
async def get_article_import(run_id: str, request: Request) -> ArticleImportResponse:
    if not feature_enabled(request, "feature_article_import"):
        return _feature_disabled_response()
    run = _load_run(settings=request.app.state.settings, run_id=run_id)
    if not run:
        return _not_found_response(run_id)
    return ArticleImportResponse(
        success=True,
        data=ArticleImportData(run=run),
        error=None,
        meta=response_meta(),
    )


@router.post("/articles/import/{run_id}/translate", response_model=ArticleImportResponse)
async def translate_article_import(run_id: str, request: Request) -> ArticleImportResponse:
    if not feature_enabled(request, "feature_article_import"):
        return _feature_disabled_response()
    run = _load_run(settings=request.app.state.settings, run_id=run_id)
    if not run:
        return _not_found_response(run_id)
    article_translation_service = request.app.state.services["article_translation_service"]
    wordpress_draft_builder = request.app.state.services["wordpress_draft_builder"]
    try:
        _set_progress(run, pct=max(_translation_completion_pct(run), 1), stage="translate", message="Translating article blocks...", in_progress=True)
        _persist_run(run)
        base_pct = _translation_completion_pct(run)
        progress_span = max(1, 96 - base_pct)

        def on_batch_progress(done_batches: int, total_batches: int) -> None:
            if total_batches <= 0:
                return
            pct = base_pct + int((done_batches / total_batches) * progress_span)
            _set_progress(
                run,
                pct=pct,
                stage="translate",
                message=f"Translating blocks ({done_batches}/{total_batches})...",
                in_progress=True,
            )
            _persist_run(run)

        translation_outcome = await article_translation_service.translate_run(
            run,
            on_batch_progress=on_batch_progress,
        )
        run.metadata["translation_status"] = translation_outcome.status
        run.metadata["translation_warning_count"] = len(translation_outcome.warnings)
        if translation_outcome.error:
            run.metadata["translation_error"] = translation_outcome.error
        else:
            run.metadata.pop("translation_error", None)
        run.draft = wordpress_draft_builder.build(run)
        run.status = ArticleImportStatus.DRAFT_READY
        run.metadata["draft_status"] = "ready"
        run.metadata["draft_content_format"] = run.draft.content_format
        if translation_outcome.status == "partial":
            run.metadata["import_progress_pct"] = max(_translation_completion_pct(run), 1)
            run.metadata["import_progress_stage"] = "paused"
            run.metadata["import_progress_message"] = "Translation paused. Press Translate to continue."
            run.metadata["import_in_progress"] = False
        elif translation_outcome.status == "failed":
            run.metadata["import_progress_pct"] = max(_translation_completion_pct(run), 1)
            run.metadata["import_progress_stage"] = "failed"
            run.metadata["import_progress_message"] = "Translation failed. Retry after a short wait."
            run.metadata["import_in_progress"] = False
        else:
            run.metadata["import_progress_pct"] = 100
            run.metadata["import_progress_stage"] = "done"
            run.metadata["import_progress_message"] = "Draft ready."
            run.metadata["import_in_progress"] = False
        run.updated_at = datetime.now(timezone.utc)
        _persist_run(run)
        if run.draft:
            Path(run.storage.draft_json_path).write_text(
                json.dumps(run.draft.model_dump(mode="json"), ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        _audit(
            request=request,
            action="article_import_translate",
            status_value="failed",
            details={"run_id": run_id, "translation_status": "failed", "error": str(exc)},
        )
        return _internal_error_response(
            run=run,
            code="ARTICLE_TRANSLATION_PIPELINE_FAILED",
            message="Article translation pipeline failed",
            exc=exc,
        )
    _audit(
        request=request,
        action="article_import_translate",
        status_value="success" if translation_outcome.status == "translated" else "failed",
        details={"run_id": run_id, "translation_status": translation_outcome.status},
    )
    return ArticleImportResponse(success=True, data=ArticleImportData(run=run), error=None, meta=response_meta())


@router.post("/articles/import/{run_id}/wordpress/dry-run", response_model=ArticleImportResponse)
async def dry_run_wordpress_article_import(run_id: str, request: Request) -> ArticleImportResponse:
    if not feature_enabled(request, "feature_article_import"):
        return _feature_disabled_response()
    run = _load_run(settings=request.app.state.settings, run_id=run_id)
    if not run:
        return _not_found_response(run_id)
    wordpress_automation = request.app.state.services["wordpress_automation_service"]
    try:
        result = await wordpress_automation.dry_run()
        run.metadata["wordpress_dry_run_status"] = result.status
        run.metadata["wordpress_dry_run_message"] = result.message
        if result.page_url:
            run.metadata["wordpress_page_url"] = result.page_url
        run.updated_at = datetime.now(timezone.utc)
        _persist_run(run)
    except Exception as exc:
        _audit(
            request=request,
            action="article_import_wordpress_dry_run",
            status_value="failed",
            details={"run_id": run_id, "status": "failed", "message": str(exc)},
        )
        return _internal_error_response(
            run=run,
            code="WORDPRESS_DRY_RUN_PIPELINE_FAILED",
            message="WordPress dry-run pipeline failed",
            exc=exc,
        )
    _audit(
        request=request,
        action="article_import_wordpress_dry_run",
        status_value="success" if result.ok else "failed",
        details={"run_id": run_id, "status": result.status, "message": result.message},
    )
    if not result.ok:
        return ArticleImportResponse(
            success=False,
            data=ArticleImportData(run=run),
            error=ErrorInfo(
                code="WORDPRESS_DRY_RUN_FAILED",
                message="WordPress dry-run failed",
                details={"status": result.status, "message": result.message},
            ),
            meta=response_meta(),
        )
    return ArticleImportResponse(success=True, data=ArticleImportData(run=run), error=None, meta=response_meta())


@router.post("/articles/import/{run_id}/wordpress/paste", response_model=ArticleImportResponse)
async def paste_wordpress_article_import(run_id: str, request: Request) -> ArticleImportResponse:
    if not feature_enabled(request, "feature_article_import"):
        return _feature_disabled_response()
    run = _load_run(settings=request.app.state.settings, run_id=run_id)
    if not run:
        return _not_found_response(run_id)
    if not run.draft or not run.draft.content:
        _audit(
            request=request,
            action="article_import_wordpress_paste",
            status_value="failed",
            details={"run_id": run_id, "reason": "draft_not_ready"},
        )
        return ArticleImportResponse(
            success=False,
            data=ArticleImportData(run=run),
            error=ErrorInfo(
                code="WORDPRESS_DRAFT_NOT_READY",
                message="Draft content is not ready for WordPress paste",
                details={"run_id": run_id},
            ),
            meta=response_meta(),
        )
    wordpress_automation = request.app.state.services["wordpress_automation_service"]
    try:
        result = await wordpress_automation.paste_draft(title=run.draft.title or run.source.title or "", content=run.draft.content)
        run.metadata["wordpress_paste_status"] = result.status
        run.metadata["wordpress_paste_message"] = result.message
        if result.page_url:
            run.metadata["wordpress_page_url"] = result.page_url
        if result.ok:
            run.status = ArticleImportStatus.PASTED
        run.updated_at = datetime.now(timezone.utc)
        _persist_run(run)
    except Exception as exc:
        _audit(
            request=request,
            action="article_import_wordpress_paste",
            status_value="failed",
            details={"run_id": run_id, "status": "failed", "message": str(exc)},
        )
        return _internal_error_response(
            run=run,
            code="WORDPRESS_PASTE_PIPELINE_FAILED",
            message="WordPress paste pipeline failed",
            exc=exc,
        )
    _audit(
        request=request,
        action="article_import_wordpress_paste",
        status_value="success" if result.ok else "failed",
        details={"run_id": run_id, "status": result.status, "message": result.message},
    )
    if not result.ok:
        return ArticleImportResponse(
            success=False,
            data=ArticleImportData(run=run),
            error=ErrorInfo(
                code="WORDPRESS_PASTE_FAILED",
                message="WordPress paste failed",
                details={"status": result.status, "message": result.message},
            ),
            meta=response_meta(),
        )
    return ArticleImportResponse(success=True, data=ArticleImportData(run=run), error=None, meta=response_meta())
