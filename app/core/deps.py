from fastapi import Request

from app.core.config import Settings
from app.genui.service import GenUIService
from app.mcp.manager import MCPClientManager
from app.orchestrator.orchestrator import Orchestrator
from app.sessions.manager import SessionManager


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


def get_mcp(request: Request) -> MCPClientManager:
    return request.app.state.mcp


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_genui(request: Request) -> GenUIService:
    return request.app.state.genui
