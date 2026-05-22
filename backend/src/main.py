import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config.settings import Settings, get_settings
from src.routes.api import api_router
from src.services.evidence_merge_service import EvidenceMergeService
from src.services.chat_session_store_factory import build_chat_session_store
from src.services.context_query_rewriter_service import ContextQueryRewriterService
from src.services.audit_log_store import AuditLogStore
from src.services.auth_service import AuthService
from src.services.article_asset_service import ArticleAssetService
from src.services.article_extractor_service import ArticleExtractorService
from src.services.article_fetcher_service import ArticleFetcherService
from src.services.article_prompt_service import ArticlePromptService
from src.services.article_translation_service import ArticleTranslationService
from src.services.key_store import TavilyKeyStore
from src.services.llm_runtime_store import LlmRuntimeStore
from src.services.llm_summary_service import LlmSummaryService
from src.services.query_analyst_service import QueryAnalystService
from src.services.query_planner_service import QueryPlannerService
from src.services.query_cache import QueryCache
from src.services.search_orchestrator import SearchOrchestrator
from src.services.searxng_service import SearxngSearchService
from src.services.tavily_service import TavilySearchService
from src.services.ninerouter_gemini_article_provider import NineRouterOpenAIArticleProvider
from src.services.wordpress_draft_builder import WordPressDraftBuilder
from src.services.wordpress_automation_service import WordPressAutomationService
from src.utils.response import utc_now_iso

logger = logging.getLogger(__name__)


def build_services(settings: Settings) -> dict:
    key_store = TavilyKeyStore(file_path=settings.tavily_key_store_path)
    chat_session_store = build_chat_session_store(settings=settings)
    print(
        "[startup] session_store_backend=",
        settings.session_store_backend,
        "database_url=",
        settings.database_url,
        "store_type=",
        type(chat_session_store).__name__,
        flush=True,
    )
    audit_log_store = AuditLogStore(file_path=settings.audit_log_store_path)
    auth_service = AuthService(file_path=settings.auth_store_path, secret=settings.auth_token_secret)
    article_fetcher_service = ArticleFetcherService(settings=settings)
    article_extractor_service = ArticleExtractorService()
    article_asset_service = ArticleAssetService(settings=settings)
    article_prompt_service = ArticlePromptService()
    article_llm_provider = NineRouterOpenAIArticleProvider(settings=settings)
    article_translation_service = ArticleTranslationService(
        settings=settings,
        prompt_service=article_prompt_service,
        provider=article_llm_provider,
    )
    wordpress_draft_builder = WordPressDraftBuilder()
    wordpress_automation_service = WordPressAutomationService(settings=settings)
    llm_runtime_store = LlmRuntimeStore(
        settings=settings,
        file_path=settings.llm_runtime_store_path,
    )
    query_cache = QueryCache(ttl_seconds=settings.result_cache_ttl_seconds)
    tavily_service = TavilySearchService(settings=settings, key_store=key_store)
    searxng_service = SearxngSearchService(settings=settings)
    query_analyst_service = QueryAnalystService(settings=settings)
    query_planner_service = QueryPlannerService(settings=settings)
    evidence_merge_service = EvidenceMergeService()
    llm_summary_service = LlmSummaryService(settings=settings, runtime_store=llm_runtime_store)
    context_query_rewriter_service = ContextQueryRewriterService(
        settings=settings,
        runtime_store=llm_runtime_store,
    )
    orchestrator = SearchOrchestrator(
        settings=settings,
        query_analyst_service=query_analyst_service,
        query_planner_service=query_planner_service,
        evidence_merge_service=evidence_merge_service,
        tavily_service=tavily_service,
        searxng_service=searxng_service,
        llm_summary_service=llm_summary_service,
        query_cache=query_cache,
    )

    return {
        "key_store": key_store,
        "chat_session_store": chat_session_store,
        "query_cache": query_cache,
        "llm_runtime_store": llm_runtime_store,
        "audit_log_store": audit_log_store,
        "auth_service": auth_service,
        "article_fetcher_service": article_fetcher_service,
        "article_extractor_service": article_extractor_service,
        "article_asset_service": article_asset_service,
        "article_prompt_service": article_prompt_service,
        "article_llm_provider": article_llm_provider,
        "article_translation_service": article_translation_service,
        "wordpress_draft_builder": wordpress_draft_builder,
        "wordpress_automation_service": wordpress_automation_service,
        "tavily_service": tavily_service,
        "searxng_service": searxng_service,
        "query_analyst_service": query_analyst_service,
        "query_planner_service": query_planner_service,
        "evidence_merge_service": evidence_merge_service,
        "llm_summary_service": llm_summary_service,
        "context_query_rewriter_service": context_query_rewriter_service,
        "orchestrator": orchestrator,
    }


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.services = build_services(settings)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request payload",
                    "details": {"errors": exc.errors()},
                },
                "meta": {
                    "timestamp": utc_now_iso(),
                    "request_id": request.headers.get("X-Request-Id"),
                },
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                    "details": None,
                },
                "meta": {
                    "timestamp": utc_now_iso(),
                    "request_id": request.headers.get("X-Request-Id"),
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                    "details": None,
                },
                "meta": {
                    "timestamp": utc_now_iso(),
                    "request_id": request.headers.get("X-Request-Id"),
                },
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Unexpected server error",
                    "details": {"error": str(exc)},
                },
                "meta": {
                    "timestamp": utc_now_iso(),
                    "request_id": request.headers.get("X-Request-Id"),
                },
            },
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
