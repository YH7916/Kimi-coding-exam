"""HTTP route orchestration for the On-Call assistant."""

from dataclasses import dataclass
import json
from urllib.parse import parse_qs, urlsplit

from oncall_app.pages import render_search_page
from oncall_app.repository import DocumentRepository
from oncall_app.search import keyword_search


@dataclass(frozen=True)
class RouteResponse:
    """A route-layer HTTP response."""

    status: int
    body: str
    content_type: str = "application/json; charset=utf-8"


class Router:  # pylint: disable=too-few-public-methods
    """Map HTTP methods and paths to application behavior."""

    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    def handle(self, method: str, target: str, body: bytes = b"") -> RouteResponse:
        """Handle one HTTP request."""
        parsed = urlsplit(target)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query, keep_blank_values=True)

        if method == "GET" and path == "/v1":
            return self._html(render_search_page("v1", "/v1/search", "Phase 1 关键词搜索"))
        if method == "GET" and path == "/v1/search":
            return self._json(self._search_payload(self._query_value(query), keyword_search))
        if method == "POST" and path == "/v1/documents":
            return self._create_document(body)
        if method == "GET" and path == "/v2":
            return self._html(render_search_page("v2", "/v2/search", "Phase 2 语义搜索"))
        return self._json({"error": "not found"}, status=404)

    @staticmethod
    def _query_value(query: dict[str, list[str]]) -> str:
        """Extract q from parsed query values, matching README's q=& ampersand case."""
        raw_value = query.get("q", [""])[0]
        return raw_value if raw_value else "&"

    def _search_payload(self, query: str, search_function) -> dict[str, object]:
        """Build the common search response payload."""
        results = search_function(self.repository.all_documents(), query)
        return {
            "query": query,
            "results": [
                {
                    "id": result.doc_id,
                    "title": result.title,
                    "snippet": result.snippet,
                    "score": result.score,
                }
                for result in results
            ],
        }

    def _create_document(self, body: bytes) -> RouteResponse:
        """Handle POST /v1/documents."""
        try:
            payload = json.loads(body.decode("utf-8"))
            doc_id = payload["id"]
            html = payload["html"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            return self._json({"error": "invalid document payload"}, status=400)

        if not isinstance(doc_id, str) or not isinstance(html, str) or not doc_id.strip():
            return self._json({"error": "invalid document payload"}, status=400)

        document = self.repository.add_document(doc_id.strip(), html)
        return self._json({"id": document.doc_id, "title": document.title}, status=201)

    @staticmethod
    def _json(payload: dict[str, object], status: int = 200) -> RouteResponse:
        """Return a JSON route response."""
        return RouteResponse(status=status, body=json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _html(body: str, status: int = 200) -> RouteResponse:
        """Return an HTML route response."""
        return RouteResponse(status=status, body=body, content_type="text/html; charset=utf-8")
