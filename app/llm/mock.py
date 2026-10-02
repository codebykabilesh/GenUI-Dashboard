import uuid

from app.llm.base import LLMResponse
from app.schemas.common import Message, ToolCall, ToolInfo


class MockLLMProvider:
    """Deterministic stand-in for a real model. Needs no API key.

    - If the user's text names an available tool, requests that tool (empty args).
    - After a tool result, summarises it.
    - Otherwise echoes and lists the tools that are really available.
    """

    name = "mock"

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse:
        last = messages[-1] if messages else None
        if last and last.role == "tool" and last.tool_result:
            r = last.tool_result
            state = "failed" if r.is_error else "returned"
            return LLMResponse(content=f"[mock LLM] Tool '{r.name}' {state}: {r.content}")

        user_text = next((m.content for m in reversed(messages) if m.role == "user"), "")
        lowered = user_text.lower()
        for tool in tools:
            if tool.name.lower() in lowered or tool.tool.lower() in lowered:
                return LLMResponse(
                    content=f"[mock LLM] Calling {tool.name}",
                    tool_calls=[ToolCall(id=uuid.uuid4().hex[:12], name=tool.name)],
                )

        available = ", ".join(t.name for t in tools) or "none (no MCP servers connected)"
        return LLMResponse(
            content=f"[mock LLM] You said: {user_text!r}. Available MCP tools: {available}."
        )
