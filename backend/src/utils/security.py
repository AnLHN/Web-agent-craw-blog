from fastapi import HTTPException, Request, status

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
