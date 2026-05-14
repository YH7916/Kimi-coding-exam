"""Deterministic semantic fallback for no-key local runs."""

from typing import TypedDict

from oncall_app.models import Document, SearchResult

SNIPPET_RADIUS = 48
DEFAULT_LIMIT = 10


class SemanticRule(TypedDict):
    """A deterministic semantic expansion rule."""

    triggers: tuple[str, ...]
    required_any: tuple[str, ...]
    boosts: dict[str, float]
    terms: tuple[str, ...]


SEMANTIC_RULES: tuple[SemanticRule, ...] = (
    {
        "triggers": ("服务器挂了", "服务挂了", "宕机", "不可用", "服务异常"),
        "required_any": ("服务器", "服务", "挂", "宕机", "不可用"),
        "boosts": {"sop-001": 35.0, "sop-004": 34.0},
        "terms": ("服务", "超时", "故障", "Kubernetes", "K8s", "集群", "告警", "后端", "SRE"),
    },
    {
        "triggers": ("黑客攻击", "入侵", "被黑", "攻击", "漏洞"),
        "required_any": ("黑客", "攻击", "入侵", "漏洞"),
        "boosts": {"sop-005": 40.0, "sop-010": 8.0},
        "terms": ("安全", "入侵", "攻击", "漏洞", "事件", "DDoS", "SQL注入", "XSS"),
    },
    {
        "triggers": ("机器学习模型", "模型出问题", "推荐结果", "推荐质量", "推理"),
        "required_any": ("模型", "机器学习", "推荐", "算法", "推理"),
        "boosts": {"sop-008": 42.0},
        "terms": ("模型", "推理", "推荐", "质量", "GPU", "算法", "AI", "特征"),
    },
)


def semantic_fallback_search(
    documents: list[Document],
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    """Search documents with deterministic semantic expansion."""
    normalized_query = query.strip()
    if not normalized_query:
        return []

    terms, boosts = _semantic_terms_and_boosts(normalized_query)
    results = []
    for document in documents:
        score = boosts.get(document.doc_id, 0.0)
        for term in terms:
            score += _count_occurrences(document.title, term) * 3.0
            score += _count_occurrences(document.text, term) * 0.7
        if score <= 0:
            continue
        results.append(
            SearchResult(
                doc_id=document.doc_id,
                title=document.title,
                snippet=_best_snippet_for_terms(document, terms),
                score=round(score, 2),
            )
        )
    return sorted(results, key=lambda result: (-result.score, result.doc_id))[:limit]


def _casefold(value: str) -> str:
    """Return a case-insensitive comparison form."""
    return value.casefold()


def _count_occurrences(value: str, query: str) -> int:
    """Count non-overlapping case-insensitive query occurrences."""
    if not query:
        return 0
    return _casefold(value).count(_casefold(query))


def _semantic_terms_and_boosts(query: str) -> tuple[list[str], dict[str, float]]:
    """Expand a query into semantic terms and per-document boosts."""
    terms = [query]
    boosts: dict[str, float] = {}
    for rule in SEMANTIC_RULES:
        if not _rule_matches(rule, query):
            continue
        terms.extend(rule["terms"])
        for doc_id, boost in rule["boosts"].items():
            boosts[doc_id] = boosts.get(doc_id, 0.0) + float(boost)
    return terms, boosts


def _rule_matches(rule: SemanticRule, query: str) -> bool:
    """Return whether a semantic rule applies to a query."""
    folded_query = _casefold(query)
    return any(_casefold(term) in folded_query for term in rule["triggers"]) or any(
        _casefold(term) in folded_query for term in rule["required_any"]
    )


def _best_snippet_for_terms(document: Document, terms: list[str]) -> str:
    """Return a snippet for the first semantic term found in a document."""
    for term in terms:
        if _casefold(term) in _casefold(document.title) or _casefold(term) in _casefold(
            document.text
        ):
            return _make_snippet(document, term)
    return document.text[: SNIPPET_RADIUS * 2]


def _make_snippet(document: Document, query: str) -> str:
    """Build a compact snippet around the first query match."""
    for source in (document.text, document.title):
        index = _casefold(source).find(_casefold(query))
        if index >= 0:
            start = max(0, index - SNIPPET_RADIUS)
            end = min(len(source), index + len(query) + SNIPPET_RADIUS)
            prefix = "..." if start else ""
            suffix = "..." if end < len(source) else ""
            return f"{prefix}{source[start:end]}{suffix}"
    return document.text[: SNIPPET_RADIUS * 2]
