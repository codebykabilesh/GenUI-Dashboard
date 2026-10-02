"""Host connected to BOTH MCP servers at once, over real HTTP (subprocesses)."""

import os
import socket
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import MCPServerConfig, Settings
from app.main import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(module: str, port_var: str, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", module],
        env={**os.environ, port_var: str(port)},
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
                raise RuntimeError(f"{module} exited early")
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"{module} did not start")


@pytest.fixture
def host():
    p1, p2 = free_port(), free_port()
    procs = [
        start("servers.investigation", "INVESTIGATION_PORT", p1),
        start("servers.analytics", "ANALYTICS_PORT", p2),
    ]
    settings = Settings(
        _env_file=None,
        mcp_servers=[
            MCPServerConfig(name="investigation", url=f"http://127.0.0.1:{p1}/mcp"),
            MCPServerConfig(name="analytics", url=f"http://127.0.0.1:{p2}/mcp"),
        ],
        mcp_connect_timeout=5,
        mcp_call_timeout=5,
    )
    try:
        with TestClient(create_app(settings)) as client:
            yield client, procs
    finally:
        for p in procs:
            p.kill()


def call(client, name, **arguments):
    return client.post("/api/v1/tools/call", json={"tool_name": name, "arguments": arguments})


def test_both_servers_connect_and_all_ten_tools_are_discovered(host):
    client, _ = host
    servers = {s["name"]: s for s in client.get("/api/v1/servers").json()["servers"]}
    assert servers["investigation"]["status"] == "connected" and servers["investigation"]["tool_count"] == 5
    assert servers["analytics"]["status"] == "connected" and servers["analytics"]["tool_count"] == 5
    names = {t["name"] for t in client.get("/api/v1/tools").json()["tools"]}
    assert len(names) == 10
    assert {"analytics__get_vehicle_count", "analytics__compare_junctions", "investigation__search_vehicle"} <= names
    assert client.get("/health").json()["servers_connected"] == 2


def test_invoke_tools_on_both_servers(host):
    client, _ = host
    r = call(client, "search_vehicle", registration_number="KA01AB1234")
    assert r.status_code == 200 and r.json()["server"] == "investigation"

    r = call(client, "get_vehicle_count", start_time="2026-09-30T00:00:00Z", end_time="2026-10-01T00:00:00Z")
    assert r.status_code == 200 and r.json()["server"] == "analytics"
    assert r.json()["result"]["mock_data"] is True and r.json()["result"]["total_vehicles"] > 0

    r = call(client, "analytics__compare_junctions", junction_ids=["JN-001", "JN-014"],
             start_time="2026-09-30T00:00:00Z", end_time="2026-10-01T00:00:00Z")
    assert r.json()["result"]["busiest_junction"] in ("JN-001", "JN-014")

    assert call(client, "get_hourly_traffic", date="2026-09-30").status_code == 200
    assert call(client, "get_junction_statistics", junction_id="JN-001",
                start_time="2026-09-30T00:00:00Z", end_time="2026-10-01T00:00:00Z").status_code == 200
    assert call(client, "get_vehicle_type_distribution",
                start_time="2026-09-30T00:00:00Z", end_time="2026-10-01T00:00:00Z").status_code == 200


def test_analytics_errors_and_isolation(host):
    client, procs = host
    r = call(client, "get_vehicle_count", start_time="nope", end_time="2026-10-01T00:00:00Z")
    assert r.status_code == 422 and r.json()["error"]["code"] == "tool_error"

    procs[1].kill()  # analytics goes down; investigation must keep working
    procs[1].wait()
    assert call(client, "get_hourly_traffic", date="2026-09-30").status_code in (502, 503)
    assert call(client, "search_vehicle", registration_number="KA01AB1234").status_code == 200
    statuses = {s["name"]: s["status"] for s in client.get("/api/v1/servers").json()["servers"]}
    assert statuses == {"investigation": "connected", "analytics": "failed"}
