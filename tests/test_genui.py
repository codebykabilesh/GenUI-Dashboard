"""A2UI generation and userAction handling, with the real Investigation and Analytics
servers over FastMCP's in-memory transport."""

import json

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.core.config import MCPServerConfig, Settings
from app.genui.a2ui import CATALOG_ID, CUSTOM_COMPONENTS, to_contents
from app.main import create_app
from servers.analytics.server import mcp as analytics_server
from servers.investigation.server import mcp as investigation_server
from tests.test_chat_stream import StreamFake, parse_sse
from tests.test_llm_chat import FakeLLM, completion, make_provider, tc

SERVERS = {"investigation": investigation_server, "analytics": analytics_server}
DAY = {"start_time": "2026-09-30T00:00:00Z", "end_time": "2026-10-01T00:00:00Z"}
STANDARD = {"Text", "Row", "Column", "List", "Card", "Divider", "Button", "TextField",
            "DateTimeInput", "MultipleChoice", "CheckBox", "Tabs", "Image"}
CUSTOM = set(CUSTOM_COMPONENTS)


def factory(config: MCPServerConfig) -> Client:
    return Client(SERVERS[config.name])


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None,
        mcp_servers=[MCPServerConfig(name=n, url=f"http://{n}.invalid/mcp") for n in SERVERS],
    )
    with TestClient(create_app(settings, client_factory=factory, llm_provider=make_provider(FakeLLM(lambda r: completion("ok"))))) as c:
        yield c


def check_surfaces(messages: list[dict]) -> dict[str, dict]:
    """Validate A2UI structure; return {surfaceId: {"components": {...}, "root": id}}."""
    surfaces: dict[str, dict] = {}
    for m in messages:
        (kind, body), = m.items()
        s = surfaces.setdefault(body["surfaceId"], {"components": {}, "root": None, "data": []})
        if kind == "surfaceUpdate":
            for c in body["components"]:
                (ctype, props), = c["component"].items()
                assert ctype in STANDARD | CUSTOM, ctype
                s["components"][c["id"]] = (ctype, props)
        elif kind == "dataModelUpdate":
            s["data"] = body["contents"]
        elif kind == "beginRendering":
            assert body["catalogId"] == CATALOG_ID
            s["root"] = body["root"]
    for sid, s in surfaces.items():
        assert s["root"] in s["components"], sid
        for ctype, props in s["components"].values():  # every reference resolves
            refs = [props.get("child")] if "child" in props else []
            ch = props.get("children", {})
            refs += ch.get("explicitList", []) + ([ch["template"]["componentId"]] if "template" in ch else [])
            for ref in refs:
                assert ref in s["components"], (sid, ctype, ref)
    return surfaces


