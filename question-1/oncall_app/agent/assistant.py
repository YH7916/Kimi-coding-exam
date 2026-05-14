"""Chat Completions tool-calling On-Call assistant."""

import json
from typing import cast

from oncall_app.agent.prompts import READ_FILE_TOOLS, SYSTEM_PROMPT
from oncall_app.agent.tools import ReadFileTool
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient
from oncall_app.llm.openai_compat import JsonObject
from oncall_app.models import AgentResponse

MAX_TOOL_ROUNDS = 4
MANIFEST_FILE = "sop-index.json"


class OnCallAssistant:  # pylint: disable=too-few-public-methods
    """Run a Chat Completions loop with the readFile tool."""

    def __init__(
        self,
        repository: DocumentRepository,
        chat_client: ChatClient,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ):
        self.repository = repository
        self.chat_client = chat_client
        self.max_tool_rounds = max_tool_rounds
        self.read_file_tool = ReadFileTool(repository)

    def chat(self, message: str) -> AgentResponse:
        """Answer a user message with tool-calling."""
        self.repository.write_manifest(MANIFEST_FILE)
        manifest_observation = self.read_file_tool.read_file(MANIFEST_FILE)
        tool_calls = [manifest_observation.call]
        messages = self._initial_messages(message, manifest_observation.content)

        for _ in range(self.max_tool_rounds):
            response = self.chat_client.create_chat_completion(messages, READ_FILE_TOOLS)
            assistant_message = _assistant_message(response)
            messages.append(assistant_message)
            requested_tools = _tool_calls(assistant_message)
            if not requested_tools:
                return AgentResponse(
                    answer=str(assistant_message.get("content") or ""),
                    tool_calls=tool_calls,
                )
            for tool_call in requested_tools:
                observation = self._execute_tool_call(tool_call)
                tool_calls.append(observation.call)
                messages.append(_tool_message(tool_call, observation.content))

        return AgentResponse(
            answer="工具调用轮次已达到上限，请缩小问题范围后重试。",
            tool_calls=tool_calls,
        )

    @staticmethod
    def _initial_messages(message: str, manifest_content: str) -> list[JsonObject]:
        """Build initial Chat Completions messages."""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"readFile({MANIFEST_FILE}) returned this SOP index:\n"
                    f"{manifest_content}"
                ),
            },
            {"role": "user", "content": message},
        ]

    def _execute_tool_call(self, tool_call: JsonObject):
        """Execute one model-requested tool call."""
        function = _function_payload(tool_call)
        name = str(function.get("name", ""))
        if name != "readFile":
            raise ValueError(f"unsupported tool: {name}")
        arguments = json.loads(str(function.get("arguments") or "{}"))
        fname = str(arguments.get("fname", ""))
        return self.read_file_tool.read_file(fname)


def _assistant_message(response: JsonObject) -> JsonObject:
    """Extract the assistant message from a provider response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat response missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("chat choice is not an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("chat choice missing message")
    return cast(JsonObject, message)


def _tool_calls(message: JsonObject) -> list[JsonObject]:
    """Return model-requested tool calls."""
    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        return []
    if not isinstance(tool_calls, list):
        raise ValueError("tool_calls must be a list")
    return [cast(JsonObject, tool_call) for tool_call in tool_calls]


def _function_payload(tool_call: JsonObject) -> JsonObject:
    """Extract a function payload from a tool call."""
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool call missing function payload")
    return cast(JsonObject, function)


def _tool_message(tool_call: JsonObject, content: str) -> JsonObject:
    """Build a Chat Completions tool-result message."""
    return {
        "role": "tool",
        "tool_call_id": str(tool_call.get("id", "")),
        "name": "readFile",
        "content": content,
    }
