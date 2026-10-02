from typing import Protocol

from pydantic import BaseModel, Field

from app.schemas.common import Message, ToolCall, ToolInfo


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse: ...
