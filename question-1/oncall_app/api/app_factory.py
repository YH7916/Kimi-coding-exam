"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from oncall_app.api.router import reset_runtime, router
from oncall_app.api.static_files import FRONTEND_DIR


def create_app() -> FastAPI:
    """Build the HTTP application."""
    reset_runtime()
    app = FastAPI(title="On-Call Copilot")
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    app.include_router(router)
    return app
