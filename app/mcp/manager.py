import asyncio
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client
from jsonschema import Draft202012Validator

from app.core.config import MCPServerConfig
from app.core.errors import (
    InvalidToolArgumentsError,
    MCPServerError,
    ServerUnavailableError,
    ToolExecutionError,
    ToolNotFoundError,
)
from app.schemas.common import ServerInfo, ToolInfo

logger = logging.getLogger(__name__)

SEP = "__"
ClientFactory = Callable[[MCPServerConfig], Client]


def default_client_factory(config: MCPServerConfig) -> Client:
    return Client(config.to_client_config(), name=f"genui-runtime-{config.name}")


def _ui_resource_uri(meta: dict[str, Any] | None) -> str | None:
    """MCP Apps: a tool links its view via `_meta.ui.resourceUri` (legacy `ui/resourceUri`)."""
    if not meta:
        return None
    ui = meta.get("ui")
    uri = ui.get("resourceUri") if isinstance(ui, dict) else meta.get("ui/resourceUri")
    return uri if isinstance(uri, str) and uri.startswith("ui://") else None


@dataclass
class _Connection:
    config: MCPServerConfig
    client: Client | None = None
    stack: AsyncExitStack | None = None
    status: str = "disconnected"
    error: str | None = None
    tools: list[ToolInfo] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MCPClientManager:
    """Holds one FastMCP Client connection per configured server.

    Only real connections are reported; a server that cannot be reached is
    marked "failed" and contributes no tools.
    """

    def __init__(
        self,
        servers: list[MCPServerConfig],
        connect_timeout: float = 10.0,
        call_timeout: float = 30.0,
        client_factory: ClientFactory = default_client_factory,
    ) -> None:
        self._conns = {s.name: _Connection(s) for s in servers}
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._factory = client_factory
        self._ui_cache: dict[tuple[str, str], tuple[str, dict[str, Any] | None]] = {}
        for conn in self._conns.values():
            if not conn.config.enabled:
                conn.status = "disabled"

    async def start(self) -> None:
        targets = [c for c in self._conns.values() if c.config.enabled]
        await asyncio.gather(*(self._connect(c) for c in targets))

    async def close(self) -> None:
        for conn in self._conns.values():
            await self._disconnect(conn)

    async def _connect(self, conn: _Connection) -> None:
        async with conn.lock:
            if conn.status == "connected":
                return
            await self._disconnect_locked(conn)
            stack = AsyncExitStack()
            try:
                client = self._factory(conn.config)
                async with asyncio.timeout(self._connect_timeout):
                    await stack.enter_async_context(client)
                    raw_tools = await client.list_tools()
                conn.client, conn.stack = client, stack
                conn.tools = [
                    ToolInfo(
                        name=f"{conn.config.name}{SEP}{t.name}",
                        server=conn.config.name,
                        tool=t.name,
                        description=t.description or "",
                        input_schema=t.input_schema,
                        ui_resource_uri=_ui_resource_uri(getattr(t, "meta", None)),
                    )
                    for t in raw_tools
                ]
                conn.status, conn.error = "connected", None
                logger.info("MCP server '%s' connected (%d tools)", conn.config.name, len(conn.tools))
            except BaseException as exc:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                await self._safe_aclose(stack)
                conn.client = conn.stack = None
                conn.tools = []
                conn.status, conn.error = "failed", str(exc) or type(exc).__name__
                logger.warning("MCP server '%s' failed to connect: %s", conn.config.name, conn.error)

    async def _disconnect(self, conn: _Connection) -> None:
        async with conn.lock:
            await self._disconnect_locked(conn)

    async def _disconnect_locked(self, conn: _Connection) -> None:
        if conn.stack is not None:
            await self._safe_aclose(conn.stack)
        conn.client = conn.stack = None
        conn.tools = []
        if conn.status != "disabled":
            conn.status = "disconnected"

    @staticmethod
    async def _safe_aclose(stack: AsyncExitStack) -> None:
        try:
            await stack.aclose()
        except Exception:
            logger.debug("Error while closing MCP client", exc_info=True)

    def list_servers(self) -> list[ServerInfo]:
        return [
            ServerInfo(
                name=c.config.name,
                transport="http" if c.config.url else "stdio",
                status=c.status,  # type: ignore[arg-type]
                error=c.error,
                tool_count=len(c.tools),
            )
            for c in self._conns.values()
        ]

    def list_tools(self) -> list[ToolInfo]:
        return [t for c in self._conns.values() if c.status == "connected" for t in c.tools]

    async def read_ui_resource(self, server: str, uri: str) -> tuple[str, dict[str, Any] | None]:
        """Fetch an MCP App `ui://` resource: (html, csp). Static, so cached per server."""
        conn = self._conns.get(server)
        if conn is None or conn.client is None or conn.status != "connected":
            raise ServerUnavailableError(f"Server '{server}' is unavailable")
        key = (server, uri)
        if key not in self._ui_cache:
            try:
                contents = await asyncio.wait_for(
                    conn.client.read_resource(uri), timeout=self._call_timeout
                )
            except Exception as exc:
                raise MCPServerError(f"Reading '{uri}' from '{server}' failed: {exc}") from exc
            part = contents[0] if contents else None
            html = getattr(part, "text", None)
            if not html:
                raise MCPServerError(f"Resource '{uri}' from '{server}' has no HTML content")
            meta = getattr(part, "meta", None) or {}
            ui = meta.get("ui") if isinstance(meta, dict) else None
            csp = ui.get("csp") if isinstance(ui, dict) else None
            self._ui_cache[key] = (html, csp)
        return self._ui_cache[key]

    async def refresh(self) -> None:
        """Reconnect failed/disconnected servers and re-discover tools."""
        pending = [
            c for c in self._conns.values() if c.config.enabled and c.status != "connected"
        ]
        await asyncio.gather(*(self._connect(c) for c in pending))

    def resolve_tool(self, name: str) -> tuple[str, str]:
        """Map a bare or namespaced tool name to (server, tool) among known servers' tools."""
        server, sep, tool = name.partition(SEP)
        if sep and server in self._conns:
            return server, tool
        matches = [
            (c.config.name, t.tool)
            for c in self._conns.values()
            for t in c.tools
            if t.tool == name
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f"{s}{SEP}{t}" for s, t in matches)
            raise ToolNotFoundError(f"Tool name '{name}' is ambiguous; use one of: {names}")
        raise ToolNotFoundError(f"Unknown tool '{name}'")

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> ToolInfo:
        """Resolve a tool and check arguments against its discovered JSON schema."""
        info = self.get_tool(name)
        errors = sorted(
            Draft202012Validator(info.input_schema).iter_errors(arguments),
            key=lambda e: list(e.path),
        )
        if errors:
            detail = "; ".join(
                f"{'.'.join(map(str, e.path)) or 'arguments'}: {e.message}" for e in errors
            )
            raise InvalidToolArgumentsError(f"Invalid arguments for '{info.name}': {detail}")
        return info

    def get_tool(self, name: str) -> ToolInfo:
        server, tool = self.resolve_tool(name)
        for t in self._conns[server].tools:
            if t.tool == tool:
                return t
        raise ToolNotFoundError(f"Unknown tool '{name}'")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        server, tool = self.resolve_tool(name)
        conn = self._conns[server]
        if conn.status != "connected":
            await self._connect(conn)
        if conn.client is None or conn.status != "connected":
            raise ServerUnavailableError(f"Server '{server}' is unavailable: {conn.error or conn.status}")
        if tool not in {t.tool for t in conn.tools}:
            raise ToolNotFoundError(f"Unknown tool '{server}{SEP}{tool}'")
        try:
            result = await conn.client.call_tool(
                tool, arguments, timeout=self._call_timeout, raise_on_error=False
            )
        except Exception as exc:
            # Connection likely broken; drop it so the next call reconnects.
            conn.status, conn.error = "failed", str(exc) or type(exc).__name__
            logger.warning("Call to %s%s%s failed: %s", server, SEP, tool, conn.error)
            raise MCPServerError(f"Call to '{server}{SEP}{tool}' failed: {conn.error}") from exc
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content).strip()
            raise ToolExecutionError(text or f"Tool '{server}{SEP}{tool}' returned an error")
        if result.structured_content is not None:
            return result.structured_content
        return " ".join(getattr(c, "text", "") for c in result.content)
