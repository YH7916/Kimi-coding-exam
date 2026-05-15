export const MODES = {
  v1: {
    endpoint: "/v1/search",
    kicker: "v1 Search",
    title: "Search the SOPs",
    subtitle: "关键词匹配，适合 OOM、CDN、P0 这类明确线索。",
    placeholder: "OOM / CDN / P0",
    resultTitle: "Keyword matches",
  },
  v2: {
    endpoint: "/v2/search",
    kicker: "v2 RAG",
    title: "Ask for evidence",
    subtitle: "语义检索相关 SOP 片段，不生成最终处置结论。",
    placeholder: "服务器挂了，先查什么？",
    resultTitle: "Retrieved evidence",
  },
  v3: {
    endpoint: "/v3/chat",
    streamEndpoint: "/v3/chat/stream",
    kicker: "v3 Agent",
    title: "Ask the agent",
    subtitle: "读取 SOP，生成回答，并展示工具调用。",
    placeholder: "P0 故障的响应流程是什么？",
    resultTitle: "Agent response",
  },
};

export const MAX_HISTORY_ENTRIES = 24;

export function modeFromPath(pathname) {
  if (pathname === "/v1") {
    return "v1";
  }
  if (pathname === "/v2") {
    return "v2";
  }
  return "v3";
}
