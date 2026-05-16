import { escapeHtml } from "./markdown.js";
import { renderMemoryTrace } from "./memory.js";

export function renderInlineTrace(turn, showTrace) {
  const trace = showTrace ? turn.trace || [] : [];
  if (!trace.length) {
    return "";
  }
  const toolCallCount = (turn.toolCalls || []).length;
  const hasEvidence = (turn.evidence || []).length > 0;
  const memoryTrace = renderMemoryTrace(turn.memoryHits || []);
  if (!toolCallCount && !hasEvidence && turn.streaming) {
    return "";
  }
  const visibleTrace = trace.filter((item) => item.type !== "answer").slice(0, 4);
  if (!visibleTrace.length && !toolCallCount) {
    return "";
  }
  const workflowSteps = [
    ...visibleTrace.map((item) => ({
      label: compactTraceType(item.type),
      message: compactTraceMessage(item.message),
    })),
  ];
  if (turn.content || turn.streaming) {
    workflowSteps.push({
      label: "输出",
      message: turn.streaming ? "正在生成回答" : "回答已生成",
    });
  }
  return `
    <section class="inline-trace" aria-label="工具调用过程">
      <div class="inline-trace-header">
        <span>过程</span>
        <small>${toolCallCount ? `${toolCallCount} 次 readFile` : "检索完成"}</small>
      </div>
      <ol class="inline-trace-list">
        ${workflowSteps.map((item, index) => `
          <li class="inline-trace-step ${turn.streaming && index === workflowSteps.length - 1 ? "is-active" : ""}" style="--i: ${index}">
            <span class="inline-trace-dot" aria-hidden="true"></span>
            <div>
              <strong>${escapeHtml(item.label)}</strong>
              <p>${escapeHtml(item.message)}</p>
            </div>
          </li>
        `).join("")}
      </ol>
      ${memoryTrace}
    </section>
  `;
}

function compactTraceType(type) {
  if (type === "tool_call") {
    return "readFile";
  }
  if (type === "retrieval") {
    return "检索";
  }
  if (type === "memory") {
    return "记忆";
  }
  if (type === "observation") {
    return "读取";
  }
  if (type === "evidence") {
    return "证据";
  }
  if (type === "warning") {
    return "提示";
  }
  if (type === "error") {
    return "错误";
  }
  return String(type || "trace");
}

function compactTraceMessage(message) {
  return String(message || "")
    .replace("v2 hybrid retrieval candidates: ", "")
    .replace(" cited sections extracted", " sections")
    .replace(" loaded", "");
}
