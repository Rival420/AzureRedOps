import os
import secrets
import functools


class Settings:
    """Runtime configuration sourced from environment variables."""

    def __init__(self):
        self.database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://azureredops:azureredops@db:5432/azureredops",
        )
        # Auth / crypto
        self.secret_key = os.environ.get("SECRET_KEY", secrets.token_urlsafe(48))
        self.jwt_algorithm = "HS256"
        self.access_token_minutes = int(os.environ.get("ACCESS_TOKEN_MINUTES", "720"))

        # Single admin user (bootstrapped on first run)
        self.admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        self.admin_password = os.environ.get("ADMIN_PASSWORD", "changeme")

        # Fernet key for token-vault encryption at rest. Derived from SECRET_KEY
        # if not explicitly supplied.
        self.vault_key = os.environ.get("VAULT_KEY")

        self.cors_origins = [
            o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
        ]


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
