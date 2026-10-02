import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health, mcp
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.llm.base import LLMProvider
from app.llm.gateway import LLMGateway, create_provider
from app.mcp.manager import ClientFactory, MCPClientManager, default_client_factory
from app.orchestrator.orchestrator import Orchestrator
from app.sessions.manager import SessionManager

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    client_factory: ClientFactory = default_client_factory,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sessions = SessionManager()
        mcp_manager = MCPClientManager(
            settings.load_servers(),
            connect_timeout=settings.mcp_connect_timeout,
            call_timeout=settings.mcp_call_timeout,
            client_factory=client_factory,
        )
        llm = LLMGateway(llm_provider or create_provider(settings))
        app.state.settings = settings
        app.state.sessions = sessions
        app.state.mcp = mcp_manager
        app.state.orchestrator = Orchestrator(
            sessions, mcp_manager, llm, max_tool_rounds=settings.max_tool_rounds
        )
        await mcp_manager.start()
        logger.info("Runtime started (llm=%s)", llm.provider_name)
        try:
            yield
        finally:
            await mcp_manager.close()
            await llm.aclose()
            logger.info("Runtime stopped")

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(mcp.router)
    app.include_router(chat.router)
    return app


app = create_app()
