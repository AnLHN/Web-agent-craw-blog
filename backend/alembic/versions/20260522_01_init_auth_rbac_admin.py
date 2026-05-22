"""init auth rbac admin tables

Revision ID: 20260522_01
Revises: 20260514_01
Create Date: 2026-05-22 00:00:00
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260522_01"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_verification"),
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_status", "users", ["status"], unique=False)

    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"], unique=False)
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("refresh_token_hash", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)

    op.create_table(
        "admin_profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("admin_level", sa.String(length=32), nullable=False, server_default="admin"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_admin_profiles_admin_level", "admin_profiles", ["admin_level"], unique=False)

    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=True),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_events_actor_user_id", "admin_audit_events", ["actor_user_id"], unique=False)
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"], unique=False)
    op.create_index("ix_admin_audit_events_action", "admin_audit_events", ["action"], unique=False)

    now = datetime.now(timezone.utc)

    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"id": "role_user", "name": "user", "description": "Standard application user", "created_at": now},
            {"id": "role_admin", "name": "admin", "description": "Administrator with full access", "created_at": now},
        ],
    )

    permission_rows = [
        ("perm_search_use", "search:use", "Use search chat"),
        ("perm_article_import", "article:import", "Import article URLs"),
        ("perm_article_translate", "article:translate", "Translate imported articles"),
        ("perm_article_wordpress_dry_run", "article:wordpress_dry_run", "Check WordPress browser readiness"),
        ("perm_article_wordpress_paste", "article:wordpress_paste", "Paste drafts into WordPress"),
        ("perm_keys_tavily_manage", "keys:tavily_manage", "Manage Tavily keys"),
        ("perm_llm_config_manage", "llm:config_manage", "Manage LLM runtime config"),
        ("perm_ops_audit_read", "ops:audit_read", "Read ops audit logs"),
        ("perm_admin_users_read", "admin:users_read", "Read users in admin"),
        ("perm_admin_users_manage", "admin:users_manage", "Manage users in admin"),
        ("perm_admin_roles_manage", "admin:roles_manage", "Manage roles and permissions"),
        ("perm_admin_system_manage", "admin:system_manage", "Manage system settings"),
    ]
    op.bulk_insert(
        sa.table(
            "permissions",
            sa.column("id", sa.String),
            sa.column("code", sa.String),
            sa.column("description", sa.Text),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"id": permission_id, "code": code, "description": description, "created_at": now}
            for permission_id, code, description in permission_rows
        ],
    )

    user_permission_ids = {
        "perm_search_use",
        "perm_article_import",
        "perm_article_translate",
        "perm_article_wordpress_dry_run",
    }
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_id", sa.String),
            sa.column("permission_id", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"role_id": "role_user", "permission_id": permission_id, "created_at": now}
            for permission_id in sorted(user_permission_ids)
        ]
        + [
            {"role_id": "role_admin", "permission_id": permission_id, "created_at": now}
            for permission_id, _, _ in permission_rows
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_events_action", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_actor_user_id", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_index("ix_admin_profiles_admin_level", table_name="admin_profiles")
    op.drop_table("admin_profiles")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
