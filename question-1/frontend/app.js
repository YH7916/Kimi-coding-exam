const app = document.querySelector("#app");

const MODES = {
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

function modeFromPath(pathname) {
  if (pathname === "/v1") {
    return "v1";
  }
  if (pathname === "/v2") {
    return "v2";
  }
  return "v3";
}

let mode = modeFromPath(window.location.pathname);
let config = MODES[mode];
const chatTurns = [];
const SETTINGS_STORAGE_KEY = "oncall-copilot-settings";
const userSettings = loadUserSettings();
let pendingAssistantContentTurn = null;
let pendingAssistantContentFrame = 0;

function isActiveChat() {
  return mode === "v3" && chatTurns.length > 0;
}

function hasPendingChatTurn() {
  return chatTurns.some((turn) => turn.role === "pending" || turn.streaming);
}

function loadUserSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || "{}");
    return {
      showTrace: saved.showTrace !== false,
      sectionJump: saved.sectionJump !== false,
    };
  } catch (_error) {
    return { showTrace: true, sectionJump: true };
  }
}

function saveUserSettings() {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(userSettings));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  const codeSpans = [];
  let rendered = escapeHtml(value).replace(/`([^`]+)`/g, (_match, code) => {
    const placeholder = `%%CODESPAN${codeSpans.length}%%`;
    codeSpans.push(`<code>${code}</code>`);
    return placeholder;
  });

  rendered = rendered
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/(\*\*|__)(.+?)\1/g, "<strong>$2</strong>")
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

  codeSpans.forEach((code, index) => {
    rendered = rendered.replaceAll(`%%CODESPAN${index}%%`, code);
  });
  return rendered;
}

function renderMarkdown(value) {
  const lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = "";
  let inCodeBlock = false;
  let codeLines = [];

  const closeParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${paragraph.join("<br>")}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) {
      return;
    }
    html.push(`</${listType}>`);
    listType = "";
  };

  const openList = (nextListType) => {
    closeParagraph();
    if (listType === nextListType) {
      return;
    }
    closeList();
    listType = nextListType;
    html.push(`<${listType}>`);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCodeBlock = false;
      } else {
        closeParagraph();
        closeList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      closeParagraph();
      closeList();
      continue;
    }

    if (/^([-*_])(?:\s*\1){2,}$/.test(trimmed)) {
      closeParagraph();
      closeList();
      html.push("<hr>");
      continue;
    }

    if (looksLikeTableStart(lines, index)) {
      closeParagraph();
      closeList();
      const table = collectMarkdownTable(lines, index);
      html.push(renderMarkdownTable(table.headers, table.rows));
      index = table.nextIndex - 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/);
    if (heading) {
      closeParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 6);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = trimmed.match(/^>\s?(.+)$/);
    if (quote) {
      closeParagraph();
      closeList();
      html.push(`<blockquote><p>${renderInlineMarkdown(quote[1])}</p></blockquote>`);
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      openList("ul");
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      openList("ol");
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(renderInlineMarkdown(trimmed));
  }

  if (inCodeBlock) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  closeParagraph();
  closeList();
  return html.join("");
}

function splitMarkdownTableRow(line) {
  let row = line.trim();
  if (row.startsWith("|")) {
    row = row.slice(1);
  }
  if (row.endsWith("|")) {
    row = row.slice(0, -1);
  }
  return row.split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function looksLikeTableStart(lines, index) {
  const current = lines[index] || "";
  const next = lines[index + 1] || "";
  return current.includes("|") && isMarkdownTableSeparator(next);
}

function collectMarkdownTable(lines, startIndex) {
  const headers = splitMarkdownTableRow(lines[startIndex]);
  const rows = [];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(splitMarkdownTableRow(lines[index]));
    index += 1;
  }
  return { headers, rows, nextIndex: index };
}

function renderMarkdownTable(headers, rows) {
  const headerHtml = headers
    .map((header) => `<th>${renderInlineMarkdown(header)}</th>`)
    .join("");
  const bodyHtml = rows
    .map((row) => `
      <tr>
        ${headers.map((_header, index) => `<td>${renderInlineMarkdown(row[index] || "")}</td>`).join("")}
      </tr>
    `)
    .join("");
  return `
    <div class="markdown-table-wrap">
      <table>
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </div>
  `;
}

function scoreLabel(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) {
    return String(score);
  }
  return numeric.toFixed(numeric >= 10 ? 0 : 2);
}

async function refreshProviderStatus() {
  try {
    const response = await fetch("/provider-status");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    renderProviderStatus(await response.json());
  } catch (_error) {
    renderProviderStatus(null);
  }
}

function renderProviderStatus(status) {
  const summary = document.querySelector("#settings-summary");
  const details = document.querySelector("#provider-status-details");
  const button = document.querySelector("#settings-button");
  if (!summary || !details || !button) {
    return;
  }

  if (!status) {
    summary.textContent = "状态不可用";
    details.innerHTML = `<p>状态暂时不可用。</p>`;
    return;
  }

  const embeddingMode = status.embedding?.mode || "fallback";
  const chatMode = status.chat?.mode || "fallback";
  const isAllReal = embeddingMode === "real" && chatMode === "real";
  button.title = isAllReal ? "模型服务已连接" : "部分能力使用本地模式";
  summary.textContent = isAllReal ? "模型服务已连接" : "部分本地模式";
  details.innerHTML = `
    ${renderProviderRow("向量检索", status.embedding, "SiliconFlow Embedding")}
    ${renderProviderRow("对话模型", status.chat, "OpenAI Chat Completions")}
    ${renderCacheRow(status.cache || {})}
  `;
}

function renderProviderRow(label, item, realLabel) {
  const mode = item?.mode || "fallback";
  const isReal = mode === "real";
  const model = item?.model ? `<small>${escapeHtml(item.model)}</small>` : "";
  return `
    <article class="provider-row">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(isReal ? realLabel : "本地兜底")}</span>
        ${model}
      </div>
      <mark class="${isReal ? "is-real" : ""}">${isReal ? "已连接" : "本地"}</mark>
    </article>
  `;
}

function renderCacheRow(cache) {
  if (!cache.enabled) {
    return `
      <article class="provider-row">
        <div>
          <strong>向量缓存</strong>
          <span>当前未启用</span>
        </div>
        <mark>关闭</mark>
      </article>
    `;
  }
  return `
    <article class="provider-row">
      <div>
        <strong>向量缓存</strong>
        <span>${escapeHtml(cache.entries || 0)} 条向量，命中 ${escapeHtml(cache.hits || 0)} 次</span>
      </div>
      <mark class="is-real">开启</mark>
    </article>
  `;
}

function sopIdFromFile(value) {
  return String(value || "").replace(/\.html$/i, "");
}

function sectionKey(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function setActiveNav() {
  const switcher = document.querySelector(".version-switcher");
  if (switcher) {
    switcher.dataset.active = mode;
  }
  document.querySelectorAll(".version-switcher a").forEach((item) => {
    const isActive = item.dataset.mode === mode;
    item.classList.toggle("is-active", isActive);
    if (isActive) {
      item.setAttribute("aria-current", "page");
    } else {
      item.removeAttribute("aria-current");
    }
  });
}

function switchMode(nextMode, pushState = false) {
  if (!MODES[nextMode]) {
    return;
  }
  mode = nextMode;
  config = MODES[mode];
  if (pushState) {
    window.history.pushState({}, "", `/${mode}`);
  }
  setActiveNav();
  renderShell();
}

function setupNavigation() {
  const switcher = document.querySelector(".version-switcher");
  if (!switcher) {
    return;
  }

  switcher.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const link = event.target.closest("a[data-mode]");
    if (!link) {
      return;
    }
    event.preventDefault();
    const nextMode = link.dataset.mode;
    if (nextMode === mode) {
      return;
    }
    switchMode(nextMode, true);
  });

  window.addEventListener("popstate", () => {
    switchMode(modeFromPath(window.location.pathname));
  });
}

function setupSettingsPopover() {
  const button = document.querySelector("#settings-button");
  const popover = document.querySelector("#settings-popover");
  const showTrace = document.querySelector("#setting-show-trace");
  const sectionJump = document.querySelector("#setting-section-jump");
  if (!button || !popover || !showTrace || !sectionJump) {
    return;
  }

  showTrace.checked = userSettings.showTrace;
  sectionJump.checked = userSettings.sectionJump;

  button.addEventListener("click", () => {
    const isOpening = popover.hidden;
    popover.hidden = !isOpening;
    button.setAttribute("aria-expanded", String(isOpening));
  });

  showTrace.addEventListener("change", () => {
    userSettings.showTrace = showTrace.checked;
    saveUserSettings();
    if (isActiveChat()) {
      renderChatConversation();
    }
  });

  sectionJump.addEventListener("change", () => {
    userSettings.sectionJump = sectionJump.checked;
    saveUserSettings();
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    if (popover.hidden || button.contains(event.target) || popover.contains(event.target)) {
      return;
    }
    popover.hidden = true;
    button.setAttribute("aria-expanded", "false");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || popover.hidden) {
      return;
    }
    popover.hidden = true;
    button.setAttribute("aria-expanded", "false");
  });
}

function renderShell() {
  const activeChat = isActiveChat();
  document.body.classList.toggle("chat-active", activeChat);
  app.innerHTML = activeChat ? renderChatShell() : renderHomeShell();

  const form = document.querySelector("#query-form");
  const textarea = form.querySelector("textarea");
  const submitButton = form.querySelector(".send-button");
  let isSubmitting = false;
  submitButton.disabled = mode === "v3" && hasPendingChatTurn();

  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  });

  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    form.requestSubmit();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isSubmitting || (mode === "v3" && hasPendingChatTurn())) {
      return;
    }
    const q = new FormData(event.target).get("q") || "";
    if (!String(q).trim()) {
      textarea.focus();
      return;
    }
    isSubmitting = true;
    submitButton.disabled = true;
    if (mode === "v3") {
      textarea.value = "";
      textarea.style.height = "auto";
    }
    try {
      if (mode === "v3") {
        await submitChat(q);
      } else {
        await submitSearch(q);
      }
    } finally {
      isSubmitting = false;
      submitButton.disabled = mode === "v3" && hasPendingChatTurn();
    }
  });

  if (activeChat) {
    renderChatConversation();
  }
}

function renderHomeShell() {
  return `
    <section class="home">
      <p class="kicker">${escapeHtml(config.kicker)}</p>
      <h1>${escapeHtml(config.title)}</h1>
      <p class="subtitle">${escapeHtml(config.subtitle)}</p>
      <form id="query-form" class="query-box">
        <textarea name="q" rows="1" placeholder="${escapeHtml(config.placeholder)}" autofocus></textarea>
        <button class="send-button" type="submit" aria-label="Submit query">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 19V5"></path>
            <path d="m5 12 7-7 7 7"></path>
          </svg>
        </button>
      </form>
    </section>
    <section id="results" class="results" aria-label="${escapeHtml(config.resultTitle)}"></section>
  `;
}

function renderChatShell() {
  return `
    <section class="chat-screen">
      <section id="results" class="results chat-results" aria-label="${escapeHtml(config.resultTitle)}"></section>
      <form id="query-form" class="query-box chat-composer">
        <textarea name="q" rows="1" placeholder="继续追问 SOP，或要求展开某个步骤" autofocus></textarea>
        <button class="send-button" type="submit" aria-label="Submit query">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 19V5"></path>
            <path d="m5 12 7-7 7 7"></path>
          </svg>
        </button>
      </form>
    </section>
  `;
}

function renderLoading(label) {
  document.querySelector("#results").innerHTML = `
    <div class="loading-row result-enter">
      <span class="spinner" aria-hidden="true"></span>
      <span>${escapeHtml(label)}</span>
    </div>
  `;
}

function renderError(message) {
  document.querySelector("#results").innerHTML = `
    <article class="notice-card">
      <strong>Request failed</strong>
      <p>${escapeHtml(message)}</p>
    </article>
  `;
}

async function submitSearch(q) {
  renderLoading(mode === "v1" ? "Searching keywords" : "Retrieving evidence");
  try {
    const response = await fetch(`${config.endpoint}?q=${encodeURIComponent(q)}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    renderSearchResults(payload.results || []);
    refreshProviderStatus();
  } catch (error) {
    renderError(error.message || "Unknown error");
  }
}

