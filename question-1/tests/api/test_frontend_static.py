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
        self.assertTrue((PROJECT_ROOT / "frontend" / "assets" / "settings-2.svg").is_file())

    def test_pages_use_static_frontend_shell(self):
        """README page routes serve the shared static frontend shell."""
        client = TestClient(create_app(test_mode=True))

        response = client.get("/v3")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<script src="/static/app.js"', response.text)
        self.assertIn('<link rel="stylesheet" href="/static/styles.css"', response.text)
        self.assertIn('/static/assets/settings-2.svg', response.text)
        self.assertIn('id="settings-button"', response.text)

    def test_static_js_calls_readme_api_routes(self):
        """Frontend JavaScript calls the README API routes."""
        js = (PROJECT_ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

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
        self.assertIn("JSON.stringify({ message, history })", js)
        self.assertIn("renderMarkdown", js)
        self.assertIn("markdown-body", js)
        self.assertIn("renderChatShell", js)
        self.assertIn("chat-screen", js)
        self.assertIn("/documents/", js)
        self.assertIn("openSopModal", js)
        self.assertIn("data-sop-id", js)
        self.assertIn("data-sop-section", js)


if __name__ == "__main__":
    unittest.main()
