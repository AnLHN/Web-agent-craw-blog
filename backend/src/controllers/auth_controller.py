from fastapi import APIRouter, Request
from fastapi.security.utils import get_authorization_scheme_param

from src.models.auth_schemas import (
    AuthResponse,
    CurrentUserData,
    CurrentUserResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
)
from src.models.schemas import ErrorInfo
from src.utils.response import response_meta


router = APIRouter(prefix="/auth")


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, request: Request) -> AuthResponse:
    auth_service = request.app.state.services["auth_service"]
    try:
        user, token = auth_service.register(
            email=payload.email,
            password=payload.password,
            username=payload.username,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        return AuthResponse(
            success=False,
            data=None,
            error=ErrorInfo(code=str(exc), message="Registration failed", details=None),
            meta=response_meta(),
        )
    return AuthResponse(success=True, data={"user": user, "access_token": token, "token_type": "bearer"}, error=None, meta=response_meta())


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request) -> AuthResponse:
    auth_service = request.app.state.services["auth_service"]
    try:
        user, token = auth_service.login(email=payload.email, password=payload.password)
    except ValueError:
        return AuthResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="INVALID_CREDENTIALS", message="Invalid email or password", details=None),
            meta=response_meta(),
        )
    return AuthResponse(success=True, data={"user": user, "access_token": token, "token_type": "bearer"}, error=None, meta=response_meta())


@router.get("/me", response_model=CurrentUserResponse)
def me(request: Request) -> CurrentUserResponse:
    token = _bearer_token(request)
    if not token:
        return CurrentUserResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="AUTH_REQUIRED", message="Bearer token is required", details=None),
            meta=response_meta(),
        )
    auth_service = request.app.state.services["auth_service"]
    user = auth_service.current_user(token)
    if not user:
        return CurrentUserResponse(
            success=False,
            data=None,
            error=ErrorInfo(code="INVALID_SESSION", message="Session is invalid or expired", details=None),
            meta=response_meta(),
        )
    return CurrentUserResponse(success=True, data=CurrentUserData(user=user), error=None, meta=response_meta())


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request) -> LogoutResponse:
    token = _bearer_token(request)
    if token:
        auth_service = request.app.state.services["auth_service"]
        auth_service.logout(token)
    return LogoutResponse(success=True, data={"status": "logged_out"}, error=None, meta=response_meta())
