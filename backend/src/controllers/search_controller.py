import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.models.schemas import (
    ErrorInfo,
    HealthData,
    HealthResponse,
    KeyCreateRequest,
    KeyUpdateRequest,
    KeyInfo,
    SearchRequest,
    SearchResponse,
    TavilyKeyMetricsData,
    TavilyKeyMetricsResponse,
    TavilyKeysData,
    TavilyKeysResponse,
)
from src.services.key_store import mask_key
from src.utils.feature_flags import feature_enabled
from src.utils.response import response_meta
from src.utils.security import require_role
from src.utils.text import finalize_summary_for_response

router = APIRouter()


def _key_info(record) -> KeyInfo:
    return KeyInfo(
        id=record.id,
        label=record.label,
        masked_key=mask_key(record.api_key),
        status=record.status,
        success_rate_5m=record.success_rate_5m,
        last_used_at=record.last_used_at,
        cooldown_until=record.cooldown_until,
        success_count=record.success_count,
        failure_count=record.failure_count,
    )


def _keys_response(key_store) -> TavilyKeysResponse:
    keys = [_key_info(record) for record in key_store.list_records()]
    return TavilyKeysResponse(success=True, data=TavilyKeysData(keys=keys), error=None, meta=response_meta())


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _summary_chunks(text: str, chunk_size: int = 80) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            split_at = cleaned.rfind(" ", start, end)
            if split_at > start + 20:
                end = split_at + 1
        chunks.append(cleaned[start:end])
        start = end
    return chunks


def _validate_search_session(payload: SearchRequest, request: Request, chat_session_store) -> ErrorInfo | None:
    if payload.session_id and not feature_enabled(request, "feature_session_history"):
        return ErrorInfo(
            code="FEATURE_DISABLED",
            message="Session history feature is disabled",
            details=None,
        )
    if payload.session_id and not chat_session_store.get_session(payload.session_id):
        return ErrorInfo(
            code="SESSION_NOT_FOUND",
            message="Chat session not found",
            details={"session_id": payload.session_id},
        )
    return None


async def _resolve_contextual_query(
    payload: SearchRequest,
    chat_session_store,
    context_query_rewriter_service,
) -> str:
    if not payload.session_id:
        return payload.query
    session = chat_session_store.get_session(payload.session_id)
    if not session or not session.messages:
        return payload.query
    try:
        return await context_query_rewriter_service.rewrite(
            query=payload.query,
            messages=session.messages,
        )
    except Exception:
        return payload.query


def _persist_search_result(payload: SearchRequest, chat_session_store, result) -> None:
    search_result = result.model_dump(mode="json")
    if payload.session_id:
        chat_session_store.add_message(
            session_id=payload.session_id,
            role="user",
            content=payload.query,
            metadata={
                "top_k": payload.top_k,
                "resolved_query": result.query,
            },
        )
        chat_session_store.add_message(
            session_id=payload.session_id,
            role="assistant",
            content=result.summary,
            metadata={
                "provider_used": result.provider_used,
                "confidence": result.confidence,
                "source_count": len(result.sources),
                "attempt_count": len(result.attempts),
                "search_result": search_result,
            },
        )
    chat_session_store.save_search_run(
        session_id=payload.session_id,
        query=payload.query,
        provider_used=result.provider_used,
        summary=result.summary,
        confidence=result.confidence,
        query_analysis=search_result.get("query_analysis"),
        attempts=search_result["attempts"],
        sources=search_result["sources"],
        debug_trace={
            "attempt_count": len(result.attempts),
            "source_count": len(result.sources),
            "provider_used": result.provider_used,
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        success=True,
        data=HealthData(
            status="ok",
            service="web-search-backend",
            version="0.1.0",
            llm_enabled=settings.llm_enabled,
            llm_base_url=settings.llm_base_url,
        ),
        error=None,
        meta=response_meta(),
    )


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    orchestrator = request.app.state.services["orchestrator"]
    chat_session_store = request.app.state.services["chat_session_store"]
    context_query_rewriter_service = request.app.state.services["context_query_rewriter_service"]
    try:
        session_error = _validate_search_session(payload, request, chat_session_store)
        if session_error:
            return SearchResponse(
                success=False,
                data=None,
                error=session_error,
                meta=response_meta(),
            )

        resolved_query = await _resolve_contextual_query(
            payload=payload,
            chat_session_store=chat_session_store,
            context_query_rewriter_service=context_query_rewriter_service,
        )
        result = await orchestrator.search(query=resolved_query, top_k=payload.top_k)
        result.summary = finalize_summary_for_response(
            summary=result.summary,
            query=result.query,
            sources=result.sources,
        )
        _persist_search_result(payload, chat_session_store, result)
        return SearchResponse(success=True, data=result, error=None, meta=response_meta())
    except Exception as exc:
        return SearchResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="SEARCH_FAILED", message="Search pipeline failed", details={"error": str(exc)}),
            meta=response_meta(),
        )


