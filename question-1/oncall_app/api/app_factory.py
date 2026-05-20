"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from oncall_app.api.router import router
from oncall_app.api.static_files import FRONTEND_DIR
from oncall_app.runtime import reset_runtime


def create_app(test_mode: bool = False) -> FastAPI:
    """Build the HTTP application."""
    reset_runtime(test_mode=test_mode)
    app = FastAPI(title="On-Call Copilot")
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    app.include_router(router)
    return app
