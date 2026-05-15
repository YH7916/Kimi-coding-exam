import { MAX_HISTORY_ENTRIES } from "./config.js";
import { escapeHtml } from "./markdown.js";

export function renderWorkspaceShell({
  activeHistoryId,
  content,
  historyEntries,
  userSettings,
}) {
  return `
    <div class="workspace-shell ${userSettings.historyOpen ? "is-history-open" : ""} ${userSettings.settingsOpen ? "is-settings-open" : ""}">
      <div
        class="side-panel-backdrop"
        ${userSettings.historyOpen || userSettings.settingsOpen ? "" : "hidden"}
        data-panel-dismiss
      ></div>
      <aside
        id="history-sidebar"
        class="side-panel history-sidebar"
        aria-label="聊天记录"
        aria-hidden="${userSettings.historyOpen ? "false" : "true"}"
        ${userSettings.historyOpen ? "" : "inert"}
      >
        ${renderHistorySidebar(historyEntries, activeHistoryId)}
      </aside>
      <aside
        id="settings-sidebar"
        class="side-panel settings-sidebar"
        aria-label="运行设置"
        aria-hidden="${userSettings.settingsOpen ? "false" : "true"}"
        ${userSettings.settingsOpen ? "" : "inert"}
      >
        ${renderSettingsSidebar(userSettings)}
      </aside>
      <div class="workspace-main">
        ${content}
      </div>
    </div>
  `;
}

export function renderHistorySidebar(historyEntries, activeHistoryId) {
  const entries = historyEntries.slice(0, MAX_HISTORY_ENTRIES);
  const emptyState = `
    <p class="history-empty">还没有记录。搜索或提问后会自动出现在这里。</p>
  `;

  return `
    <div class="history-sidebar-header">
      <span>聊天记录</span>
    </div>
    <div class="history-list">
      ${
        entries.length
          ? entries.map((entry, index) => renderHistoryEntry(entry, index, activeHistoryId)).join("")
          : emptyState
      }
    </div>
  `;
}

export function renderHomeShell(config) {
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

export function renderChatShell(config) {
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

export function renderSettingsSidebar(userSettings) {
  return `
    <div class="side-panel-header">
      <span>运行状态</span>
      <small id="settings-summary">正在检查</small>
    </div>
    <div id="provider-status-details" class="provider-status-details">
      <p>正在加载运行状态...</p>
    </div>
    <div class="settings-group">
      <span>界面</span>
      <label>
        <input id="setting-show-trace" type="checkbox" ${userSettings.showTrace ? "checked" : ""}>
        显示工具调用过程
      </label>
      <label>
        <input id="setting-section-jump" type="checkbox" ${userSettings.sectionJump ? "checked" : ""}>
        打开 SOP 时定位引用章节
      </label>
    </div>
  `;
}

function renderHistoryEntry(entry, index, activeHistoryId) {
  const isCurrent = entry.id === activeHistoryId;
  return `
    <article class="history-entry ${isCurrent ? "is-current" : ""}" style="--i: ${index}">
      <button
        type="button"
        class="history-entry-load"
        data-history-id="${escapeHtml(entry.id)}"
      >
        <span class="history-mode-tag">${escapeHtml(entry.mode)}</span>
        <span class="history-entry-title">${escapeHtml(entry.title)}</span>
      </button>
      <button
        type="button"
        class="history-delete-button"
        data-history-delete-id="${escapeHtml(entry.id)}"
        aria-label="删除 ${escapeHtml(entry.title)}"
      >
        <img src="/static/assets/trash-2.svg" alt="" aria-hidden="true">
      </button>
    </article>
  `;
}
