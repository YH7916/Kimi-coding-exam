"""Run offline acceptance evaluations."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.documents.repository import DocumentRepository
from oncall_app.evaluation.cases import MEMORY_CASES, EvalCase, load_default_cases
from oncall_app.evaluation.metrics import (
    hit_rate_at_k,
    keyword_coverage,
    memory_recall_at_1,
    mrr,
    tool_file_accuracy,
)
from oncall_app.memory.extractor import DeterministicMemoryExtractor
from oncall_app.memory.models import RawMemoryEvent
from oncall_app.memory.retrieval import MemoryRetriever
from oncall_app.memory.store import MemoryStore
from oncall_app.models import SearchResult
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class EvaluationReport:
    """Summary metrics for README-derived evaluation cases."""

    case_count: int
    v1_hit_rate_at_5: float
    v1_mrr: float
    v2_hit_rate_at_3: float
    v2_mrr: float
    v3_tool_file_accuracy: float
    v3_keyword_coverage: float
    memory_recall_at_1: float


def run_evaluation(cases: list[EvalCase] | None = None) -> EvaluationReport:
    """Run retrieval and agent evaluations without external network calls."""
    eval_cases = cases or load_default_cases()
    repository = DocumentRepository(DATA_DIR)
    service = RetrievalService.from_documents(repository.all_documents())
    assistant = OnCallAssistant(repository=repository, chat_client=LocalChatClient())

    v1_hit, v1_rank = _retrieval_metrics(
        _cases_for_phase(eval_cases, "v1"),
        service.keyword_search,
        k=5,
    )
    v2_hit, v2_rank = _retrieval_metrics(
        _cases_for_phase(eval_cases, "v2"),
        service.semantic_search,
        k=3,
    )
    v3_tool_files, v3_keywords = _agent_metrics(
        _cases_for_phase(eval_cases, "v3"),
        assistant,
        service,
    )
    memory_recall = _memory_metrics(MEMORY_CASES)

    return EvaluationReport(
        case_count=len(eval_cases) + len(MEMORY_CASES),
        v1_hit_rate_at_5=v1_hit,
        v1_mrr=v1_rank,
        v2_hit_rate_at_3=v2_hit,
        v2_mrr=v2_rank,
        v3_tool_file_accuracy=v3_tool_files,
        v3_keyword_coverage=v3_keywords,
        memory_recall_at_1=memory_recall,
    )


def format_report(report: EvaluationReport) -> str:
    """Format a compact terminal table."""
    rows = [
        ("cases", f"{report.case_count}"),
        ("v1 hit@5", _pct(report.v1_hit_rate_at_5)),
        ("v1 mrr", _pct(report.v1_mrr)),
        ("v2 hit@3", _pct(report.v2_hit_rate_at_3)),
        ("v2 mrr", _pct(report.v2_mrr)),
        ("v3 tool files", _pct(report.v3_tool_file_accuracy)),
        ("v3 keywords", _pct(report.v3_keyword_coverage)),
        ("memory recall@1", _pct(report.memory_recall_at_1)),
    ]
    width = max(len(name) for name, _ in rows)
    lines = ["Metric".ljust(width) + "  Score", "-" * (width + 7)]
    lines.extend(f"{name.ljust(width)}  {score}" for name, score in rows)
    return "\n".join(lines)


def _retrieval_batches(
    cases: list[EvalCase],
    search: Callable[[str], list[SearchResult]],
) -> tuple[list[list[str]], list[list[str]]]:
    """Run retrieval cases and return expected/actual doc id batches."""
    expected = [list(case.expected_doc_ids) for case in cases]
    actual = [[result.doc_id for result in search(case.query)] for case in cases]
    return expected, actual


def _retrieval_metrics(
    cases: list[EvalCase],
    search: Callable[[str], list[SearchResult]],
    k: int,
) -> tuple[float, float]:
    """Run retrieval cases and return hit-rate and MRR."""
    expected, actual = _retrieval_batches(cases, search)
    return hit_rate_at_k(expected, actual, k=k), mrr(expected, actual)


def _agent_metrics(
    cases: list[EvalCase],
    assistant: OnCallAssistant,
    service: RetrievalService,
) -> tuple[float, float]:
    """Run agent cases and return tool-file and keyword scores."""
    expected, actual, keywords, answers = _agent_batches(cases, assistant, service)
    return tool_file_accuracy(expected, actual), keyword_coverage(keywords, answers)


def _agent_batches(
    cases: list[EvalCase],
    assistant: OnCallAssistant,
    service: RetrievalService,
) -> tuple[list[list[str]], list[list[str]], list[list[str]], list[str]]:
    """Run agent cases and return expected/actual file and answer batches."""
    expected_files = [list(case.expected_files) for case in cases]
    actual_files = []
    expected_keywords = [list(case.must_include) for case in cases]
    answers = []
    for case in cases:
        candidates = service.semantic_search(case.query)
        response = assistant.chat(case.query, retrieval_candidates=candidates)
        actual_files.append(
            [
                call.fname
                for call in response.tool_calls
                if call.tool == "readFile"
            ]
        )
        answers.append(response.answer)
    return expected_files, actual_files, expected_keywords, answers


def _memory_metrics(cases: list[dict[str, str]]) -> float:
    """Run memory write-then-recall cases."""
    expected = []
    actual = []
    with TemporaryDirectory() as temp_dir:
        store = MemoryStore(Path(temp_dir) / "memory.sqlite3")
        extractor = DeterministicMemoryExtractor()
        retriever = MemoryRetriever(store)
        for index, case in enumerate(cases):
            event = RawMemoryEvent(
                id=f"mem-eval-{index}",
                session_id="eval",
                user_message=case["write"],
                assistant_answer="已记录。",
            )
            store.add_event(event)
            for memory in extractor.extract(event):
                store.upsert_memory(memory)
            hits = retriever.search(case["recall"], limit=1)
            expected.append(case["expected_memory"])
            actual.append(hits[0].record.summary if hits else "")
    return memory_recall_at_1(expected, actual)


def _cases_for_phase(cases: list[EvalCase], phase: str) -> list[EvalCase]:
    """Return cases for one phase."""
    return [case for case in cases if case.phase == phase]


def _pct(score: float) -> str:
    """Format a 0..1 score."""
    return f"{score:.2f}"
