import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SessionNotFoundError(AppError):
    status_code = 404
    code = "session_not_found"


class MCPServerError(AppError):
    status_code = 502
    code = "mcp_error"


class LLMProviderError(AppError):
    status_code = 502
    code = "llm_error"


class LLMTimeoutError(LLMProviderError):
    status_code = 504
    code = "llm_timeout"


class ServerUnavailableError(MCPServerError):
    status_code = 503
    code = "mcp_server_unavailable"


class ToolExecutionError(AppError):
    """The tool ran and reported an error (e.g. invalid input)."""

    status_code = 422
    code = "tool_error"


class InvalidToolArgumentsError(AppError):
    status_code = 422
    code = "invalid_tool_arguments"


class ToolNotFoundError(MCPServerError):
    status_code = 404
    code = "tool_not_found"


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content=_body("internal_error", "Internal server error"))
