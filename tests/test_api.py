import pytest

from app.core.config import MCPServerConfig


def test_health_without_servers(client_no_servers):
    r = client_no_servers.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "llm_provider": "mock",
        "servers_configured": 0,
        "servers_connected": 0,
    }


def test_servers_and_tools_empty(client_no_servers):
    assert client_no_servers.get("/api/v1/servers").json() == {"servers": []}
    assert client_no_servers.get("/api/v1/tools").json() == {"tools": []}


def test_chat_and_session_history(client_no_servers):
    r = client_no_servers.post("/api/v1/chat", json={"message": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert "no MCP servers connected" in body["reply"]
    assert body["tool_calls"] == []
    sid = body["session_id"]

    r2 = client_no_servers.post("/api/v1/chat", json={"message": "again", "session_id": sid})
    assert r2.json()["session_id"] == sid

    s = client_no_servers.get(f"/api/v1/sessions/{sid}").json()
    assert [m["role"] for m in s["messages"]] == ["user", "assistant", "user", "assistant"]


def test_unknown_session_404(client_no_servers):
    r = client_no_servers.get("/api/v1/sessions/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "session_not_found"
    r = client_no_servers.post("/api/v1/chat", json={"message": "x", "session_id": "nope"})
    assert r.status_code == 404


def test_chat_validation(client_no_servers):
    assert client_no_servers.post("/api/v1/chat", json={"message": ""}).status_code == 422


def test_unreachable_server_is_reported_failed(client_unreachable_server):
    servers = client_unreachable_server.get("/api/v1/servers").json()["servers"]
    assert servers[0]["name"] == "dead"
    assert servers[0]["status"] == "failed"
    assert servers[0]["error"]
    assert client_unreachable_server.get("/api/v1/tools").json()["tools"] == []
    assert client_unreachable_server.get("/health").json()["servers_connected"] == 0


def test_server_discovery(client_with_server):
    servers = {s["name"]: s for s in client_with_server.get("/api/v1/servers").json()["servers"]}
    assert servers["demo"]["status"] == "connected"
    assert servers["demo"]["tool_count"] == 2
    assert servers["off"]["status"] == "disabled"
    names = {t["name"] for t in client_with_server.get("/api/v1/tools").json()["tools"]}
    assert names == {"demo__add", "demo__boom"}


def test_chat_invokes_real_mcp_tool(client_with_server):
    # mock LLM requests the tool with empty args -> server rejects; surfaced as tool error
    r = client_with_server.post("/api/v1/chat", json={"message": "please run demo__add"})
    body = r.json()
    assert body["tool_calls"][0]["name"] == "add"  # bare alias offered to the LLM
    assert body["tool_results"][0]["is_error"] is True


def test_chat_tool_success_and_error(client_with_server):
    mcp = client_with_server.app.state.mcp

    async def go():
        return await mcp.call_tool("demo__add", {"a": 2, "b": 3})

    # run on the app's own loop via portal
    result = client_with_server.portal.call(go)
    assert result == {"result": 5}

    with pytest.raises(Exception, match="kaboom"):
        client_with_server.portal.call(lambda: mcp.call_tool("demo__boom", {}))


def test_unknown_tool(client_with_server):
    from app.core.errors import ToolNotFoundError

    with pytest.raises(ToolNotFoundError):
        client_with_server.portal.call(
            lambda: client_with_server.app.state.mcp.call_tool("demo__missing", {})
        )


def test_server_config_requires_exactly_one_transport():
    with pytest.raises(ValueError):
        MCPServerConfig(name="x")
    with pytest.raises(ValueError):
        MCPServerConfig(name="x", url="http://a", command="b")
