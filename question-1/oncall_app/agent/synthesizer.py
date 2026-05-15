"""Evidence formatting for LLM context and fallback answers."""

from oncall_app.agent.evidence import EvidenceItem

EVIDENCE_TEXT_LIMIT = 360


def format_evidence_context(evidence: list[EvidenceItem]) -> str:
    """Format evidence sections into compact context."""
    if not evidence:
        return "No matching SOP evidence was extracted."
    lines = ["Use these SOP evidence sections when answering:"]
    for item in evidence:
        text = item.text[:EVIDENCE_TEXT_LIMIT]
        lines.append(f"- {item.file} :: {item.section_heading} :: {text}")
    return "\n".join(lines)


def fallback_answer_from_evidence(evidence: list[EvidenceItem]) -> str:
    """Build a compact local fallback answer from evidence."""
    if not evidence:
        return "没有找到足够的 SOP 依据，请补充更具体的故障现象。"
    first = evidence[0]
    return (
        f"我读取了 {first.file} 的 {first.section_heading}。"
        f"建议先按该章节处理：{first.text[:EVIDENCE_TEXT_LIMIT]}"
    )
