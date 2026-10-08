"""Process configuration; secrets are read from mounted files."""

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import URL


@dataclass(frozen=True)
class Settings:
    database_url: URL
    collector_token: str


def database_url_from_environment() -> URL:
    password_file = Path(os.environ["DB_PASSWORD_FILE"])
    password = password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("database password file is empty")
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("DB_USER", "ledgerquant"),
        password=password,
        host=os.environ.get("DB_HOST", "postgres"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "ledgerquant"),
    )


def load_settings() -> Settings:
    token = Path(os.environ["COLLECTOR_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("collector token must contain at least 32 characters")
    return Settings(database_url=database_url_from_environment(), collector_token=token)
