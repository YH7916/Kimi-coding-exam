"""Tool-calling agent tests."""

# pylint: disable=too-few-public-methods

import unittest
from pathlib import Path
from typing import Any

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.documents.repository import DocumentRepository
from oncall_app.models import SearchResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class FakeChatClient:
    """Fake Chat Completions client returning tool calls then final answer."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return one readFile call, then a final answer."""
        self.calls.append({"messages": messages, "tools": tools})
        if len(self.calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "readFile",
                                        "arguments": "{\"fname\":\"sop-001.html\"}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "服务 OOM 时需要保存堆转储文件，并检查 JVM 内存曲线。",
                    }
                }
            ]
        }


class ToolCallingAgentTest(unittest.TestCase):
    """Agent uses Chat Completions tool calls."""

    def test_oom_uses_readfile_tool_call(self):
        """The assistant uses v2 candidates, executes readFile, then answers."""
        chat_client = FakeChatClient()
        assistant = OnCallAssistant(
            repository=DocumentRepository(DATA_DIR),
            chat_client=chat_client,
        )

        response = assistant.chat(
            "服务 OOM 了怎么办？",
            retrieval_candidates=[
                SearchResult(
                    doc_id="sop-001",
                    title="后端服务 On-Call SOP",
                    snippet="单服务 OOM 崩溃",
                    score=1.0,
                )
            ],
        )
        fnames = [call.fname for call in response.tool_calls]

        self.assertNotIn("sop-index.json", fnames)
        self.assertIn("sop-001.html", fnames)
        self.assertIn("堆转储", response.answer)
        self.assertEqual(response.retrieval_candidates[0].doc_id, "sop-001")
        self.assertEqual(chat_client.calls[0]["tools"][0]["function"]["name"], "readFile")
        self.assertTrue(
            any(
                "Hybrid retrieval candidates" in message.get("content", "")
                and "sop-001.html" in message.get("content", "")
                for message in chat_client.calls[0]["messages"]
            )
        )
        self.assertTrue(
            any(
                message.get("role") == "tool" and "后端服务 On-Call SOP" in message.get("content", "")
                for message in chat_client.calls[1]["messages"]
            )
        )


if __name__ == "__main__":
    unittest.main()
