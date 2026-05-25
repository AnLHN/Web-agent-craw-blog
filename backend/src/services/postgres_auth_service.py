from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import PermissionRow, RolePermissionRow, RoleRow, UserRoleRow, UserRow, UserSessionRow
from src.models.auth_schemas import AuthUser
from src.services.auth_service import ADMIN_PERMISSIONS, USER_PERMISSIONS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresAuthService:
    def __init__(self, database_url: str, secret: str):
        self.secret = secret or "dev-auth-secret-change-me"
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        for table in [
            UserRow.__table__,
            RoleRow.__table__,
            PermissionRow.__table__,
            UserRoleRow.__table__,
            RolePermissionRow.__table__,
            UserSessionRow.__table__,
        ]:
            table.create(self.engine, checkfirst=True)
        self._ensure_seed_data()

    def register(self, email: str, password: str, username: str | None, full_name: str | None) -> tuple[AuthUser, str]:
        normalized_email = email.strip().lower()
        now = _utc_now()
        with self.session_factory() as db:
            if self._find_user(db, normalized_email):
                raise ValueError("email_already_registered")
            is_first_user = db.scalar(select(func.count(UserRow.id))) == 0
            role_names = ["admin"] if is_first_user else ["user"]
            user = UserRow(
                id=f"usr_{uuid.uuid4().hex}",
                email=normalized_email,
                username=username.strip() if username else None,
                full_name=full_name.strip() if full_name else None,
                password_hash=self._hash_password(password),
                status="active",
                is_email_verified=False,
                created_at=now,
                updated_at=now,
                last_login_at=None,
            )
            db.add(user)
            db.flush()
            self._set_roles(db, user.id, role_names)
            token = self._create_session(db, user.id)
            db.commit()
            return self._public_user(db, user), token

    def login(self, email: str, password: str) -> tuple[AuthUser, str]:
        with self.session_factory() as db:
            user = self._find_user(db, email.strip().lower())
            if not user or not self._verify_password(password, user.password_hash):
                raise ValueError("invalid_credentials")
            if user.status != "active":
                raise ValueError("user_not_active")
            user.last_login_at = _utc_now()
            user.updated_at = _utc_now()
            token = self._create_session(db, user.id)
            db.commit()
            return self._public_user(db, user), token

    def current_user(self, token: str) -> AuthUser | None:
        token_hash = self._hash_token(token)
        now = _utc_now()
        with self.session_factory() as db:
            session = db.scalar(
                select(UserSessionRow).where(
                    UserSessionRow.session_token_hash == token_hash,
                    UserSessionRow.revoked_at.is_(None),
                    UserSessionRow.expires_at > now,
                )
            )
            if not session:
                return None
            user = db.get(UserRow, session.user_id)
            if not user or user.status != "active":
                return None
            return self._public_user(db, user)

    def list_users(self) -> list[AuthUser]:
        with self.session_factory() as db:
            rows = db.scalars(select(UserRow).order_by(UserRow.created_at.asc())).all()
            return [self._public_user(db, row) for row in rows]

    def update_user_status(self, user_id: str, status: str) -> AuthUser:
        if status not in {"active", "disabled"}:
            raise ValueError("invalid_status")
        with self.session_factory() as db:
            user = db.get(UserRow, user_id)
            if not user:
                raise ValueError("user_not_found")
            user.status = status
            user.updated_at = _utc_now()
            db.commit()
            return self._public_user(db, user)

    def add_user_role(self, user_id: str, role: str) -> AuthUser:
        if role not in {"admin", "user"}:
            raise ValueError("invalid_role")
        with self.session_factory() as db:
            user = db.get(UserRow, user_id)
            if not user:
                raise ValueError("user_not_found")
            roles = self._role_names(db, user.id)
            if role not in roles:
                roles.append(role)
            self._set_roles(db, user.id, roles)
            user.updated_at = _utc_now()
            db.commit()
            return self._public_user(db, user)

    def remove_user_role(self, user_id: str, role: str) -> AuthUser:
        if role not in {"admin", "user"}:
            raise ValueError("invalid_role")
        with self.session_factory() as db:
            user = db.get(UserRow, user_id)
            if not user:
                raise ValueError("user_not_found")
            roles = [item for item in self._role_names(db, user.id) if item != role] or ["user"]
            self._set_roles(db, user.id, roles)
            user.updated_at = _utc_now()
            db.commit()
            return self._public_user(db, user)

    def logout(self, token: str) -> None:
        token_hash = self._hash_token(token)
        now = _utc_now()
        with self.session_factory() as db:
            sessions = db.scalars(select(UserSessionRow).where(UserSessionRow.session_token_hash == token_hash)).all()
            for session in sessions:
                session.revoked_at = now
            db.commit()

    def _ensure_seed_data(self) -> None:
        now = _utc_now()
        permission_descriptions = {
            "search:use": "Use search chat",
            "article:import": "Import article URLs",
            "article:translate": "Translate imported articles",
            "article:wordpress_dry_run": "Check WordPress browser readiness",
            "article:wordpress_paste": "Paste drafts into WordPress",
            "keys:tavily_manage": "Manage Tavily keys",
            "llm:config_manage": "Manage LLM runtime config",
            "ops:audit_read": "Read ops audit logs",
            "admin:users_read": "Read users in admin",
            "admin:users_manage": "Manage users in admin",
            "admin:roles_manage": "Manage roles and permissions",
            "admin:system_manage": "Manage system settings",
        }
        with self.session_factory() as db:
            for name, description in {"user": "Standard application user", "admin": "Administrator with full access"}.items():
                if not db.scalar(select(RoleRow).where(RoleRow.name == name)):
                    db.add(RoleRow(id=f"role_{name}", name=name, description=description, created_at=now))
            for code, description in permission_descriptions.items():
                if not db.scalar(select(PermissionRow).where(PermissionRow.code == code)):
                    db.add(PermissionRow(id=f"perm_{code.replace(':', '_')}", code=code, description=description, created_at=now))
            db.flush()
            self._ensure_role_permissions(db, "user", USER_PERMISSIONS)
            self._ensure_role_permissions(db, "admin", ADMIN_PERMISSIONS)
            db.commit()

    def _ensure_role_permissions(self, db: Session, role_name: str, permission_codes: list[str]) -> None:
        role = db.scalar(select(RoleRow).where(RoleRow.name == role_name))
        if not role:
            return
        for code in permission_codes:
            permission = db.scalar(select(PermissionRow).where(PermissionRow.code == code))
            if not permission:
                continue
            exists = db.get(RolePermissionRow, {"role_id": role.id, "permission_id": permission.id})
            if not exists:
                db.add(RolePermissionRow(role_id=role.id, permission_id=permission.id, created_at=_utc_now()))

    def _find_user(self, db: Session, email: str) -> UserRow | None:
        return db.scalar(select(UserRow).where(UserRow.email == email))

    def _create_session(self, db: Session, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        db.add(
            UserSessionRow(
                id=f"ses_{uuid.uuid4().hex}",
                user_id=user_id,
                session_token_hash=self._hash_token(token),
                refresh_token_hash=None,
                expires_at=_utc_now() + timedelta(days=30),
                revoked_at=None,
                created_at=_utc_now(),
            )
        )
        return token

    def _public_user(self, db: Session, user: UserRow) -> AuthUser:
        roles = self._role_names(db, user.id)
        permissions = self._permission_codes(db, roles)
        return AuthUser(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            status=user.status,
            roles=roles,
            permissions=permissions,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    def _role_names(self, db: Session, user_id: str) -> list[str]:
        rows = db.execute(
            select(RoleRow.name)
            .join(UserRoleRow, UserRoleRow.role_id == RoleRow.id)
            .where(UserRoleRow.user_id == user_id)
            .order_by(RoleRow.name.asc())
        ).all()
        names = [row[0] for row in rows]
        if "user" in names:
            names = ["user"] + [name for name in names if name != "user"]
        return names

    def _permission_codes(self, db: Session, role_names: list[str]) -> list[str]:
        if not role_names:
            return []
        rows = db.execute(
            select(PermissionRow.code)
            .join(RolePermissionRow, RolePermissionRow.permission_id == PermissionRow.id)
            .join(RoleRow, RoleRow.id == RolePermissionRow.role_id)
            .where(RoleRow.name.in_(role_names))
            .order_by(PermissionRow.code.asc())
        ).all()
        return sorted({row[0] for row in rows})

    def _set_roles(self, db: Session, user_id: str, roles: list[str]) -> None:
        db.execute(delete(UserRoleRow).where(UserRoleRow.user_id == user_id))
        for role_name in roles:
            role = db.scalar(select(RoleRow).where(RoleRow.name == role_name))
            if role:
                db.add(UserRoleRow(user_id=user_id, role_id=role.id, created_at=_utc_now()))

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
