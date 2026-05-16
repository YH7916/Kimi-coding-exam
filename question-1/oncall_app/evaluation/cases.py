"""Evaluation case definitions for README behavior."""

from dataclasses import dataclass, field
from typing import Literal

EvalPhase = Literal["v1", "v2", "v3"]

MEMORY_CASES = [
    {
        "write": "记住：支付服务负责人是小王，升级群是 #pay-oncall。",
        "recall": "支付服务报警应该找谁？",
        "expected_memory": "支付服务负责人",
    }
]


@dataclass(frozen=True)
class EvalCase:
    """One retrieval or agent evaluation case."""

    phase: EvalPhase
    query: str
    expected_doc_ids: tuple[str, ...] = field(default_factory=tuple)
    expected_files: tuple[str, ...] = field(default_factory=tuple)
    must_include: tuple[str, ...] = field(default_factory=tuple)


def load_default_cases() -> list[EvalCase]:
    """Return README-derived acceptance cases."""
    return [
        EvalCase("v1", "OOM", expected_doc_ids=("sop-001",)),
        EvalCase(
            "v1",
            "故障",
            expected_doc_ids=("sop-001", "sop-002", "sop-003", "sop-004"),
        ),
        EvalCase("v1", "replication", expected_doc_ids=()),
        EvalCase("v1", "CDN", expected_doc_ids=("sop-003", "sop-010")),
        EvalCase("v1", "&", expected_doc_ids=("sop-003", "sop-010")),
        EvalCase("v2", "服务器挂了", expected_doc_ids=("sop-001", "sop-004")),
        EvalCase("v2", "黑客攻击", expected_doc_ids=("sop-005",)),
        EvalCase("v2", "机器学习模型出问题", expected_doc_ids=("sop-008",)),
        EvalCase(
            "v3",
            "数据库主从延迟超过30秒怎么处理？",
            expected_files=("sop-002.html",),
            must_include=("主从", "延迟"),
        ),
        EvalCase(
            "v3",
            "服务 OOM 了怎么办？",
            expected_files=("sop-001.html",),
            must_include=("堆转储", "JVM"),
        ),
        EvalCase(
            "v3",
            "P0 故障的响应流程是什么？",
            expected_files=("sop-001.html", "sop-002.html", "sop-005.html"),
            must_include=("P0", "升级"),
        ),
        EvalCase(
            "v3",
            "怀疑有人入侵了系统",
            expected_files=("sop-005.html",),
            must_include=("隔离", "证据"),
        ),
        EvalCase(
            "v3",
            "推荐结果质量下降了",
            expected_files=("sop-008.html",),
            must_include=("推荐", "模型"),
        ),
    ]
