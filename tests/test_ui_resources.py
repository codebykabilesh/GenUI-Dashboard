"""MCP Apps (ui://) tool results are surfaced to the frontend as `ui_resources`."""

from fastapi.testclient import TestClient
from fastmcp import Client, FastMCP

from app.core.config import MCPServerConfig
from app.main import create_app
from tests.conftest import _settings

VIEW_URI = "ui://demo/view.html"
VIEW_HTML = "<html><body>view</body></html>"


def make_ui_server() -> FastMCP:
    server = FastMCP("ui-server")

    @server.resource(
        VIEW_URI,
        mime_type="text/html;profile=mcp-app",
        meta={"ui": {"csp": {"resourceDomains": ["https://cdn.example"]}}},
    )
    def view() -> str:
        return VIEW_HTML

    @server.tool(meta={"ui": {"resourceUri": VIEW_URI}})
    def show_view() -> dict:
        """Render the demo view."""
        return {"rows": [1, 2, 3]}

    @server.tool
    def plain() -> str:
        """No UI."""
        return "ok"

    return server


def _client() -> TestClient:
    server = make_ui_server()
    cfg = [MCPServerConfig(name="demo", url="http://test.invalid/mcp")]
    return TestClient(create_app(_settings(cfg), client_factory=lambda _c: Client(server)))


def test_tools_expose_ui_resource_uri():
    with _client() as c:
        tools = {t["name"]: t for t in c.get("/api/v1/tools").json()["tools"]}
    assert tools["demo__show_view"]["ui_resource_uri"] == VIEW_URI
    assert tools["demo__plain"]["ui_resource_uri"] is None


def test_chat_returns_ui_resource_for_ui_tool():
    with _client() as c:
        body = c.post("/api/v1/chat", json={"message": "please run demo__show_view"}).json()
    assert len(body["ui_resources"]) == 1
    ui = body["ui_resources"][0]
    assert ui["tool_name"] == "demo__show_view"
    assert ui["html"] == VIEW_HTML
    assert ui["csp"] == {"resourceDomains": ["https://cdn.example"]}
    assert ui["tool_result"] == {"rows": [1, 2, 3]} or ui["tool_result"] == {"result": {"rows": [1, 2, 3]}}


def test_chat_has_no_ui_resource_for_plain_tool():
    with _client() as c:
        body = c.post("/api/v1/chat", json={"message": "run demo__plain"}).json()
    assert body["ui_resources"] == []