function renderSearchResults(results) {
  const displayedResults = results.slice(0, 3);
  const empty = `
    <article class="notice-card result-enter">
      <strong>No matching SOP found</strong>
      <p>Try a concrete incident keyword such as OOM, CDN, P0, 黑客攻击, or 模型。</p>
    </article>
  `;

  document.querySelector("#results").innerHTML = `
    <div class="section-heading result-enter">
      <h2>${escapeHtml(config.resultTitle)}</h2>
      <span>${displayedResults.length ? `${displayedResults.length} shown` : "empty"}</span>
    </div>
    <div class="result-list">
      ${
        displayedResults.length
          ? displayedResults
              .map(
                (item, index) => `
                  <button type="button" class="result-row sop-open-button" data-sop-id="${escapeHtml(item.id)}" style="--i: ${index}">
                    <span class="result-index">${index + 1}</span>
                    <div>
                      <h3>${escapeHtml(item.title)}</h3>
                      <p>${escapeHtml(item.snippet)}</p>
                      <small>${escapeHtml(item.id)} · score ${escapeHtml(scoreLabel(item.score))}</small>
                    </div>
                  </button>
                `,
              )
              .join("")
          : empty
      }
    </div>
  `;
}

async function submitChat(message) {
  const history = visibleChatHistory();
  chatTurns.push({ role: "user", content: String(message) });
  const assistantTurn = {
    role: "assistant",
    content: "",
    evidence: [],
    trace: [],
    toolCalls: [],
    streaming: true,
  };
  chatTurns.push(assistantTurn);
  renderShell();
  try {
    const response = await fetch(config.streamEndpoint || `${config.endpoint}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    await readSseStream(response, (event) => {
      const renderMode = applyChatStreamEvent(assistantTurn, event);
      if (renderMode === "content") {
        scheduleAssistantContentUpdate(assistantTurn);
        return;
      }
      cancelAssistantContentUpdate();
      renderChatConversation();
    });
    assistantTurn.streaming = false;
    renderShell();
  } catch (error) {
    applyChatFailure(assistantTurn, error.message || "Unknown error");
    renderShell();
  } finally {
    refreshProviderStatus();
  }
}

function visibleChatHistory() {
  return chatTurns
    .filter((turn) => turn.role === "user" || turn.role === "assistant")
    .map((turn) => ({ role: turn.role, content: turn.content }));
}

function removePendingTurn() {
  for (let index = chatTurns.length - 1; index >= 0; index -= 1) {
    if (chatTurns[index].role === "pending") {
      chatTurns.splice(index, 1);
      return;
    }
  }
}

async function readSseStream(response, onEvent) {
  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    frames.forEach((frame) => {
      const event = parseSseFrame(frame);
      if (event) {
        onEvent(event);
      }
    });
  }

  const tail = buffer.trim();
  if (tail) {
    const event = parseSseFrame(tail);
    if (event) {
      onEvent(event);
    }
  }
}

function parseSseFrame(frame) {
  let type = "message";
  const dataLines = [];
  frame.split("\n").forEach((line) => {
    if (line.startsWith("event:")) {
      type = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  });
  if (!dataLines.length) {
    return null;
  }
  return { type, data: JSON.parse(dataLines.join("\n")) };
}

function applyChatStreamEvent(turn, event) {
  const data = event.data || {};
  if (event.type === "retrieval") {
    const files = (data.candidates || []).map((item) => item.file).join(", ");
    turn.trace = [
      ...(turn.trace || []),
      { type: "retrieval", message: files ? `v2 hybrid retrieval candidates: ${files}` : "no candidates" },
    ];
    return "full";
  }
  if (event.type === "tool_call") {
    turn.toolCalls = [...(turn.toolCalls || []), { tool: data.tool || "readFile", fname: data.fname || "" }];
    turn.trace = [
      ...(turn.trace || []),
      { type: "tool_call", message: `readFile("${data.fname || ""}")` },
    ];
    return "full";
  }
  if (event.type === "observation") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "observation", message: `${data.fname || "SOP"} loaded (${data.chars || 0} chars)` },
    ];
    return "full";
  }
  if (event.type === "evidence") {
    turn.evidence = data.items || [];
    turn.trace = [
      ...(turn.trace || []),
      { type: "evidence", message: `${turn.evidence.length} cited sections extracted` },
    ];
    return "full";
  }
  if (event.type === "answer_delta") {
    turn.content = `${turn.content || ""}${data.delta || ""}`;
    return "content";
  }
  if (event.type === "done") {
    turn.streaming = false;
    turn.content = data.answer || turn.content || "";
    turn.evidence = data.evidence || turn.evidence || [];
    turn.trace = data.trace || turn.trace || [];
    turn.toolCalls = data.tool_calls || turn.toolCalls || [];
    return "full";
  }
  if (event.type === "warning") {
    turn.trace = [
      ...(turn.trace || []),
      { type: "warning", message: data.message || "Agent finished with a fallback answer" },
    ];
    return "full";
  }
  if (event.type === "error") {
    applyChatFailure(turn, data.message || "Streaming request failed");
  }
  return "full";
}

function applyChatFailure(turn, message) {
  turn.streaming = false;
  if (hasPartialAgentState(turn)) {
    turn.trace = [
      ...(turn.trace || []),
      { type: "error", message },
    ];
    if (!turn.content) {
      turn.content = "模型生成最终回答时失败，但已经保留上方读取到的 SOP 证据和工具调用过程。";
    }
    return;
  }
  turn.role = "error";
  turn.content = message;
}

function hasPartialAgentState(turn) {
  return Boolean(
    turn.content
      || (turn.evidence || []).length
      || (turn.trace || []).length
      || (turn.toolCalls || []).length,
  );
}

function streamingPlaceholder(turn) {
  if ((turn.evidence || []).length) {
    return "已读取 SOP 证据，正在生成回答...";
  }
  if ((turn.toolCalls || []).length) {
    return "正在读取相关 SOP...";
  }
  if ((turn.trace || []).length) {
    return "正在检索相关 SOP...";
  }
  return "Retrieving SOP evidence...";
}

function latestAssistantTurn() {
  for (let index = chatTurns.length - 1; index >= 0; index -= 1) {
    if (chatTurns[index].role === "assistant") {
      return chatTurns[index];
    }
  }
  return null;
}

function renderChatConversation() {
  const latest = latestAssistantTurn();
  const trace = latest?.trace || [];
  const toolCalls = latest?.toolCalls || [];
  const tracePanel = userSettings.showTrace
    ? `
      <aside class="trace-panel">
        <div class="section-heading">
          <h2>Trace</h2>
          <span>${toolCalls.length} tool calls</span>
        </div>
        <div class="trace-list">
          ${renderTrace(trace)}
        </div>
      </aside>
    `
    : "";

  document.querySelector("#results").innerHTML = `
    <div class="agent-layout chat-agent-layout ${userSettings.showTrace ? "" : "is-trace-hidden"} result-enter">
      <section class="answer-panel chat-thread-panel">
        <div class="chat-list">
          ${chatTurns.map((turn, index) => renderChatTurn(turn, index)).join("")}
        </div>
      </section>
      ${tracePanel}
    </div>
  `;
}

function scheduleAssistantContentUpdate(turn) {
  pendingAssistantContentTurn = turn;
  if (pendingAssistantContentFrame) {
    return;
  }
  pendingAssistantContentFrame = window.requestAnimationFrame(() => {
    pendingAssistantContentFrame = 0;
    if (pendingAssistantContentTurn) {
      updateAssistantContent(pendingAssistantContentTurn);
    }
    pendingAssistantContentTurn = null;
  });
}

function cancelAssistantContentUpdate() {
  if (pendingAssistantContentFrame) {
    window.cancelAnimationFrame(pendingAssistantContentFrame);
    pendingAssistantContentFrame = 0;
  }
  pendingAssistantContentTurn = null;
}

function updateAssistantContent(turn) {
  const index = chatTurns.indexOf(turn);
  const body = document.querySelector(
    `.chat-message-assistant[data-turn-index="${index}"] .markdown-body`,
  );
  if (!body) {
    renderChatConversation();
    return;
  }
  body.innerHTML = renderAssistantBody(turn);
}

function renderChatTurn(turn, index) {
  if (turn.role === "pending") {
    return `
      <div class="loading-row chat-loading" style="--i: ${index}">
        <span class="spinner" aria-hidden="true"></span>
        <span>${escapeHtml(turn.content)}</span>
      </div>
    `;
  }
  if (turn.role === "error") {
    return `
      <article class="notice-card chat-message" style="--i: ${index}">
        <strong>Request failed</strong>
        <p>${escapeHtml(turn.content)}</p>
      </article>
    `;
  }
  if (turn.role === "user") {
    return `
      <article class="chat-message chat-message-user" style="--i: ${index}">
        <small>You</small>
        <p>${escapeHtml(turn.content)}</p>
      </article>
    `;
  }
  return `
    <article class="chat-message chat-message-assistant" data-turn-index="${index}" style="--i: ${index}">
      <small>Assistant</small>
      <div class="markdown-body">${renderAssistantBody(turn)}</div>
      ${renderEvidence(turn.evidence || [])}
    </article>
  `;
}

function renderAssistantBody(turn) {
  return `
    ${
      turn.content
        ? renderMarkdown(turn.content)
        : `<p class="stream-placeholder">${escapeHtml(streamingPlaceholder(turn))}</p>`
    }
    ${turn.streaming ? `<span class="stream-cursor" aria-hidden="true"></span>` : ""}
  `;
}

function renderTrace(trace) {
  if (!trace.length) {
    return `
      <article class="trace-item">
        <span>conversation</span>
        <p>Ask a question to see retrieval and readFile calls.</p>
      </article>
    `;
  }
  return trace.map((item, index) => `
    <article class="trace-item" style="--i: ${index}">
      <span>${escapeHtml(item.type)}</span>
      <p>${escapeHtml(item.message)}</p>
    </article>
  `).join("");
}

function renderEvidence(evidence) {
  if (!evidence.length) {
    return "";
  }
  const cards = evidence.slice(0, 6);
  return `
    <section class="evidence-section" aria-label="引用 SOP">
      <div class="evidence-section-header">
        <span>引用 SOP</span>
        <small>${cards.length} 条</small>
      </div>
      <div class="evidence-strip">
        ${cards.map((item, index) => `
        <button
          type="button"
          class="evidence-card sop-open-button"
          data-sop-id="${escapeHtml(sopIdFromFile(item.file))}"
          data-sop-section="${escapeHtml(item.section)}"
          style="--i: ${index}"
        >
          <small>${escapeHtml(item.file)}</small>
          <h3>${escapeHtml(item.section)}</h3>
          <p>${escapeHtml(item.text)}</p>
        </button>
        `).join("")}
      </div>
    </section>
  `;
}

function setupSopPreview() {
  app.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const trigger = event.target.closest("[data-sop-id]");
    if (!trigger) {
      return;
    }
    event.preventDefault();
    openSopModal(trigger.dataset.sopId || "", trigger.dataset.sopSection || "");
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    if (event.target.matches("[data-modal-close]")) {
      closeSopModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSopModal();
    }
  });
}

async function openSopModal(rawId, targetSection = "") {
  const docId = sopIdFromFile(rawId);
  if (!docId) {
    return;
  }
  renderSopModal(`
    <header class="sop-modal-header">
      <div>
        <p>SOP preview</p>
        <h2 id="sop-modal-title">${escapeHtml(docId)}.html</h2>
      </div>
      <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
    </header>
    <div class="sop-modal-status">
      <span class="spinner" aria-hidden="true"></span>
      <span>Loading source</span>
    </div>
  `);

  try {
    const response = await fetch(`/documents/${encodeURIComponent(docId)}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const documentDetail = await response.json();
    renderSopModal(renderSopDocument(documentDetail, targetSection));
    scrollToSopSection(targetSection);
  } catch (error) {
    renderSopModal(`
      <header class="sop-modal-header">
        <div>
          <p>SOP preview</p>
          <h2 id="sop-modal-title">Unable to open ${escapeHtml(docId)}.html</h2>
        </div>
        <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
      </header>
      <div class="sop-modal-body">
        <article class="notice-card">
          <strong>Request failed</strong>
          <p>${escapeHtml(error.message || "Unknown error")}</p>
        </article>
      </div>
    `);
  }
}

function renderSopModal(innerHtml) {
  let root = document.querySelector("#sop-modal-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "sop-modal-root";
    document.body.append(root);
  }
  root.innerHTML = `
    <div class="sop-modal-backdrop" data-modal-close></div>
    <section class="sop-modal" role="dialog" aria-modal="true" aria-labelledby="sop-modal-title">
      ${innerHtml}
    </section>
  `;
  document.body.classList.add("modal-open");
  root.querySelector(".sop-modal-close")?.focus();
}

function renderSopDocument(documentDetail, targetSection = "") {
  const targetKey = userSettings.sectionJump ? sectionKey(targetSection) : "";
  const sections = (documentDetail.sections || [])
    .filter((section) => String(section.text || "").trim())
    .map((section) => `
      <section
        class="sop-full-section${targetKey && sectionKey(section.heading) === targetKey ? " is-target" : ""}"
        data-section-key="${escapeHtml(sectionKey(section.heading))}"
      >
        <h3>${escapeHtml(section.heading || documentDetail.title)}</h3>
        <p>${escapeHtml(section.text)}</p>
      </section>
    `)
    .join("");

  return `
    <header class="sop-modal-header">
      <div>
        <p>${escapeHtml(documentDetail.file)}</p>
        <h2 id="sop-modal-title">${escapeHtml(documentDetail.title)}</h2>
      </div>
      <button type="button" class="sop-modal-close" data-modal-close aria-label="Close preview">×</button>
    </header>
    <div class="sop-modal-body">
      ${sections || `<p>${escapeHtml(documentDetail.text || "")}</p>`}
    </div>
  `;
}

function scrollToSopSection(targetSection) {
  if (!userSettings.sectionJump) {
    return;
  }
  const key = sectionKey(targetSection);
  if (!key) {
    return;
  }
  requestAnimationFrame(() => {
    const target = document.querySelector(`[data-section-key="${CSS.escape(key)}"]`);
    target?.scrollIntoView({ block: "start", behavior: "smooth" });
  });
}

function closeSopModal() {
  const root = document.querySelector("#sop-modal-root");
  if (root) {
    root.remove();
  }
  document.body.classList.remove("modal-open");
}

setupNavigation();
setupSettingsPopover();
setupSopPreview();
setActiveNav();
renderShell();
refreshProviderStatus();
