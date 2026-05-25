from sqlalchemy.exc import SQLAlchemyError

from src.config.settings import Settings
from src.services.auth_service import AuthService
from src.services.postgres_auth_service import PostgresAuthService


def build_auth_service(settings: Settings):
    backend = (settings.auth_store_backend or "auto").strip().lower()
    db_url = (settings.database_url or "").strip()
    can_use_postgres = bool(db_url and (db_url.startswith("postgres") or db_url.startswith("sqlite")))

    if backend == "local":
        return AuthService(file_path=settings.auth_store_path, secret=settings.auth_token_secret)
    if backend == "postgres":
        if not can_use_postgres:
            raise ValueError("APP_AUTH_STORE_BACKEND=postgres nhung APP_DATABASE_URL chua hop le.")
        return PostgresAuthService(database_url=db_url, secret=settings.auth_token_secret)
    if backend == "auto" and can_use_postgres:
        try:
            return PostgresAuthService(database_url=db_url, secret=settings.auth_token_secret)
        except SQLAlchemyError:
            return AuthService(file_path=settings.auth_store_path, secret=settings.auth_token_secret)
    return AuthService(file_path=settings.auth_store_path, secret=settings.auth_token_secret)
