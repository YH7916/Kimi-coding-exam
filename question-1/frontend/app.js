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

function isActiveChat() {
  return mode === "v3" && chatTurns.length > 0;
}

function hasPendingChatTurn() {
  return chatTurns.some((turn) => turn.role === "pending");
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
    const placeholder = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return placeholder;
  });

  rendered = rendered
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');

  codeSpans.forEach((code, index) => {
    rendered = rendered.replaceAll(`@@CODE_SPAN_${index}@@`, code);
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

  lines.forEach((line) => {
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
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    if (!trimmed) {
      closeParagraph();
      closeList();
      return;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeParagraph();
      closeList();
      const level = Math.min(heading[1].length + 2, 5);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      openList("ul");
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      return;
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      openList("ol");
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      return;
    }

    closeList();
    paragraph.push(renderInlineMarkdown(trimmed));
  });

  if (inCodeBlock) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  closeParagraph();
  closeList();
  return html.join("");
}

function scoreLabel(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) {
    return String(score);
  }
  return numeric.toFixed(numeric >= 10 ? 0 : 2);
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
                  <article class="result-row" style="--i: ${index}">
                    <span class="result-index">${index + 1}</span>
                    <div>
                      <h3>${escapeHtml(item.title)}</h3>
                      <p>${escapeHtml(item.snippet)}</p>
                      <small>${escapeHtml(item.id)} · score ${escapeHtml(scoreLabel(item.score))}</small>
                    </div>
                  </article>
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
  chatTurns.push({ role: "pending", content: "Reading SOP evidence" });
  renderShell();
  try {
    const response = await fetch(config.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    removePendingTurn();
    chatTurns.push({
      role: "assistant",
      content: payload.answer || "",
      evidence: payload.evidence || [],
      trace: payload.trace || [],
      toolCalls: payload.tool_calls || [],
    });
    renderShell();
  } catch (error) {
    removePendingTurn();
    chatTurns.push({
      role: "error",
      content: error.message || "Unknown error",
    });
    renderShell();
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
  const visibleTurns = chatTurns.filter((turn) => turn.role === "user" || turn.role === "assistant").length;

  document.querySelector("#results").innerHTML = `
    <div class="agent-layout chat-agent-layout result-enter">
      <section class="answer-panel chat-thread-panel">
        <div class="chat-thread-header">
          <span>On-Call Agent</span>
          <small>${visibleTurns} turns</small>
        </div>
        <div class="chat-list">
          ${chatTurns.map((turn, index) => renderChatTurn(turn, index)).join("")}
        </div>
      </section>
      <aside class="trace-panel">
        <div class="section-heading">
          <h2>Trace</h2>
          <span>${toolCalls.length} tool calls</span>
        </div>
        <div class="trace-list">
          ${renderTrace(trace)}
        </div>
      </aside>
    </div>
  `;
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
    <article class="chat-message chat-message-assistant" style="--i: ${index}">
      <small>Assistant</small>
      <div class="markdown-body">${renderMarkdown(turn.content || "")}</div>
      ${renderEvidence(turn.evidence || [])}
    </article>
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
  return `
    <div class="evidence-strip">
      ${evidence.slice(0, 3).map((item, index) => `
        <article class="evidence-card" style="--i: ${index}">
          <small>${escapeHtml(item.file)}</small>
          <h3>${escapeHtml(item.section)}</h3>
          <p>${escapeHtml(item.text)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

setupNavigation();
setActiveNav();
renderShell();
