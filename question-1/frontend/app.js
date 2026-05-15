const app = document.querySelector("#app");
const route = window.location.pathname;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderSearch(version, endpoint, title) {
  app.innerHTML = `
    <h1>${title}</h1>
    <form id="search-form">
      <input name="q" placeholder="输入关键词或问题" autofocus />
      <button type="submit">搜索</button>
    </form>
    <section id="results"></section>
  `;

  document.querySelector("#search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const q = new FormData(event.target).get("q") || "";
    const response = await fetch(`${endpoint}?q=${encodeURIComponent(q)}`);
    const payload = await response.json();
    document.querySelector("#results").innerHTML = payload.results.map((item) => `
      <article>
        <h2>${escapeHtml(item.title)}</h2>
        <p>${escapeHtml(item.snippet)}</p>
        <small>${version} · ${escapeHtml(item.id)} · score=${escapeHtml(item.score)}</small>
      </article>
    `).join("") || "<p>没有结果</p>";
  });
}

function renderChat() {
  app.innerHTML = `
    <h1>v3 On-Call Agent</h1>
    <form id="chat-form">
      <textarea name="message" placeholder="例如：服务 OOM 了怎么办？"></textarea>
      <button type="submit">发送</button>
    </form>
    <section id="trace"></section>
    <section id="answer"></section>
  `;

  document.querySelector("#chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = new FormData(event.target).get("message") || "";
    const response = await fetch("/v3/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const payload = await response.json();
    const trace = payload.trace || [];
    const evidence = payload.evidence || [];
    const toolCalls = payload.tool_calls || [];
    document.querySelector("#trace").innerHTML = `
      <div class="trace-list">
        ${trace.map((item) => `
          <article class="trace-item">
            <strong>${escapeHtml(item.type)}</strong>
            <p>${escapeHtml(item.message)}</p>
          </article>
        `).join("")}
      </div>
      <div class="tool-list">
        ${toolCalls.map((call) => `
          <pre>${escapeHtml(call.tool)}("${escapeHtml(call.fname)}")\n${escapeHtml(call.result_preview || "")}</pre>
        `).join("")}
      </div>
      <div class="evidence-list">
        ${evidence.map((item) => `
          <article class="evidence-card">
            <h2>${escapeHtml(item.file)} · ${escapeHtml(item.section)}</h2>
            <p>${escapeHtml(item.text)}</p>
          </article>
        `).join("")}
      </div>
    `;
    document.querySelector("#answer").innerHTML = `<pre>${escapeHtml(payload.answer)}</pre>`;
  });
}

if (route === "/v1") {
  renderSearch("v1", "/v1/search", "v1 BM25 Keyword Search");
} else if (route === "/v2") {
  renderSearch("v2", "/v2/search", "v2 RAG Retriever");
} else {
  renderChat();
}
