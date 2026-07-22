"""NEXUS PM Agent API — thin FastAPI wrapper over src/ (see
FRONTEND_IMPLEMENTATION_PLAN.md section 1).

Run:  python -m uvicorn api.main:app --port 8000
The database is migrated once at startup via the existing forward-only
runner (src/db.py); requests get their own connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from api import admin_routes, auth_routes
from src import db

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "nexus.db"


def create_app(db_path: str | Path = DEFAULT_DB_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.open_db(app.state.db_path)  # runs pending migrations
        conn.close()
        yield

    app = FastAPI(title="NEXUS PM Agent API", version="0.1.0", lifespan=lifespan)
    app.state.db_path = str(db_path)
    app.include_router(auth_routes.router)
    app.include_router(admin_routes.router)
    return app


app = create_app()
