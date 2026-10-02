from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_mcp
from app.mcp.manager import MCPClientManager
from app.schemas.api import ServersResponse, ToolCallRequest, ToolCallResponse, ToolsResponse

router = APIRouter(prefix="/api/v1")


@router.get("/servers", response_model=ServersResponse)
async def list_servers(mcp: Annotated[MCPClientManager, Depends(get_mcp)]) -> ServersResponse:
    return ServersResponse(servers=mcp.list_servers())


@router.get("/tools", response_model=ToolsResponse)
async def list_tools(mcp: Annotated[MCPClientManager, Depends(get_mcp)]) -> ToolsResponse:
    return ToolsResponse(tools=mcp.list_tools())


@router.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(
    body: ToolCallRequest, mcp: Annotated[MCPClientManager, Depends(get_mcp)]
) -> ToolCallResponse:
    info = mcp.validate_arguments(body.tool_name, body.arguments)  # 404 / 422
    result = await mcp.call_tool(info.name, body.arguments)
    return ToolCallResponse(tool_name=info.name, server=info.server, result=result)