def call(client, tool, **args):
    r = client.post("/api/v1/tools/call", json={"tool_name": tool, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()


def render(client, tool, args, result):
    # run on the app's event loop, where the MCP connections live
    return client.portal.call(client.app.state.genui.render, tool, args, result)


def actions_in(surface: dict) -> set[str]:
    return {p["action"]["name"] for _, p in surface["components"].values() if "action" in p}


@pytest.mark.parametrize("tool,args,expect_actions", [
    ("search_vehicle", {"registration_number": "KA01AB1234"}, {"open_evidence", "vehicle_details", "search_vehicle"}),
    ("search_vehicle", {"registration_number": "ZZ99ZZ9999"}, {"search_vehicle"}),
    ("get_vehicle_history", {"registration_number": "KA01AB1234"}, {"open_evidence"}),
    ("get_vehicle_details", {"registration_number": "MH12XY9876"}, {"vehicle_history"}),
    ("get_detection_by_id", {"detection_id": "DET-0002"}, {"open_evidence", "vehicle_history"}),
    ("get_detection_evidence", {"detection_id": "DET-0002"}, {"open_detection"}),
    ("get_vehicle_count", DAY, {"vehicle_count"}),
    ("get_junction_statistics", {"junction_id": "JN-001", **DAY}, {"junction_stats"}),
    ("get_vehicle_type_distribution", DAY, {"type_distribution"}),
    ("get_hourly_traffic", {"date": "2026-09-30"}, {"hourly_traffic"}),
    ("compare_junctions", {"junction_ids": ["JN-001", "JN-014"], **DAY}, {"compare_junctions"}),
])
def test_every_tool_renders_a_valid_interactive_surface(client, tool, args, expect_actions):
    result = call(client, tool, **args)["result"]
    messages = render(client, tool, args, result)
    surfaces = check_surfaces(messages)
    assert len(surfaces) == 1
    surface = next(iter(surfaces.values()))
    assert expect_actions <= actions_in(surface)
    assert "mock" not in json.dumps(messages).lower().replace("mock://", "")  # no mock wording in the UI


def test_analytics_surfaces_offer_discovered_junctions(client):
    result = call(client, "get_hourly_traffic", date="2026-09-30")["result"]
    surface = next(iter(check_surfaces(render(client, "get_hourly_traffic", {}, result)).values()))
    choice = next(p for t, p in surface["components"].values() if t == "MultipleChoice")
    assert [o["value"] for o in choice["options"]] == ["all"] + [f"JN-{i:03d}" for i in range(1, 17)]
    chart = next(p for t, p in surface["components"].values() if t == "BarChart")
    assert chart["orientation"] == "vertical" and chart["colorMode"] == "heat"
    hours = next(e for e in surface["data"] if e["key"] == "hours")["valueMap"]
    assert len(hours) == 24


def test_to_contents_encodes_lists_and_types():
    out = to_contents({"a": "x", "n": 3, "ok": True, "items": [{"v": 1}], "skip": None})
    assert out == [
        {"key": "a", "valueString": "x"},
        {"key": "n", "valueNumber": 3},
        {"key": "ok", "valueBoolean": True},
        {"key": "items", "valueMap": [{"key": "0", "valueMap": [{"key": "v", "valueNumber": 1}]}]},
    ]


def action(client, name, surface_id, context, session_id=None):
    return client.post("/api/v1/ui/action", json={
        "session_id": session_id,
        "userAction": {"name": name, "surfaceId": surface_id, "sourceComponentId": "c1",
                       "timestamp": "2026-10-03T10:00:00Z", "context": context},
    })


def test_filter_action_replaces_the_same_surface(client):
    r = action(client, "hourly_traffic", "get-hourly-traffic-abc12345", {"date": "2026-09-30", "junction_id": ["JN-014"]})
    assert r.status_code == 200
    body = r.json()
    assert body["tool_name"] == "analytics__get_hourly_traffic"
    assert set(check_surfaces(body["messages"])) == {"get-hourly-traffic-abc12345"}


def test_navigation_action_adds_a_new_surface(client):
    r = action(client, "open_evidence", "search-vehicle-abc12345", {"detection_id": "DET-0001"})
    sid, = check_surfaces(r.json()["messages"])
    assert sid.startswith("get-detection-evidence-") and sid != "search-vehicle-abc12345"


def test_all_junctions_choice_means_no_filter(client):
    r = action(client, "vehicle_count", "get-vehicle-count-1", {**DAY, "junction_id": ["all"]})
    assert r.status_code == 200
    texts = json.dumps(r.json()["messages"])
    assert "all junctions" in texts.lower()


def test_action_errors(client):
    r = action(client, "drop_tables", "x", {})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_action"
    r = action(client, "search_vehicle", "x", {"registration_number": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_tool_arguments"
    r = action(client, "search_vehicle", "x", {"registration_number": "!!"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "tool_error"
    r = action(client, "compare_junctions", "x", {**DAY, "junction_ids": ["JN-001"]})
    assert r.status_code == 422


def test_action_is_recorded_in_the_session(client):
    sid = client.post("/api/v1/chat", json={"message": "hi"}).json()["session_id"]
    assert action(client, "open_detection", "x", {"detection_id": "DET-0003"}, sid).status_code == 200
    roles = [m["role"] for m in client.get(f"/api/v1/sessions/{sid}").json()["messages"]]
    assert roles == ["user", "assistant", "assistant", "tool"]


def test_chat_stream_emits_a2ui_and_done_carries_ui():
    fake = StreamFake(
        lambda r: completion(tool_calls=[tc("h", "analytics__get_hourly_traffic", {"date": "2026-09-30"})]),
        lambda r: completion("Peak at 08:00 (mock data)."),
    )
    settings = Settings(_env_file=None, mcp_servers=[MCPServerConfig(name=n, url=f"http://{n}.invalid/mcp") for n in SERVERS])
    with TestClient(create_app(settings, client_factory=factory, llm_provider=make_provider(fake))) as c:
        events = parse_sse(c.post("/api/v1/chat/stream", json={"message": "hourly traffic"}).text)
    kinds = [k for k, _ in events]
    assert kinds.index("tool_result") < kinds.index("a2ui") < kinds.index("done")
    a2ui = next(d for k, d in events if k == "a2ui")["messages"]
    check_surfaces(a2ui)
    assert events[-1][1]["ui"] == a2ui
