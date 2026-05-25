from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param

from src.models.auth_schemas import AuthUser

ROLE_LEVEL = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
}


def current_role(request: Request) -> str:
    role = (request.headers.get("X-Role") or "viewer").strip().lower()
    if role not in ROLE_LEVEL:
        return "viewer"
    return role


def require_role(request: Request, minimum_role: str) -> str:
    settings = request.app.state.settings
    role = current_role(request)
    if not settings.rbac_enabled:
        return role

    if ROLE_LEVEL[role] < ROLE_LEVEL[minimum_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' is not allowed to perform this action",
        )

    if minimum_role == "admin" and settings.rbac_admin_token:
        token = request.headers.get("X-Admin-Token", "")
        if token != settings.rbac_admin_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid admin token",
            )
    return role


def require_permission(request: Request, permission: str) -> AuthUser:
    if not request.app.state.settings.rbac_enabled:
        return AuthUser(
            id="dev_operator",
            email="dev-operator@local",
            status="active",
            roles=[current_role(request)],
            permissions=[permission],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bearer token is required")

    auth_service = request.app.state.services["auth_service"]
    user = auth_service.current_user(token)
    if not user or permission not in user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required")
    return user