@router.post("/search/stream")
async def search_stream(payload: SearchRequest, request: Request) -> StreamingResponse:
    orchestrator = request.app.state.services["orchestrator"]
    chat_session_store = request.app.state.services["chat_session_store"]
    context_query_rewriter_service = request.app.state.services["context_query_rewriter_service"]

    async def event_generator():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def emit(event: str, data: dict) -> None:
            await queue.put((event, data))

        async def run_search() -> None:
            try:
                session_error = _validate_search_session(payload, request, chat_session_store)
                if session_error:
                    await emit("error", session_error.model_dump(mode="json"))
                    return

                await emit("status", {"status": "accepted", "query": payload.query, "top_k": payload.top_k})
                await emit("status", {"status": "context_rewrite_started"})
                resolved_query = await _resolve_contextual_query(
                    payload=payload,
                    chat_session_store=chat_session_store,
                    context_query_rewriter_service=context_query_rewriter_service,
                )
                await emit(
                    "status",
                    {
                        "status": "context_rewrite_done",
                        "query": payload.query,
                        "resolved_query": resolved_query,
                    },
                )
                result = await orchestrator.search_with_events(
                    query=resolved_query,
                    top_k=payload.top_k,
                    emit=emit,
                )
                result.summary = finalize_summary_for_response(
                    summary=result.summary,
                    query=result.query,
                    sources=result.sources,
                )
                for chunk in _summary_chunks(result.summary):
                    await emit("token", {"text": chunk})
                    await asyncio.sleep(0.03)

                _persist_search_result(payload, chat_session_store, result)
                await emit(
                    "done",
                    {
                        "result": result.model_dump(mode="json"),
                        "meta": SearchResponse(
                            success=True,
                            data=result,
                            error=None,
                            meta=response_meta(),
                        ).meta.model_dump(mode="json"),
                    },
                )
            except Exception as exc:
                await emit(
                    "error",
                    {
                        "code": "SEARCH_STREAM_FAILED",
                        "message": "Search stream failed",
                        "details": {"error": str(exc)},
                    },
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_search())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield _sse(event, data)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/keys/tavily", response_model=TavilyKeysResponse)
async def list_tavily_keys(request: Request) -> TavilyKeysResponse:
    key_store = request.app.state.services["key_store"]
    return _keys_response(key_store)


@router.post("/keys/tavily", response_model=TavilyKeysResponse, status_code=status.HTTP_201_CREATED)
async def add_tavily_key(payload: KeyCreateRequest, request: Request) -> TavilyKeysResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Ops dashboard feature is disabled", details=None),
            meta=response_meta(),
        )
    actor_role = require_role(request, "operator")
    key_store = request.app.state.services["key_store"]
    audit = request.app.state.services["audit_log_store"]
    try:
        key_store.add_key(api_key=payload.api_key, label=payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit.append(
        {
            "actor_role": actor_role,
            "action": "tavily_key_add",
            "path": str(request.url.path),
            "method": request.method,
            "status": "success",
            "details": {"label": payload.label or "Tavily key"},
        }
    )

    return _keys_response(key_store)


@router.delete("/keys/tavily/{key_id}", response_model=TavilyKeysResponse)
async def delete_tavily_key(key_id: str, request: Request) -> TavilyKeysResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Ops dashboard feature is disabled", details=None),
            meta=response_meta(),
        )
    actor_role = require_role(request, "operator")
    key_store = request.app.state.services["key_store"]
    audit = request.app.state.services["audit_log_store"]
    deleted = key_store.delete_key(key_id)

    if not deleted:
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="KEY_NOT_FOUND", message="Tavily key not found", details={"key_id": key_id}),
            meta=response_meta(),
        )

    audit.append(
        {
            "actor_role": actor_role,
            "action": "tavily_key_delete",
            "path": str(request.url.path),
            "method": request.method,
            "status": "success",
            "details": {"key_id": key_id},
        }
    )
    return _keys_response(key_store)


