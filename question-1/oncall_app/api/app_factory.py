"""FastAPI application factory."""

from fastapi import FastAPI

from oncall_app.api.router import router


def create_app() -> FastAPI:
    """Build the HTTP application."""
    app = FastAPI(title="On-Call Copilot")
    app.include_router(router)
    return app
