import { fetchProviderStatus, fetchSearchResults, streamChat } from "./app/api.js";
import {
  renderAssistantBody,
  renderChatConversation as renderChatConversationMarkup,
} from "./app/chatView.js";
import { MAX_HISTORY_ENTRIES, MODES, modeFromPath } from "./app/config.js";
import { setupEvidenceCarousel } from "./app/evidence.js";
import { escapeHtml } from "./app/markdown.js";
import { renderProviderStatus } from "./app/providerStatus.js";
import { renderSearchResults } from "./app/searchResults.js";
import {
  renderChatShell,
  renderHistorySidebar,
  renderHomeShell,
  renderSettingsSidebar,
  renderWorkspaceShell,
} from "./app/shellView.js";
import { setupSopPreview } from "./app/sopPreview.js";
import {
  compactHistoryTitle,
  createHistoryId,
  loadHistoryEntries,
  loadUserSettings,
  saveHistoryEntries,
  saveUserSettings,
} from "./app/storage.js";

const app = document.querySelector("#app");

let mode = modeFromPath(window.location.pathname);
let config = MODES[mode];
const chatTurns = [];
const userSettings = loadUserSettings();
let historyEntries = loadHistoryEntries();
let activeHistoryId = null;
let activeChatHistoryId = null;
let pendingAssistantContentTurn = null;
let pendingAssistantContentFrame = 0;

function isActiveChat() {
  return mode === "v3" && chatTurns.length > 0;
}

function hasPendingChatTurn() {
  return chatTurns.some((turn) => turn.role === "pending" || turn.streaming);
}

function recordSearchHistory(query) {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    return;
  }
  const now = Date.now();
  const existing = historyEntries.find(
    (entry) => entry.mode === mode && entry.query === normalizedQuery && !entry.turns,
  );
  const entry = {
    id: existing?.id || createHistoryId(),
    mode,
    title: compactHistoryTitle(normalizedQuery),
    query: normalizedQuery,
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  };
  activeHistoryId = entry.id;
  historyEntries = [entry, ...historyEntries.filter((item) => item.id !== entry.id)].slice(
    0,
    MAX_HISTORY_ENTRIES,
  );
  saveHistoryEntries(historyEntries);
}

function serializeChatTurns() {
  return chatTurns
    .filter((turn) => ["user", "assistant", "error"].includes(turn.role))
    .map((turn) => ({
      role: turn.role,
      content: turn.content || "",
      evidence: turn.evidence || [],
      trace: turn.trace || [],
      toolCalls: turn.toolCalls || [],
      streaming: false,
    }));
}

function persistCurrentChatHistory() {
  const firstUserTurn = chatTurns.find((turn) => turn.role === "user" && turn.content);
  if (!firstUserTurn) {
    return;
  }
  const now = Date.now();
  const existing = historyEntries.find((entry) => entry.id === activeChatHistoryId);
  const entry = {
    id: existing?.id || createHistoryId(),
    mode: "v3",
    title: compactHistoryTitle(firstUserTurn.content),
    query: firstUserTurn.content,
    turns: serializeChatTurns(),
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  };
  activeChatHistoryId = entry.id;
  activeHistoryId = entry.id;
  historyEntries = [entry, ...historyEntries.filter((item) => item.id !== entry.id)].slice(
    0,
    MAX_HISTORY_ENTRIES,
  );
  saveHistoryEntries(historyEntries);
}

function restoreChatTurns(turns) {
  chatTurns.splice(
    0,
    chatTurns.length,
    ...(Array.isArray(turns) ? turns : [])
      .filter((turn) => ["user", "assistant", "error"].includes(turn?.role))
      .map((turn) => ({
        role: turn.role,
        content: turn.content || "",
        evidence: turn.evidence || [],
        trace: turn.trace || [],
        toolCalls: turn.toolCalls || [],
        streaming: false,
      })),
  );
}

