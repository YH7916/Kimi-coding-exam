"""Local deterministic Chat Completions fallback."""

from oncall_app.llm.openai_compat import JsonObject


class LocalChatClient:  # pylint: disable=too-few-public-methods
    """Small ChatClient-compatible fallback for tests and no-key demos."""

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Return a tool call first, then a concise SOP-grounded answer."""
        del tools
        if not any(message.get("role") == "tool" for message in messages):
            return _tool_call_response(_select_files(_last_user_message(messages)))
        return _answer_response(messages)


def _last_user_message(messages: list[JsonObject]) -> str:
    """Return the latest user message."""
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _select_files(message: str) -> list[str]:
    """Select likely SOP files without listing the data directory."""
    folded = message.casefold()
    rules = (
        (
            "p0" in folded or "响应流程" in message or "升级流程" in message,
            ["sop-001.html", "sop-002.html", "sop-005.html"],
        ),
        ("主从" in message or "数据库" in message, ["sop-002.html"]),
        ("oom" in folded or "outofmemory" in folded or "内存" in message, ["sop-001.html"]),
        (
            "入侵" in message or "黑客" in message or "安全" in message or "攻击" in message,
            ["sop-005.html"],
        ),
        ("推荐" in message or "模型" in message or "算法" in message, ["sop-008.html"]),
        ("cdn" in folded or "dns" in folded, ["sop-010.html"]),
    )
    for matches, files in rules:
        if matches:
            return files
    return ["sop-001.html"]


def _tool_call_response(fnames: list[str]) -> JsonObject:
    """Return an assistant message requesting readFile calls."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": "readFile",
                                "arguments": f'{{"fname":"{fname}"}}',
                            },
                        }
                        for index, fname in enumerate(fnames, start=1)
                    ],
                }
            }
        ]
    }


def _answer_response(messages: list[JsonObject]) -> JsonObject:
    """Return a final local answer from tool observations."""
    tool_text = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "tool"
    )
    if "OutOfMemoryError" in tool_text or "OOM" in tool_text:
        content = "服务 OOM 时需要保存堆转储文件，检查 JVM 内存曲线，必要时扩容或回滚。"
    elif "主从" in tool_text:
        content = "数据库主从延迟时先检查复制线程状态和错误信息，修复后验证数据一致性。"
    elif "安全" in tool_text or "入侵" in tool_text:
        content = "安全事件先确认影响范围并隔离受感染资产，保留日志证据后升级安全负责人。"
    else:
        content = "请先确认影响范围、查看监控和近期变更，再按相关 SOP 执行处理和升级。"
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}
