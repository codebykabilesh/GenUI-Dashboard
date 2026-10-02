"""Real Host -> Investigation Server tests over HTTP (server runs as a subprocess)."""

import os
import socket
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import MCPServerConfig, Settings
from app.main import create_app

EXPECTED_TOOLS = {
    "investigation__search_vehicle",
    "investigation__get_vehicle_details",
    "investigation__get_vehicle_history",
    "investigation__get_detection_evidence",
    "investigation__get_detection_by_id",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "INVESTIGATION_PORT": str(port)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "servers.investigation"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("investigation server exited early")
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("investigation server did not start")


@pytest.fixture
def stack():
    port = free_port()
    holder = {"proc": start_server(port), "port": port}
    settings = Settings(
        _env_file=None,
        mcp_servers=[MCPServerConfig(name="investigation", url=f"http://127.0.0.1:{port}/mcp")],
        mcp_connect_timeout=5,
        mcp_call_timeout=5,
    )
    try:
        with TestClient(create_app(settings)) as client:
            yield client, holder
    finally:
        holder["proc"].kill()


def call(client, name, **arguments):
    return client.post("/api/v1/tools/call", json={"tool_name": name, "arguments": arguments})


def test_connects_and_discovers_five_tools(stack):
    client, _ = stack
    srv = client.get("/api/v1/servers").json()["servers"][0]
    assert srv["status"] == "connected" and srv["tool_count"] == 5
    assert {t["name"] for t in client.get("/api/v1/tools").json()["tools"]} == EXPECTED_TOOLS
    assert client.get("/health").json()["servers_connected"] == 1


def test_all_tools_via_endpoint(stack):
    client, _ = stack
    r = call(client, "search_vehicle", registration_number="KA01AB1234")  # bare name
    assert r.status_code == 200
    assert r.json()["tool_name"] == "investigation__search_vehicle"
    assert len(r.json()["result"]["records"]) == 2

    r = call(client, "investigation__get_vehicle_details", registration_number="KA05MN4321")
    assert r.json()["result"]["vehicle"]["make"] == "Honda"

    r = call(client, "get_vehicle_history", registration_number="KA01AB1234")
    assert r.json()["result"]["total"] == 2

    r = call(client, "get_detection_evidence", detection_id="DET-0004")
    assert len(r.json()["result"]["evidence"]) == 3

    r = call(client, "get_detection_by_id", detection_id="DET-0004")
    assert r.json()["result"]["record"]["plate_number"] == "MH12XY9876"


def test_missing_entities_are_graceful(stack):
    client, _ = stack
    assert call(client, "search_vehicle", registration_number="ZZ99ZZ9999").json()["result"]["found"] is False
    assert call(client, "get_detection_by_id", detection_id="DET-9999").json()["result"]["found"] is False
    assert call(client, "get_detection_evidence", detection_id="DET-9999").json()["result"]["found"] is False


def test_error_cases(stack):
    client, _ = stack
    r = call(client, "does_not_exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "tool_not_found"
    r = call(client, "search_vehicle")  # missing argument -> schema validation
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_tool_arguments"
    r = call(client, "search_vehicle", registration_number=123)
    assert r.status_code == 422
    r = call(client, "search_vehicle", registration_number="!!")  # tool-level rejection
    assert r.status_code == 422 and r.json()["error"]["code"] == "tool_error"


def test_chat_uses_real_tool(stack):
    client, _ = stack
    body = client.post("/api/v1/chat", json={"message": "run search_vehicle"}).json()
    assert body["tool_calls"][0]["name"] == "search_vehicle"  # bare alias offered to the LLM


def test_disconnection_and_recovery(stack):
    client, holder = stack
    assert call(client, "search_vehicle", registration_number="KA01AB1234").status_code == 200

    holder["proc"].kill()
    holder["proc"].wait()
    r = call(client, "search_vehicle", registration_number="KA01AB1234")
    assert r.status_code in (502, 503)
    assert r.json()["error"]["code"] in ("mcp_error", "mcp_server_unavailable")
    assert client.get("/health").status_code == 200  # host stays up
    assert client.get("/api/v1/servers").json()["servers"][0]["status"] == "failed"
    assert client.get("/api/v1/tools").json()["tools"] == []

    holder["proc"] = start_server(holder["port"])  # server comes back
    r = call(client, "search_vehicle", registration_number="KA01AB1234")
    assert r.status_code == 200
    assert client.get("/api/v1/servers").json()["servers"][0]["status"] == "connected"
