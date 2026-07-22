"""SonnetClient as a FastAPI dependency so tests can override it with a stub
(app.dependency_overrides[get_sonnet]) — API tests never hit the network."""

from __future__ import annotations

from src.llm.sonnet_client import SonnetClient


def get_sonnet() -> SonnetClient:
    return SonnetClient()
