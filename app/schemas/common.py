from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str  # namespaced: "<server>__<tool>"
    arguments: dict[str, Any] = Field(default_factory=dict)
    argument_error: str | None = None  # set when the model sent unparseable arguments


class ToolResult(BaseModel):
    call_id: str
    name: str
    is_error: bool = False
    content: Any = None


class Message(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: ToolResult | None = None


class ToolInfo(BaseModel):
    name: str  # namespaced
    server: str
    tool: str  # name on the server
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    ui_resource_uri: str | None = None  # MCP App (ui://) resource that renders this tool's result


class ServerInfo(BaseModel):
    name: str
    transport: Literal["http", "stdio"]
    status: Literal["connected", "failed", "disabled", "disconnected"]
    error: str | None = None
    tool_count: int = 0
