import pytest
from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP

from app.core.config import MCPServerConfig, Settings
from app.main import create_app


def make_test_server() -> FastMCP:
    """In-process FastMCP server used only to exercise the client path in tests."""
    server = FastMCP("test-server")

    @server.tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool
    def boom() -> str:
        """Always fails."""
        raise ValueError("kaboom")

    return server


def _settings(servers: list[MCPServerConfig]) -> Settings:
    return Settings(_env_file=None, mcp_servers=servers, mcp_connect_timeout=2)


@pytest.fixture
def client_no_servers():
    with TestClient(create_app(_settings([]))) as c:
        yield c


@pytest.fixture
def client_with_server():
    cfg = [
        MCPServerConfig(name="demo", url="http://test.invalid/mcp"),
        MCPServerConfig(name="off", url="http://test.invalid/mcp", enabled=False),
    ]
    server = make_test_server()

    def factory(config: MCPServerConfig) -> Client:
        return Client(server)  # in-memory transport

    with TestClient(create_app(_settings(cfg), client_factory=factory)) as c:
        yield c


@pytest.fixture
def client_unreachable_server():
    cfg = [MCPServerConfig(name="dead", url="http://127.0.0.1:9/mcp")]
    with TestClient(create_app(_settings(cfg))) as c:
        yield c
