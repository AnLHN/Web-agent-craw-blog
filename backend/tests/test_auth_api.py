from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


def build_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings_kwargs: dict[str, object] = {
        "cors_origins": ["http://localhost:3000"],
        "searxng_base_url": "https://searx.test",
        "searxng_backup_base_urls": "",
        "tavily_key_store_path": str(tmp_path / "tavily_keys.json"),
        "chat_session_store_path": str(tmp_path / "chat_sessions.json"),
        "llm_runtime_store_path": str(tmp_path / "llm_runtime.json"),
        "audit_log_store_path": str(tmp_path / "audit_logs.jsonl"),
        "auth_store_path": str(tmp_path / "auth_store.json"),
        "auth_store_backend": "local",
        "database_url": "",
        "session_store_backend": "local",
        "auth_token_secret": "test-secret",
        "llm_enabled": False,
    }
    settings_kwargs.update(overrides)
    settings = Settings(**settings_kwargs)
    return TestClient(create_app(settings_override=settings))


def test_register_first_user_becomes_admin_and_can_read_me(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Admin@Example.com",
            "password": "super-secret-123",
            "username": "admin",
            "full_name": "Admin User",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    token = payload["data"]["access_token"]
    user = payload["data"]["user"]
    assert user["email"] == "admin@example.com"
    assert user["roles"] == ["admin"]
    assert "admin:users_manage" in user["permissions"]
    assert "password_hash" not in user

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["success"] is True
    assert me.json()["data"]["user"]["email"] == "admin@example.com"


def test_register_second_user_gets_user_role_and_login_logout(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    response = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["user"]["roles"] == ["user"]
    assert "article:wordpress_paste" not in payload["data"]["user"]["permissions"]

    login = client.post("/api/v1/auth/login", json={"email": "USER@example.com", "password": "super-secret-123"})
    token = login.json()["data"]["access_token"]
    assert login.json()["success"] is True

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.json()["success"] is True

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["success"] is False
    assert me.json()["error"]["code"] == "INVALID_SESSION"


def test_login_rejects_invalid_password(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})

    response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rate_limit_blocks_repeated_attempts(tmp_path: Path) -> None:
    client = build_client(tmp_path, auth_rate_limit_max_attempts=2, auth_rate_limit_window_seconds=60)
    client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})

    first = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})
    second = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})
    third = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})

    assert first.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert second.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert third.json()["success"] is False
    assert third.json()["error"]["code"] == "RATE_LIMITED"


def test_admin_can_list_users_and_user_cannot(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    admin = client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    user = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})
    admin_token = admin.json()["data"]["access_token"]
    user_token = user.json()["data"]["access_token"]

    denied = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {user_token}"})
    allowed = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"})

    assert denied.json()["success"] is False
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert allowed.json()["success"] is True
    assert allowed.json()["data"]["total"] == 2
    assert [item["email"] for item in allowed.json()["data"]["users"]] == ["admin@example.com", "user@example.com"]


def test_admin_can_list_audit_events_and_user_cannot(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    admin = client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    user = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})
    admin_token = admin.json()["data"]["access_token"]
    user_token = user.json()["data"]["access_token"]
    client.app.state.services["audit_log_store"].append(
        {
            "actor_role": "admin",
            "action": "test_event",
            "path": "/api/v1/test",
            "method": "POST",
            "status": "ok",
            "details": {"source": "test"},
        }
    )

    denied = client.get("/api/v1/admin/audit-events", headers={"Authorization": f"Bearer {user_token}"})
    allowed = client.get("/api/v1/admin/audit-events", headers={"Authorization": f"Bearer {admin_token}"})

    assert denied.json()["success"] is False
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert allowed.json()["success"] is True
    assert allowed.json()["data"]["total"] == 1
    assert allowed.json()["data"]["events"][0]["action"] == "test_event"


def test_admin_can_read_system_status_and_user_cannot(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    admin = client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    user = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})
    admin_token = admin.json()["data"]["access_token"]
    user_token = user.json()["data"]["access_token"]

    denied = client.get("/api/v1/admin/system-status", headers={"Authorization": f"Bearer {user_token}"})
    allowed = client.get("/api/v1/admin/system-status", headers={"Authorization": f"Bearer {admin_token}"})

    assert denied.json()["success"] is False
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert allowed.json()["success"] is True
    assert allowed.json()["data"]["status"] == "ready"
    assert allowed.json()["data"]["auth_service_type"] == "AuthService"
    assert allowed.json()["data"]["readiness_checks"]["auth_service"] == "ok"


def test_admin_can_manage_user_status_and_roles(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    admin = client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    user = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})
    admin_token = admin.json()["data"]["access_token"]
    user_id = user.json()["data"]["user"]["id"]

    disabled = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "disabled"},
    )
    promoted = client.put(f"/api/v1/admin/users/{user_id}/roles/admin", headers={"Authorization": f"Bearer {admin_token}"})
    demoted = client.delete(f"/api/v1/admin/users/{user_id}/roles/admin", headers={"Authorization": f"Bearer {admin_token}"})

    assert disabled.json()["success"] is True
    disabled_user = next(item for item in disabled.json()["data"]["users"] if item["id"] == user_id)
    assert disabled_user["status"] == "disabled"
    promoted_user = next(item for item in promoted.json()["data"]["users"] if item["id"] == user_id)
    assert "admin" in promoted_user["roles"]
    demoted_user = next(item for item in demoted.json()["data"]["users"] if item["id"] == user_id)
    assert demoted_user["roles"] == ["user"]


def test_user_cannot_manage_users(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    user = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "super-secret-123"})
    user_token = user.json()["data"]["access_token"]
    user_id = user.json()["data"]["user"]["id"]

    response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"status": "disabled"},
    )

    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "FORBIDDEN"
