from fastapi import APIRouter, HTTPException, Query, Request, status

from src.models.schemas import (
    ChatMessageCreateRequest,
    ChatSessionCreateRequest,
    ChatSessionData,
    ChatSessionListData,
    ChatSessionListResponse,
    ChatSessionResponse,
    ErrorInfo,
)
from src.utils.feature_flags import feature_enabled
from src.utils.response import response_meta

router = APIRouter()


@router.post("/chat/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    payload: ChatSessionCreateRequest,
    request: Request,
) -> ChatSessionResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    session = store.create_session(title=payload.title)
    return ChatSessionResponse(
        success=True,
        data=ChatSessionData(session=session),
        error=None,
        meta=response_meta(),
    )


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    request: Request,
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ChatSessionListResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionListResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    sessions = store.list_sessions(q=q, limit=limit)
    return ChatSessionListResponse(
        success=True,
        data=ChatSessionListData(sessions=sessions, total=len(sessions)),
        error=None,
        meta=response_meta(),
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(session_id: str, request: Request) -> ChatSessionResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    session = store.get_session(session_id=session_id)
    if not session:
        return ChatSessionResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="SESSION_NOT_FOUND", message="Chat session not found", details={"session_id": session_id}),
            meta=response_meta(),
        )
    return ChatSessionResponse(
        success=True,
        data=ChatSessionData(session=session),
        error=None,
        meta=response_meta(),
    )


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatSessionResponse)
async def add_chat_message(
    session_id: str,
    payload: ChatMessageCreateRequest,
    request: Request,
) -> ChatSessionResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    session = store.add_message(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionResponse(
        success=True,
        data=ChatSessionData(session=session),
        error=None,
        meta=response_meta(),
    )


@router.post("/chat/sessions/{session_id}/replay", response_model=ChatSessionResponse)
async def replay_chat_session(session_id: str, request: Request) -> ChatSessionResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    session = store.replay_session(session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionResponse(
        success=True,
        data=ChatSessionData(session=session),
        error=None,
        meta=response_meta(),
    )




@router.delete("/chat/sessions/{session_id}", response_model=ChatSessionListResponse)
async def delete_chat_session(session_id: str, request: Request) -> ChatSessionListResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionListResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    deleted = store.delete_session(session_id=session_id)
    if not deleted:
        return ChatSessionListResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="SESSION_NOT_FOUND", message="Chat session not found", details={"session_id": session_id}),
            meta=response_meta(),
        )
    sessions = store.list_sessions()
    return ChatSessionListResponse(
        success=True,
        data=ChatSessionListData(sessions=sessions, total=len(sessions)),
        error=None,
        meta=response_meta(),
    )


@router.delete("/chat/sessions", response_model=ChatSessionListResponse)
async def clear_chat_sessions(request: Request) -> ChatSessionListResponse:
    if not feature_enabled(request, "feature_session_history"):
        return ChatSessionListResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FEATURE_DISABLED", message="Session history feature is disabled", details=None),
            meta=response_meta(),
        )
    store = request.app.state.services["chat_session_store"]
    _ = store.clear_sessions()
    return ChatSessionListResponse(
        success=True,
        data=ChatSessionListData(sessions=[], total=0),
        error=None,
        meta=response_meta(),
    )