async function refreshProviderStatus() {
  try {
    renderProviderStatus(await fetchProviderStatus());
  } catch (_error) {
    renderProviderStatus(null);
  }
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

function syncHistoryButtonState() {
  const button = document.querySelector("#history-button");
  if (!button) {
    return;
  }
  button.setAttribute("aria-expanded", String(userSettings.historyOpen));
  button.classList.toggle("is-active", userSettings.historyOpen);
}

function syncSettingsButtonState() {
  const button = document.querySelector("#settings-button");
  if (!button) {
    return;
  }
  button.setAttribute("aria-expanded", String(userSettings.settingsOpen));
  button.classList.toggle("is-active", userSettings.settingsOpen);
}

function syncPanelBackdropState() {
  const backdrop = document.querySelector(".side-panel-backdrop");
  if (backdrop) {
    backdrop.hidden = !(userSettings.historyOpen || userSettings.settingsOpen);
  }
}

function applyHistorySidebarState() {
  document.body.classList.toggle("history-open", userSettings.historyOpen);
  document.querySelector(".workspace-shell")?.classList.toggle(
    "is-history-open",
    userSettings.historyOpen,
  );
  syncPanelBackdropState();
  const sidebar = document.querySelector("#history-sidebar");
  if (sidebar) {
    sidebar.setAttribute("aria-hidden", String(!userSettings.historyOpen));
    if (userSettings.historyOpen) {
      sidebar.removeAttribute("inert");
      sidebar.innerHTML = renderHistorySidebar(historyEntries, activeHistoryId);
    } else {
      sidebar.setAttribute("inert", "");
    }
  }
  syncHistoryButtonState();
}

function applySettingsSidebarState() {
  document.body.classList.toggle("settings-open", userSettings.settingsOpen);
  document.querySelector(".workspace-shell")?.classList.toggle(
    "is-settings-open",
    userSettings.settingsOpen,
  );
  syncPanelBackdropState();
  const sidebar = document.querySelector("#settings-sidebar");
  if (sidebar) {
    sidebar.setAttribute("aria-hidden", String(!userSettings.settingsOpen));
    if (userSettings.settingsOpen) {
      sidebar.removeAttribute("inert");
      sidebar.innerHTML = renderSettingsSidebar(userSettings);
      bindSettingsControls();
      refreshProviderStatus();
    } else {
      sidebar.setAttribute("inert", "");
    }
  }
  syncSettingsButtonState();
}

function setupHistoryButton() {
  const button = document.querySelector("#history-button");
  if (!button) {
    return;
  }
  button.addEventListener("click", () => {
    userSettings.historyOpen = !userSettings.historyOpen;
    saveUserSettings(userSettings);
    applyHistorySidebarState();
  });
  syncHistoryButtonState();
}

function setupHistorySidebar() {
  app.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const deleteTrigger = event.target.closest("[data-history-delete-id]");
    if (deleteTrigger) {
      event.preventDefault();
      deleteHistoryEntry(deleteTrigger.dataset.historyDeleteId || "");
      return;
    }
    const trigger = event.target.closest("[data-history-id]");
    if (!trigger) {
      if (event.target.closest("[data-panel-dismiss]")) {
        userSettings.historyOpen = false;
        userSettings.settingsOpen = false;
        saveUserSettings(userSettings);
        applyHistorySidebarState();
        applySettingsSidebarState();
      }
      return;
    }
    event.preventDefault();
    loadHistoryEntry(trigger.dataset.historyId || "");
  });
}

function deleteHistoryEntry(id) {
  if (!id) {
    return;
  }
  historyEntries = historyEntries.filter((entry) => entry.id !== id);
  if (activeHistoryId === id) {
    activeHistoryId = null;
  }
  if (activeChatHistoryId === id) {
    activeChatHistoryId = null;
  }
  saveHistoryEntries(historyEntries);
  refreshHistorySidebar();
}

async function loadHistoryEntry(id) {
  const entry = historyEntries.find((item) => item.id === id);
  if (!entry) {
    return;
  }
  activeHistoryId = entry.id;
  if (entry.mode === "v3") {
    activeChatHistoryId = entry.id;
    restoreChatTurns(entry.turns || []);
    switchMode("v3", true);
    return;
  }

  switchMode(entry.mode, true);
  const textarea = document.querySelector("#query-form textarea");
  if (textarea) {
    textarea.value = entry.query || entry.title;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }
  await submitSearch(entry.query || entry.title, { record: false });
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

function bindSettingsControls() {
  const showTrace = document.querySelector("#setting-show-trace");
  const sectionJump = document.querySelector("#setting-section-jump");
  if (!showTrace || !sectionJump) {
    return;
  }

  showTrace.checked = userSettings.showTrace;
  sectionJump.checked = userSettings.sectionJump;

  showTrace.addEventListener("change", () => {
    userSettings.showTrace = showTrace.checked;
    saveUserSettings(userSettings);
    if (isActiveChat()) {
      renderChatConversation();
    }
  });

  sectionJump.addEventListener("change", () => {
    userSettings.sectionJump = sectionJump.checked;
    saveUserSettings(userSettings);
  });
}

function setupSettingsPopover() {
  const button = document.querySelector("#settings-button");
  if (!button) {
    return;
  }

  button.addEventListener("click", () => {
    userSettings.settingsOpen = !userSettings.settingsOpen;
    saveUserSettings(userSettings);
    applySettingsSidebarState();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !(userSettings.historyOpen || userSettings.settingsOpen)) {
      return;
    }
    userSettings.historyOpen = false;
    userSettings.settingsOpen = false;
    saveUserSettings(userSettings);
    applyHistorySidebarState();
    applySettingsSidebarState();
  });

  syncSettingsButtonState();
}

