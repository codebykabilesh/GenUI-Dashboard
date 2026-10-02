from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.schemas.common import Message, ToolCall, ToolInfo


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class StreamEvent(BaseModel):
    """`delta`: a piece of text. `final`: the complete response (always last)."""

    kind: Literal["delta", "final"]
    text: str = ""
    response: LLMResponse | None = None


class LLMProvider(Protocol):
    name: str

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse: ...

    def stream(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> AsyncIterator[StreamEvent]: ...
