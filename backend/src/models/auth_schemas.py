from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.models.schemas import ErrorInfo, ResponseMeta


class AuthUser(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    status: str
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    username: Optional[str] = Field(default=None, min_length=3, max_length=80)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid_email")
        return email


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid_email")
        return email


class AuthData(BaseModel):
    user: AuthUser
    access_token: str
    token_type: str = "bearer"


class CurrentUserData(BaseModel):
    user: AuthUser


class AdminUsersData(BaseModel):
    users: List[AuthUser] = Field(default_factory=list)
    total: int


class AdminUserUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class AuthResponse(BaseModel):
    success: bool
    data: Optional[AuthData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class CurrentUserResponse(BaseModel):
    success: bool
    data: Optional[CurrentUserData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class AdminUsersResponse(BaseModel):
    success: bool
    data: Optional[AdminUsersData] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta


class LogoutResponse(BaseModel):
    success: bool
    data: dict[str, str]
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta
