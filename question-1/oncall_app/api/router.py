"""HTTP route declarations."""

from fastapi import APIRouter, Response

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
    html = "<!doctype html><html><body><div id='app'></div></body></html>"
    return Response(html, media_type="text/html")
