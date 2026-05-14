"""Pydantic schemas for HTTP APIs."""

from pydantic import BaseModel, Field

from oncall_app.models import SearchResult


class SearchResultItem(BaseModel):
    """One search result returned by the README APIs."""

    id: str
    title: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    """Search response shape."""

    query: str
    results: list[SearchResultItem]


class DocumentCreate(BaseModel):
    """Request body for adding an SOP document."""

    id: str = Field(min_length=1)
    html: str = Field(min_length=1)


class DocumentCreated(BaseModel):
    """Response body for a stored SOP document."""

    id: str
    title: str


def search_response(query: str, results: list[SearchResult]) -> SearchResponse:
    """Convert domain search results into API schema."""
    return SearchResponse(
        query=query,
        results=[
            SearchResultItem(
                id=result.doc_id,
                title=result.title,
                snippet=result.snippet,
                score=result.score,
            )
            for result in results
        ],
    )
