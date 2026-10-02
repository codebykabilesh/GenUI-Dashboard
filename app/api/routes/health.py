from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.core.deps import get_mcp, get_settings_dep
from app.mcp.manager import MCPClientManager
from app.schemas.api import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    mcp: Annotated[MCPClientManager, Depends(get_mcp)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> HealthResponse:
    servers = mcp.list_servers()
    return HealthResponse(
        llm_provider=settings.llm_provider,
        servers_configured=len(servers),
        servers_connected=sum(s.status == "connected" for s in servers),
    )
