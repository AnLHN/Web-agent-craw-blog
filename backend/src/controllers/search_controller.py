from fastapi import APIRouter, HTTPException, Request, status

from src.models.schemas import (
    ErrorInfo,
    HealthData,
    HealthResponse,
    KeyCreateRequest,
    KeyInfo,
    SearchRequest,
    SearchResponse,
    TavilyKeysData,
    TavilyKeysResponse,
)
from src.services.key_store import mask_key
from src.utils.response import response_meta

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        success=True,
        data=HealthData(status="ok", service="web-search-backend", version="0.1.0"),
        error=None,
        meta=response_meta(),
    )


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    orchestrator = request.app.state.services["orchestrator"]
    try:
        result = await orchestrator.search(query=payload.query, top_k=payload.top_k)
        return SearchResponse(success=True, data=result, error=None, meta=response_meta())
    except Exception as exc:
        return SearchResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="SEARCH_FAILED", message="Search pipeline failed", details={"error": str(exc)}),
            meta=response_meta(),
        )


@router.get("/keys/tavily", response_model=TavilyKeysResponse)
async def list_tavily_keys(request: Request) -> TavilyKeysResponse:
    key_store = request.app.state.services["key_store"]
    records = key_store.list_records()
    keys = [
        KeyInfo(
            id=record.id,
            label=record.label,
            masked_key=mask_key(record.api_key),
            status=record.status,
            success_rate_5m=record.success_rate_5m,
            last_used_at=record.last_used_at,
            cooldown_until=record.cooldown_until,
        )
        for record in records
    ]
    return TavilyKeysResponse(success=True, data=TavilyKeysData(keys=keys), error=None, meta=response_meta())


@router.post("/keys/tavily", response_model=TavilyKeysResponse, status_code=status.HTTP_201_CREATED)
async def add_tavily_key(payload: KeyCreateRequest, request: Request) -> TavilyKeysResponse:
    key_store = request.app.state.services["key_store"]
    try:
        key_store.add_key(api_key=payload.api_key, label=payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    records = key_store.list_records()
    keys = [
        KeyInfo(
            id=record.id,
            label=record.label,
            masked_key=mask_key(record.api_key),
            status=record.status,
            success_rate_5m=record.success_rate_5m,
            last_used_at=record.last_used_at,
            cooldown_until=record.cooldown_until,
        )
        for record in records
    ]

    return TavilyKeysResponse(success=True, data=TavilyKeysData(keys=keys), error=None, meta=response_meta())


@router.delete("/keys/tavily/{key_id}", response_model=TavilyKeysResponse)
async def delete_tavily_key(key_id: str, request: Request) -> TavilyKeysResponse:
    key_store = request.app.state.services["key_store"]
    deleted = key_store.delete_key(key_id)

    if not deleted:
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="KEY_NOT_FOUND", message="Tavily key not found", details={"key_id": key_id}),
            meta=response_meta(),
        )

    records = key_store.list_records()
    keys = [
        KeyInfo(
            id=record.id,
            label=record.label,
            masked_key=mask_key(record.api_key),
            status=record.status,
            success_rate_5m=record.success_rate_5m,
            last_used_at=record.last_used_at,
            cooldown_until=record.cooldown_until,
        )
        for record in records
    ]

    return TavilyKeysResponse(success=True, data=TavilyKeysData(keys=keys), error=None, meta=response_meta())
