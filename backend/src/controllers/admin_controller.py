import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.security.utils import get_authorization_scheme_param

from src.models.auth_schemas import AdminUserUpdateRequest, AdminUsersData, AdminUsersResponse
from src.models.schemas import AdminSystemStatusData, AdminSystemStatusResponse, AuditLogData, AuditLogItem, AuditLogResponse, ErrorInfo
from src.utils.response import response_meta

router = APIRouter(prefix="/admin")


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _current_admin_user(request: Request, permission: str):
    token = _bearer_token(request)
    if not token:
        return None
    auth_service = request.app.state.services["auth_service"]
    user = auth_service.current_user(token)
    if not user or permission not in user.permissions:
        return None
    return user


def _readiness_checks(request: Request) -> dict[str, str]:
    services = request.app.state.services
    return {
        "key_store": "ok" if "key_store" in services else "missing",
        "chat_session_store": "ok" if "chat_session_store" in services else "missing",
        "audit_log_store": "ok" if "audit_log_store" in services else "missing",
        "auth_service": "ok" if "auth_service" in services else "missing",
        "article_fetcher_service": "ok" if "article_fetcher_service" in services else "missing",
    }


def _article_import_status_counts(storage_path: str) -> tuple[int, dict[str, int]]:
    root = Path(storage_path)
    if not root.exists():
        return 0, {}
    counts: dict[str, int] = {}
    total = 0
    for run_json in root.glob("air_*/run.json"):
        try:
            payload = json.loads(run_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = str(payload.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        total += 1
    return total, counts


@router.get("/system-status", response_model=AdminSystemStatusResponse)
def system_status(request: Request) -> AdminSystemStatusResponse:
    if not _current_admin_user(request, "ops:audit_read"):
        return AdminSystemStatusResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Ops audit permission is required", details=None),
            meta=response_meta(),
        )

    settings = request.app.state.settings
    services = request.app.state.services
    readiness_checks = _readiness_checks(request)
    ready = all(value == "ok" for value in readiness_checks.values())
    key_store = services.get("key_store")
    try:
        tavily_key_count = len(key_store.list_keys()) if key_store else 0
    except Exception:
        tavily_key_count = 0
    run_count, run_status_counts = _article_import_status_counts(settings.article_import_storage_path)

    return AdminSystemStatusResponse(
        success=True,
        data=AdminSystemStatusData(
            status="ready" if ready else "not_ready",
            environment=settings.environment,
            auth_store_backend=settings.auth_store_backend,
            auth_service_type=type(services.get("auth_service")).__name__,
            session_store_backend=settings.session_store_backend,
            session_store_type=type(services.get("chat_session_store")).__name__,
            database_configured=bool((settings.database_url or "").strip()),
            rbac_enabled=settings.rbac_enabled,
            llm_enabled=settings.llm_enabled,
            llm_configured=bool((settings.llm_base_url or "").strip() and (settings.llm_model or "").strip()),
            tavily_key_count=tavily_key_count,
            article_import_storage_path=settings.article_import_storage_path,
            article_import_run_count=run_count,
            article_import_status_counts=run_status_counts,
            readiness_checks=readiness_checks,
        ),
        error=None,
        meta=response_meta(),
    )


@router.get("/users", response_model=AdminUsersResponse)
def list_users(request: Request) -> AdminUsersResponse:
    if not _current_admin_user(request, "admin:users_read"):
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Admin users permission is required", details=None),
            meta=response_meta(),
        )

    auth_service = request.app.state.services["auth_service"]
    users = auth_service.list_users()
    return AdminUsersResponse(
        success=True,
        data=AdminUsersData(users=users, total=len(users)),
        error=None,
        meta=response_meta(),
    )


@router.patch("/users/{user_id}", response_model=AdminUsersResponse)
def update_user(user_id: str, payload: AdminUserUpdateRequest, request: Request) -> AdminUsersResponse:
    actor = _current_admin_user(request, "admin:users_manage")
    if not actor:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Admin users manage permission is required", details=None),
            meta=response_meta(),
        )

    auth_service = request.app.state.services["auth_service"]
    try:
        auth_service.update_user_status(user_id, payload.status)
    except ValueError as exc:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code=str(exc), message="User update failed", details=None),
            meta=response_meta(),
        )
    audit = request.app.state.services["audit_log_store"]
    audit.append(
        {
            "actor_role": ",".join(actor.roles),
            "action": "admin_user_status_update",
            "path": str(request.url.path),
            "method": request.method,
            "status": "ok",
            "details": {"target_user_id": user_id, "next_status": payload.status},
        }
    )
    users = auth_service.list_users()
    return AdminUsersResponse(success=True, data=AdminUsersData(users=users, total=len(users)), error=None, meta=response_meta())


@router.put("/users/{user_id}/roles/{role}", response_model=AdminUsersResponse)
def add_user_role(user_id: str, role: str, request: Request) -> AdminUsersResponse:
    actor = _current_admin_user(request, "admin:roles_manage")
    if not actor:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Admin roles manage permission is required", details=None),
            meta=response_meta(),
        )

    auth_service = request.app.state.services["auth_service"]
    try:
        auth_service.add_user_role(user_id, role)
    except ValueError as exc:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code=str(exc), message="Role update failed", details=None),
            meta=response_meta(),
        )
    request.app.state.services["audit_log_store"].append(
        {
            "actor_role": ",".join(actor.roles),
            "action": "admin_user_role_add",
            "path": str(request.url.path),
            "method": request.method,
            "status": "ok",
            "details": {"target_user_id": user_id, "role": role},
        }
    )
    users = auth_service.list_users()
    return AdminUsersResponse(success=True, data=AdminUsersData(users=users, total=len(users)), error=None, meta=response_meta())


@router.delete("/users/{user_id}/roles/{role}", response_model=AdminUsersResponse)
def remove_user_role(user_id: str, role: str, request: Request) -> AdminUsersResponse:
    actor = _current_admin_user(request, "admin:roles_manage")
    if not actor:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Admin roles manage permission is required", details=None),
            meta=response_meta(),
        )

    auth_service = request.app.state.services["auth_service"]
    try:
        auth_service.remove_user_role(user_id, role)
    except ValueError as exc:
        return AdminUsersResponse(
            success=False,
            data=None,
            error=ErrorInfo(code=str(exc), message="Role update failed", details=None),
            meta=response_meta(),
        )
    request.app.state.services["audit_log_store"].append(
        {
            "actor_role": ",".join(actor.roles),
            "action": "admin_user_role_remove",
            "path": str(request.url.path),
            "method": request.method,
            "status": "ok",
            "details": {"target_user_id": user_id, "role": role},
        }
    )
    users = auth_service.list_users()
    return AdminUsersResponse(success=True, data=AdminUsersData(users=users, total=len(users)), error=None, meta=response_meta())


@router.get("/audit-events", response_model=AuditLogResponse)
def list_audit_events(request: Request, limit: int = 100) -> AuditLogResponse:
    if not _current_admin_user(request, "ops:audit_read"):
        return AuditLogResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="FORBIDDEN", message="Audit read permission is required", details=None),
            meta=response_meta(),
        )

    store = request.app.state.services["audit_log_store"]
    events = [AuditLogItem(**item) for item in store.list_recent(limit=limit)]
    return AuditLogResponse(
        success=True,
        data=AuditLogData(events=events, total=len(events)),
        error=None,
        meta=response_meta(),
    )
