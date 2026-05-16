"""Tests for separated frontend assets."""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FrontendStaticTest(unittest.TestCase):
    """Frontend assets are separate from route code."""

    def test_frontend_files_exist(self):
        """The frontend lives outside backend route modules."""
        for name in ("index.html", "app.js", "styles.css"):
            self.assertTrue((PROJECT_ROOT / "frontend" / name).is_file())
        for name in (
            "api.js",
            "chatView.js",
            "config.js",
            "evidence.js",
            "format.js",
            "markdown.js",
            "providerStatus.js",
            "searchResults.js",
            "shellView.js",
            "sopPreview.js",
            "sse.js",
            "storage.js",
            "trace.js",
        ):
            self.assertTrue((PROJECT_ROOT / "frontend" / "app" / name).is_file())
        self.assertTrue((PROJECT_ROOT / "frontend" / "assets" / "settings-2.svg").is_file())

    def test_pages_use_static_frontend_shell(self):
        """README page routes serve the shared static frontend shell."""
        client = TestClient(create_app(test_mode=True))

        response = client.get("/v3")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<script type="module" src="/static/app.js"', response.text)
        self.assertIn('<link rel="stylesheet" href="/static/styles.css"', response.text)
        self.assertIn('/static/assets/settings-2.svg', response.text)
        self.assertIn('id="settings-button"', response.text)

    def test_static_js_calls_readme_api_routes(self):
        """Frontend JavaScript calls the README API routes."""
        js = self._frontend_js()

        self.assertIn("/v1/search", js)
        self.assertIn("/v2/search", js)
        self.assertIn("/v3/chat", js)
        self.assertIn("/v3/chat/stream", js)
        self.assertIn("/provider-status", js)
        self.assertIn("setupSettingsPopover", js)
        self.assertIn("setting-show-trace", js)
        self.assertIn("visibleChatHistory", js)
        self.assertIn("applyChatFailure", js)
        self.assertIn("streamingPlaceholder", js)
        self.assertIn("scheduleAssistantContentUpdate", js)
        self.assertIn("updateAssistantContent", js)
        self.assertIn('renderMode === "content"', js)
        self.assertIn("JSON.stringify({ message, history })", js)
        self.assertIn("renderMarkdown", js)
        self.assertIn("renderMarkdownTable", js)
        self.assertIn("collectMarkdownTable", js)
        self.assertIn("pendingListBreak", js)
        self.assertIn("isListItem", js)
        self.assertIn("markdown-body", js)
        self.assertIn("renderChatShell", js)
        self.assertIn("chat-screen", js)
        self.assertIn("/documents/", js)
        self.assertIn("openSopModal", js)
        self.assertIn('data-sop-section="${escapeHtml(item.section || "")}"', js)
        self.assertIn("setupEvidenceCarousel", js)
        self.assertIn("const hasScrollableEvidence = cards.length > 3;", js)
        self.assertIn("data-evidence-direction", js)
        self.assertIn("data-evidence-pagebar", js)
        self.assertIn("scrollEvidenceStrip", js)
        self.assertIn("evidenceActiveDotIndex", js)
        self.assertIn("data-sop-id", js)
        self.assertIn("data-sop-section", js)
        self.assertIn("evidence-section", js)
        self.assertIn("memory_hits", js)
        self.assertIn("renderMemoryTrace", js)
        self.assertIn("/v3/memory/search", js)

    def test_v3_evidence_cards_use_scroll_carousel(self):
        """V3 evidence cards render as a compact horizontal carousel."""
        css = (PROJECT_ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".evidence-carousel", css)
        self.assertIn(".evidence-strip", css)
        self.assertIn("--evidence-visible: 3;", css)
        self.assertIn("scroll-snap-type: x mandatory;", css)
        self.assertIn(".evidence-nav-button", css)
        self.assertIn(".evidence-pagebar", css)
        self.assertIn("width: 18px;", css)
        self.assertIn("-webkit-line-clamp: 2;", css)

    def test_markdown_styles_support_readable_hierarchy(self):
        """Markdown output has GitHub-like hierarchy and rich block support."""
        css = (PROJECT_ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".markdown-body h2", css)
        self.assertIn("border-bottom: 1px solid var(--line-soft);", css)
        self.assertIn(".markdown-body blockquote", css)
        self.assertIn(".markdown-body table", css)
        self.assertIn(".markdown-body strong", css)

    @staticmethod
    def _frontend_js() -> str:
        """Return the concatenated static frontend modules."""
        paths = [PROJECT_ROOT / "frontend" / "app.js"]
        paths.extend(sorted((PROJECT_ROOT / "frontend" / "app").glob("*.js")))
        return "\n".join(path.read_text(encoding="utf-8") for path in paths)


if __name__ == "__main__":
    unittest.main()
