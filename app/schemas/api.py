from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import Message, ServerInfo, ToolCall, ToolInfo, ToolResult


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_provider: str
    servers_configured: int
    servers_connected: int


class ServersResponse(BaseModel):
    servers: list[ServerInfo]


class ToolsResponse(BaseModel):
    tools: list[ToolInfo]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    llm_provider: str
    ui: list[dict[str, Any]] = Field(default_factory=list, description="A2UI v0.8 messages for the reply")


class SessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    messages: list[Message]


class ToolCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, description="Bare or '<server>__<tool>' name")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    tool_name: str  # namespaced
    server: str
    result: Any


class UserAction(BaseModel):
    """A2UI v0.8 client-to-server userAction."""

    name: str = Field(min_length=1)
    surfaceId: str = Field(min_length=1)
    sourceComponentId: str = ""
    timestamp: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class UIActionRequest(BaseModel):
    session_id: str | None = None
    userAction: UserAction


class UIActionResponse(BaseModel):
    tool_name: str
    messages: list[dict[str, Any]]