@router.patch("/keys/tavily/{key_id}", response_model=TavilyKeysResponse)
async def update_tavily_key(
    key_id: str,
    payload: KeyUpdateRequest,
    request: Request,
) -> TavilyKeysResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Ops dashboard feature is disabled", details=None),
            meta=response_meta(),
        )
    actor_role = require_role(request, "operator")
    key_store = request.app.state.services["key_store"]
    audit = request.app.state.services["audit_log_store"]
    try:
        record = key_store.update_key(key_id=key_id, label=payload.label, status=payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not record:
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="KEY_NOT_FOUND", message="Tavily key not found", details={"key_id": key_id}),
            meta=response_meta(),
        )
    audit.append(
        {
            "actor_role": actor_role,
            "action": "tavily_key_update",
            "path": str(request.url.path),
            "method": request.method,
            "status": "success",
            "details": {"key_id": key_id, "label": payload.label, "status_value": payload.status},
        }
    )
    return _keys_response(key_store)


@router.post("/keys/tavily/{key_id}/cooldown/reset", response_model=TavilyKeysResponse)
async def reset_tavily_key_cooldown(key_id: str, request: Request) -> TavilyKeysResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Ops dashboard feature is disabled", details=None),
            meta=response_meta(),
        )
    actor_role = require_role(request, "operator")
    key_store = request.app.state.services["key_store"]
    audit = request.app.state.services["audit_log_store"]
    record = key_store.reset_cooldown(key_id=key_id)
    if not record:
        return TavilyKeysResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="KEY_NOT_FOUND", message="Tavily key not found", details={"key_id": key_id}),
            meta=response_meta(),
        )
    audit.append(
        {
            "actor_role": actor_role,
            "action": "tavily_key_reset_cooldown",
            "path": str(request.url.path),
            "method": request.method,
            "status": "success",
            "details": {"key_id": key_id},
        }
    )
    return _keys_response(key_store)


@router.get("/keys/tavily/metrics", response_model=TavilyKeyMetricsResponse)
async def tavily_key_metrics(request: Request) -> TavilyKeyMetricsResponse:
    if not feature_enabled(request, "feature_ops_dashboard"):
        return TavilyKeyMetricsResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Ops dashboard feature is disabled", details=None),
            meta=response_meta(),
        )
    key_store = request.app.state.services["key_store"]
    records = key_store.list_records()
    keys = [_key_info(record) for record in records]
    total_success = sum(record.success_count for record in records)
    total_failure = sum(record.failure_count for record in records)
    avg_success_rate = round(sum(record.success_rate_5m for record in records) / max(len(records), 1), 2)
    data = TavilyKeyMetricsData(
        total_keys=len(records),
        active_keys=sum(1 for record in records if record.status == "active"),
        cooling_down_keys=sum(1 for record in records if record.status == "cooling_down"),
        unhealthy_keys=sum(1 for record in records if record.status == "unhealthy"),
        exhausted_keys=sum(1 for record in records if record.status == "exhausted"),
        total_success_count=total_success,
        total_failure_count=total_failure,
        average_success_rate=avg_success_rate,
        keys=keys,
    )
    return TavilyKeyMetricsResponse(success=True, data=data, error=None, meta=response_meta())


@router.post("/ops/searxng/circuit/reset")
async def reset_searxng_circuit(request: Request) -> dict:
    require_role(request, "operator")
    searxng_service = request.app.state.services["searxng_service"]
    searxng_service.reset_circuit()
    return {
        "success": True,
        "data": {"status": "ok", "message": "SearXNG circuit reset"},
        "error": None,
        "meta": response_meta().model_dump(),
    }
