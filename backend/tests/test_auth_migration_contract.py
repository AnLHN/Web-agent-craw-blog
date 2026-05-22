from pathlib import Path


MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260522_01_init_auth_rbac_admin.py"


def test_auth_migration_defines_required_tables_and_seed_permissions() -> None:
    content = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in [
        "users",
        "roles",
        "user_roles",
        "permissions",
        "role_permissions",
        "user_sessions",
        "admin_profiles",
        "admin_audit_events",
    ]:
        assert f'"{table_name}"' in content

    for permission in [
        "search:use",
        "article:import",
        "article:translate",
        "article:wordpress_dry_run",
        "article:wordpress_paste",
        "keys:tavily_manage",
        "llm:config_manage",
        "ops:audit_read",
        "admin:users_read",
        "admin:users_manage",
        "admin:roles_manage",
        "admin:system_manage",
    ]:
        assert permission in content


def test_auth_migration_keeps_admin_profile_separate_from_users() -> None:
    content = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"admin_profiles"' in content
    assert 'sa.Column("user_id", sa.String(length=64), nullable=False)' in content
    assert 'sa.Column("admin_level", sa.String(length=32)' in content
    assert 'sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE")' in content