function renderShell() {
  const activeChat = isActiveChat();
  document.body.classList.toggle("chat-active", activeChat);
  document.body.classList.toggle("history-open", userSettings.historyOpen);
  document.body.classList.toggle("settings-open", userSettings.settingsOpen);
  app.innerHTML = renderWorkspaceShell({
    activeHistoryId,
    content: activeChat ? renderChatShell(config) : renderHomeShell(config),
    historyEntries,
    userSettings,
  });
  syncHistoryButtonState();
  syncSettingsButtonState();
  bindSettingsControls();

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

function refreshHistorySidebar() {
  const sidebar = document.querySelector("#history-sidebar");
  if (sidebar && userSettings.historyOpen) {
    sidebar.innerHTML = renderHistorySidebar(historyEntries, activeHistoryId);
  }
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

async function submitSearch(q, options = {}) {
  renderLoading(mode === "v1" ? "Searching keywords" : "Retrieving evidence");
  try {
    const payload = await fetchSearchResults(config.endpoint, q);
    renderSearchResults(payload.results || [], config.resultTitle);
    if (options.record !== false) {
      recordSearchHistory(q);
      refreshHistorySidebar();
    }
    refreshProviderStatus();
  } catch (error) {
    renderError(error.message || "Unknown error");
  }
}

async function submitChat(message) {
  const history = visibleChatHistory();
  if (!chatTurns.some((turn) => turn.role === "user" || turn.role === "assistant")) {
    activeChatHistoryId = null;
  }
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
    await streamChat(
      config.streamEndpoint || `${config.endpoint}/stream`,
      message,
      history,
      (event) => {
        const renderMode = applyChatStreamEvent(assistantTurn, event);
        if (renderMode === "content") {
          scheduleAssistantContentUpdate(assistantTurn);
          return;
        }
        cancelAssistantContentUpdate();
        renderChatConversation();
      },
    );
    assistantTurn.streaming = false;
    renderShell();
  } catch (error) {
    applyChatFailure(assistantTurn, error.message || "Unknown error");
    renderShell();
  } finally {
    persistCurrentChatHistory();
    renderShell();
    refreshProviderStatus();
  }
}

function visibleChatHistory() {
  return chatTurns
    .filter((turn) => turn.role === "user" || turn.role === "assistant")
    .map((turn) => ({ role: turn.role, content: turn.content }));
}

function applyChatStreamEvent(turn, event) {
  const data = event.data || {};
  if (event.type === "retrieval") {
    const files = (data.candidates || []).map((item) => item.file).join(", ");
    turn.trace = [
      ...(turn.trace || []),
      {
        type: "retrieval",
        message: files ? `v2 hybrid retrieval candidates: ${files}` : "no candidates",
      },
    ];
    return "full";
  }
  if (event.type === "tool_call") {
    turn.toolCalls = [
      ...(turn.toolCalls || []),
      { tool: data.tool || "readFile", fname: data.fname || "" },
    ];
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
    turn.trace = mergeTraceEvents(turn.trace || [], data.trace || []);
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

function mergeTraceEvents(existingTrace, finalTrace) {
  const seen = new Set();
  return [...existingTrace, ...finalTrace].filter((item) => {
    const key = `${item.type}:${item.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
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

function renderChatConversation() {
  document.querySelector("#results").innerHTML = renderChatConversationMarkup(chatTurns, {
    placeholderForTurn: streamingPlaceholder,
    showTrace: userSettings.showTrace,
  });
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
  body.innerHTML = renderAssistantBody(turn, streamingPlaceholder);
}

setupNavigation();
setupHistoryButton();
setupHistorySidebar();
setupSettingsPopover();
setupEvidenceCarousel(app);
setupSopPreview(app, () => userSettings);
setActiveNav();
renderShell();
refreshProviderStatus();
