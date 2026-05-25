from pathlib import Path

import pytest

from src.config.settings import Settings
from src.services.auth_service import AuthService
from src.services.auth_service_factory import build_auth_service
from src.services.postgres_auth_service import PostgresAuthService


def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'auth.db'}"


def test_postgres_auth_register_login_current_user_logout(tmp_path: Path) -> None:
    service = PostgresAuthService(database_url=db_url(tmp_path), secret="test-secret")

    admin, admin_token = service.register("Admin@Example.com", "super-secret-123", "admin", "Admin User")
    user, _ = service.register("user@example.com", "super-secret-123", None, None)
    login_user, login_token = service.login("USER@example.com", "super-secret-123")

    assert admin.email == "admin@example.com"
    assert admin.roles == ["admin"]
    assert "admin:users_manage" in admin.permissions
    assert user.roles == ["user"]
    assert "article:wordpress_paste" not in user.permissions
    assert login_user.email == "user@example.com"
    current_login_user = service.current_user(login_token)
    current_admin_user = service.current_user(admin_token)
    assert current_login_user is not None
    assert current_login_user.email == "user@example.com"
    assert current_admin_user is not None
    assert current_admin_user.email == "admin@example.com"

    service.logout(login_token)
    assert service.current_user(login_token) is None


def test_postgres_auth_user_status_and_roles(tmp_path: Path) -> None:
    service = PostgresAuthService(database_url=db_url(tmp_path), secret="test-secret")
    service.register("admin@example.com", "super-secret-123", None, None)
    user, token = service.register("user@example.com", "super-secret-123", None, None)

    promoted = service.add_user_role(user.id, "admin")
    assert "admin" in promoted.roles
    assert "admin:users_manage" in promoted.permissions

    demoted = service.remove_user_role(user.id, "admin")
    assert demoted.roles == ["user"]

    disabled = service.update_user_status(user.id, "disabled")
    assert disabled.status == "disabled"
    assert service.current_user(token) is None
    with pytest.raises(ValueError, match="user_not_active"):
        service.login("user@example.com", "super-secret-123")


def test_auth_service_factory_modes(tmp_path: Path) -> None:
    local = build_auth_service(
        Settings(auth_store_backend="local", auth_store_path=str(tmp_path / "auth.json"), auth_token_secret="test-secret")
    )
    auto_local = build_auth_service(
        Settings(auth_store_backend="auto", database_url="", auth_store_path=str(tmp_path / "auth2.json"), auth_token_secret="test-secret")
    )
    auto_postgres = build_auth_service(
        Settings(auth_store_backend="auto", database_url=db_url(tmp_path), auth_token_secret="test-secret")
    )

    assert isinstance(local, AuthService)
    assert isinstance(auto_local, AuthService)
    assert isinstance(auto_postgres, PostgresAuthService)

    with pytest.raises(ValueError, match="APP_AUTH_STORE_BACKEND=postgres"):
        build_auth_service(Settings(auth_store_backend="postgres", database_url="", auth_token_secret="test-secret"))
