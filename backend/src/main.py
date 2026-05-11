from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config.settings import Settings, get_settings
from src.routes.api import api_router
from src.services.key_store import TavilyKeyStore
from src.services.query_cache import QueryCache
from src.services.search_orchestrator import SearchOrchestrator
from src.services.searxng_service import SearxngSearchService
from src.services.tavily_service import TavilySearchService
from src.utils.response import utc_now_iso


def build_services(settings: Settings) -> dict:
    key_store = TavilyKeyStore(file_path=settings.tavily_key_store_path)
    query_cache = QueryCache(ttl_seconds=settings.result_cache_ttl_seconds)
    tavily_service = TavilySearchService(settings=settings, key_store=key_store)
    searxng_service = SearxngSearchService(settings=settings)
    orchestrator = SearchOrchestrator(
        settings=settings,
        tavily_service=tavily_service,
        searxng_service=searxng_service,
        query_cache=query_cache,
    )

    return {
        "key_store": key_store,
        "query_cache": query_cache,
        "tavily_service": tavily_service,
        "searxng_service": searxng_service,
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
