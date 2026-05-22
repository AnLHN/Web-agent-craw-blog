from pathlib import Path

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


def build_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        cors_origins=["http://localhost:3000"],
        searxng_base_url="https://searx.test",
        searxng_backup_base_urls="",
        tavily_key_store_path=str(tmp_path / "tavily_keys.json"),
        chat_session_store_path=str(tmp_path / "chat_sessions.json"),
        llm_runtime_store_path=str(tmp_path / "llm_runtime.json"),
        audit_log_store_path=str(tmp_path / "audit_logs.jsonl"),
        auth_store_path=str(tmp_path / "auth_store.json"),
        auth_token_secret="test-secret",
        llm_enabled=False,
    )
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
