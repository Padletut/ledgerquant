"""ASGI entry point for the capture-only service."""

from ledgerquant.capture.api import create_app
from ledgerquant.capture.settings import load_settings
from ledgerquant.capture.storage import create_store


settings = load_settings()
app = create_app(create_store(settings.database_url), settings.collector_token)
