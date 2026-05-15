"""HTTP route orchestration for the On-Call assistant."""

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from oncall_app.agent import OnCallAgent
from oncall_app.pages import render_chat_page, render_search_page
from oncall_app.repository import DocumentRepository
from oncall_app.search import keyword_search, semantic_search


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
        self.agent = OnCallAgent(repository)

    def handle(self, method: str, target: str, body: bytes = b"") -> RouteResponse:
        """Handle one HTTP request."""
        parsed = urlsplit(target)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query, keep_blank_values=True)
        response = self._json({"error": "not found"}, status=404)

        if method == "GET" and path == "/v1":
            response = self._html(render_search_page("v1", "/v1/search", "Phase 1 关键词搜索"))
        elif method == "GET" and path == "/v1/search":
            response = self._json(self._search_payload(self._query_value(query), keyword_search))
        elif method == "POST" and path == "/v1/documents":
            response = self._create_document(body)
        elif method == "GET" and path == "/v2":
            response = self._html(render_search_page("v2", "/v2/search", "Phase 2 语义搜索"))
        elif method == "GET" and path == "/v2/search":
            response = self._json(self._search_payload(self._query_value(query), semantic_search))
        elif method == "GET" and path == "/v3":
            response = self._html(render_chat_page())
        elif method == "POST" and path == "/v3/chat":
            response = self._chat(body)
        return response

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

    def _chat(self, body: bytes) -> RouteResponse:
        """Handle POST /v3/chat."""
        try:
            payload = json.loads(body.decode("utf-8"))
            message = payload["message"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            return self._json({"error": "invalid chat payload"}, status=400)

        if not isinstance(message, str) or not message.strip():
            return self._json({"error": "invalid chat payload"}, status=400)

        response = self.agent.answer(message.strip())
        return self._json(
            {
                "answer": response.answer,
                "tool_calls": [
                    {
                        "tool": call.tool,
                        "fname": call.fname,
                        "result_preview": call.result_preview,
                    }
                    for call in response.tool_calls
                ],
            }
        )

    @staticmethod
    def _json(payload: dict[str, object], status: int = 200) -> RouteResponse:
        """Return a JSON route response."""
        return RouteResponse(status=status, body=json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _html(body: str, status: int = 200) -> RouteResponse:
        """Return an HTML route response."""
        return RouteResponse(status=status, body=body, content_type="text/html; charset=utf-8")
