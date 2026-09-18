"""Local and hosted PostgreSQL connection settings."""

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings


@pytest.mark.parametrize("mode", ["prefer", "require", "verify-full"])
def test_database_urls_preserve_credentials_and_ssl(mode):
    settings = Settings(
        _env_file=None,
        POSTGRES_USER="user@example",
        POSTGRES_PASSWORD="secret@:/?#%",
        POSTGRES_HOST="db.example.com",
        POSTGRES_DB="app",
        POSTGRES_SSL_MODE=mode,
    )
    for value, ssl_key in [
        (settings.DATABASE_URL, "ssl"),
        (settings.DATABASE_URL_SYNC, "sslmode"),
    ]:
        url = make_url(value)
        assert url.username == "user@example"
        assert url.password == "secret@:/?#%"
        assert url.host == "db.example.com"
        assert url.database == "app"
        assert url.query[ssl_key] == mode
