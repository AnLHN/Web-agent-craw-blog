import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models.auth_schemas import AuthUser


USER_PERMISSIONS = [
    "search:use",
    "article:import",
    "article:translate",
    "article:wordpress_dry_run",
]

ADMIN_PERMISSIONS = USER_PERMISSIONS + [
    "article:wordpress_paste",
    "keys:tavily_manage",
    "llm:config_manage",
    "ops:audit_read",
    "admin:users_read",
    "admin:users_manage",
    "admin:roles_manage",
    "admin:system_manage",
]


class AuthService:
    def __init__(self, file_path: str, secret: str):
        self.path = Path(file_path)
        self.secret = secret or "dev-auth-secret-change-me"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"users": [], "sessions": []})

    def register(self, email: str, password: str, username: str | None, full_name: str | None) -> tuple[AuthUser, str]:
        data = self._read()
        normalized_email = email.strip().lower()
        if self._find_user(data, normalized_email):
            raise ValueError("email_already_registered")

        now = datetime.now(timezone.utc).isoformat()
        is_first_user = len(data["users"]) == 0
        roles = ["admin"] if is_first_user else ["user"]
        user = {
            "id": f"usr_{uuid.uuid4().hex}",
            "email": normalized_email,
            "username": username.strip() if username else None,
            "full_name": full_name.strip() if full_name else None,
            "password_hash": self._hash_password(password),
            "status": "active",
            "roles": roles,
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
        data["users"].append(user)
        token = self._create_session(data, user["id"])
        self._write(data)
        return self._public_user(user), token

    def login(self, email: str, password: str) -> tuple[AuthUser, str]:
        data = self._read()
        user = self._find_user(data, email.strip().lower())
        if not user or not self._verify_password(password, str(user.get("password_hash") or "")):
            raise ValueError("invalid_credentials")
        if user.get("status") != "active":
            raise ValueError("user_not_active")
        user["last_login_at"] = datetime.now(timezone.utc).isoformat()
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        token = self._create_session(data, str(user["id"]))
        self._write(data)
        return self._public_user(user), token

    def current_user(self, token: str) -> AuthUser | None:
        data = self._read()
        token_hash = self._hash_token(token)
        session = next(
            (
                item
                for item in data["sessions"]
                if item.get("token_hash") == token_hash and not item.get("revoked_at")
            ),
            None,
        )
        if not session:
            return None
        user = next((item for item in data["users"] if item.get("id") == session.get("user_id")), None)
        if not user or user.get("status") != "active":
            return None
        return self._public_user(user)

    def logout(self, token: str) -> None:
        data = self._read()
        token_hash = self._hash_token(token)
        now = datetime.now(timezone.utc).isoformat()
        for session in data["sessions"]:
            if session.get("token_hash") == token_hash:
                session["revoked_at"] = now
        self._write(data)

    def _create_session(self, data: dict[str, Any], user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        data["sessions"].append(
            {
                "id": f"ses_{uuid.uuid4().hex}",
                "user_id": user_id,
                "token_hash": self._hash_token(token),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "revoked_at": None,
            }
        )
        return token

    def _public_user(self, user: dict[str, Any]) -> AuthUser:
        roles = [str(item) for item in user.get("roles") or []]
        permissions = ADMIN_PERMISSIONS if "admin" in roles else USER_PERMISSIONS
        return AuthUser(
            id=str(user["id"]),
            email=str(user["email"]),
            username=user.get("username"),
            full_name=user.get("full_name"),
            status=str(user.get("status") or "active"),
            roles=roles,
            permissions=permissions,
            created_at=datetime.fromisoformat(str(user["created_at"])),
            updated_at=datetime.fromisoformat(str(user["updated_at"])),
            last_login_at=datetime.fromisoformat(str(user["last_login_at"])) if user.get("last_login_at") else None,
        )

    @staticmethod
    def _find_user(data: dict[str, Any], email: str) -> dict[str, Any] | None:
        return next((item for item in data["users"] if item.get("email") == email), None)

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
        return f"pbkdf2_sha256${salt}${digest.hex()}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        try:
            algorithm, salt, expected = password_hash.split("$", 2)
        except ValueError:
            return False
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
        return hmac.compare_digest(digest.hex(), expected)

    def _hash_token(self, token: str) -> str:
        return hmac.new(self.secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
