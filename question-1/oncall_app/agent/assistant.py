"""Chat Completions tool-calling On-Call assistant."""

import json
from pathlib import Path
from typing import cast

from oncall_app.agent.evidence import EvidenceExtractor
from oncall_app.agent.prompts import READ_FILE_TOOLS, SYSTEM_PROMPT
from oncall_app.agent.state import ToolObservation
from oncall_app.agent.synthesizer import format_evidence_context
from oncall_app.agent.tools import ReadFileTool
from oncall_app.documents.parser import parse_document
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient
from oncall_app.llm.openai_compat import JsonObject
from oncall_app.models import AgentResponse, SearchResult

MAX_TOOL_ROUNDS = 4


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

    def chat(
        self,
        message: str,
        retrieval_candidates: list[SearchResult],
    ) -> AgentResponse:
        """Answer a user message with tool-calling."""
        candidates = retrieval_candidates
        tool_calls: list = []
        messages = self._initial_messages(message, candidates)

        for _ in range(self.max_tool_rounds):
            response = self.chat_client.create_chat_completion(messages, READ_FILE_TOOLS)
            assistant_message = _assistant_message(response)
            messages.append(assistant_message)
            requested_tools = _tool_calls(assistant_message)
            if not requested_tools:
                return AgentResponse(
                    answer=str(assistant_message.get("content") or ""),
                    tool_calls=tool_calls,
                    retrieval_candidates=candidates,
                )
            round_observations: list[ToolObservation] = []
            for tool_call in requested_tools:
                observation = self._execute_tool_call(tool_call)
                round_observations.append(observation)
                tool_calls.append(observation.call)
                messages.append(_tool_message(tool_call, observation.content))
            evidence_context = self._evidence_context(message, round_observations)
            if evidence_context:
                messages.append({"role": "system", "content": evidence_context})

        return AgentResponse(
            answer="工具调用轮次已达到上限，请缩小问题范围后重试。",
            tool_calls=tool_calls,
            retrieval_candidates=candidates,
        )

    @staticmethod
    def _initial_messages(
        message: str,
        retrieval_candidates: list[SearchResult],
    ) -> list[JsonObject]:
        """Build initial Chat Completions messages."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _candidate_context(retrieval_candidates)},
        ]
        messages.append({"role": "user", "content": message})
        return messages

    def _execute_tool_call(self, tool_call: JsonObject):
        """Execute one model-requested tool call."""
        function = _function_payload(tool_call)
        name = str(function.get("name", ""))
        if name != "readFile":
            raise ValueError(f"unsupported tool: {name}")
        arguments = json.loads(str(function.get("arguments") or "{}"))
        fname = str(arguments.get("fname", ""))
        return self.read_file_tool.read_file(fname)

    @staticmethod
    def _evidence_context(
        message: str,
        observations: list[ToolObservation],
    ) -> str:
        """Extract evidence from SOP HTML tool observations."""
        documents = [
            parse_document(
                Path(observation.call.fname).stem,
                observation.content,
                file_name=observation.call.fname,
            )
            for observation in observations
            if observation.call.fname.endswith(".html")
        ]
        if not documents:
            return ""
        evidence = EvidenceExtractor().extract(message, documents)
        return format_evidence_context(evidence)


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


def _candidate_context(candidates: list[SearchResult]) -> str:
    """Build model-visible candidate files from v2 hybrid retrieval."""
    lines = [
        "Hybrid retrieval candidates from v2 semantic_search.",
        "Read original SOPs with readFile using only these candidate file names.",
    ]
    if not candidates:
        lines.append("No SOP candidates were returned; do not call readFile.")
        return "\n".join(lines)
    for index, candidate in enumerate(candidates, start=1):
        fname = f"{candidate.doc_id}.html"
        lines.append(
            f"{index}. file={fname}; title={candidate.title}; "
            f"score={candidate.score}; snippet={candidate.snippet}"
        )
    return "\n".join(lines)
