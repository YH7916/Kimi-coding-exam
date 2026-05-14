"""HTTP route declarations."""

from fastapi import APIRouter, Response

from oncall_app.api.static_files import read_frontend_shell

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return process health."""
    return {"status": "ok"}


@router.get("/v1", response_class=Response)
@router.get("/v2", response_class=Response)
@router.get("/v3", response_class=Response)
def frontend_page() -> Response:
    """Serve the frontend shell for each README page route."""
    return Response(read_frontend_shell(), media_type="text/html")
