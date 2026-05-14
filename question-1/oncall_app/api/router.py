"""HTTP route declarations."""

from pathlib import Path

from fastapi import APIRouter, Query, Response, status

from oncall_app.api.schemas import (
    DocumentCreate,
    DocumentCreated,
    SearchResponse,
    search_response,
)
from oncall_app.api.static_files import read_frontend_shell
from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

router = APIRouter()


class SearchRuntime:
    """Holds mutable document and retrieval state for the API process."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.repository = DocumentRepository(data_dir)
        self.service = RetrievalService.from_documents(self.repository.all_documents())

    def reset(self) -> None:
        """Reset repository and retrieval state from disk."""
        self.repository = DocumentRepository(self.data_dir)
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Rebuild retrieval indexes from repository documents."""
        self.service = RetrievalService.from_documents(self.repository.all_documents())


runtime = SearchRuntime(DATA_DIR)


def reset_runtime() -> None:
    """Reset API runtime state."""
    runtime.reset()


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


@router.get("/v1/search")
def v1_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with BM25 lexical retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.keyword_search(query))


@router.post("/v1/documents", status_code=status.HTTP_201_CREATED)
def v1_documents(payload: DocumentCreate) -> DocumentCreated:
    """Add an SOP document to the in-memory repository and index."""
    document = runtime.repository.add_document(
        payload.id,
        payload.html,
        file_name=f"{payload.id}.html",
    )
    runtime.rebuild_index()
    return DocumentCreated(id=document.doc_id, title=document.title)


@router.get("/v2/search")
def v2_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with semantic retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.semantic_search(query))


def _normalize_query(q: str) -> str:
    """Normalize README query behavior."""
    return "&" if q == "" else q
