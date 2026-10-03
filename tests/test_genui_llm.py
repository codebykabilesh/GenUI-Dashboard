"""LLM-designed GenUI panels: layout validation, chat integration, fallback and reuse."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.core.config import MCPServerConfig, Settings
from app.genui.designer import DESIGNER_PROMPT, LayoutError, compile_layout, parse_layout
from app.main import create_app
from servers.analytics.server import mcp as analytics_server
from servers.investigation.server import mcp as investigation_server
from tests.test_genui import action, call, check_surfaces
from tests.test_llm_chat import completion, make_provider, tc

SERVERS = {"investigation": investigation_server, "analytics": analytics_server}

HOURLY_LAYOUT = {
    "root": "main",
    "components": [
        {"id": "main", "type": "Column", "children": ["title", "peak", "chart", "filters", "mix"]},
        {"id": "title", "type": "Text", "text": {"path": "/summary/title"}, "hint": "h4"},
        {"id": "peak", "type": "Stat", "label": "Peak hour", "value": {"path": "/summary/stats/peak_hour/value"},
         "size": "large"},
        {"id": "chart", "type": "BarChart", "data": "/hours", "orientation": "vertical", "colorMode": "heat",
         "unit": "vehicles"},
        {"id": "filters", "type": "Block", "name": "filters"},
        {"id": "mix", "type": "Button", "label": "Vehicle mix", "action": "type_distribution",
         "context": {"junction_id": {"path": "/junction"}}},
    ],
}


class Router:
    """Fake LLM API: designer requests get `layouts` in turn, chat requests get `chat` in turn."""

    def __init__(self, chat: list, layouts: list) -> None:
        self.chat, self.layouts = chat, layouts
        self.chat_requests: list[dict] = []
        self.layout_requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["messages"][0]["content"] == DESIGNER_PROMPT:
            self.layout_requests.append(body)
            out = self.layouts.pop(0) if len(self.layouts) > 1 else self.layouts[0]
            return httpx.Response(200, json=completion(out if isinstance(out, str) else json.dumps(out)))
        self.chat_requests.append(body)
        step = self.chat.pop(0) if len(self.chat) > 1 else self.chat[0]
        return httpx.Response(200, json=step(body))


def build(router: Router) -> TestClient:
    settings = Settings(
        _env_file=None,
        genui_llm_layout=True,
        mcp_servers=[MCPServerConfig(name=n, url=f"http://{n}.invalid/mcp") for n in SERVERS],
    )
    return TestClient(create_app(settings, client_factory=lambda c: Client(SERVERS[c.name]),
                                 llm_provider=make_provider(router)))


def hourly_chat(router_layouts: list) -> Router:
    return Router(
        chat=[
            lambda r: completion(tool_calls=[tc("h", "get_hourly_traffic", {"date": "2026-09-30"})]),
            lambda r: completion("Traffic peaked in the evening."),
        ],
        layouts=router_layouts,
    )


def components(messages: list[dict]) -> dict[str, tuple[str, dict]]:
    (surface,) = check_surfaces(messages).values()
    return surface["components"]


def test_chat_panel_uses_the_llm_layout():
    router = hourly_chat([HOURLY_LAYOUT])
    with build(router) as client:
        body = client.post("/api/v1/chat", json={"message": "when was traffic busiest on 30 Sep?"}).json()
    comps = components(body["ui"])
    types = {t for t, _ in comps.values()}
    assert {"BarChart", "Stat", "Filters", "MultipleChoice"} <= types
    assert "Donut" not in types and "u-chart" in comps  # the LLM's components, not the template's
    # the designer saw the user's request and the data model, and figures stay data-bound
    req = json.loads(router.layout_requests[0]["messages"][1]["content"])
    assert req["request"] == "when was traffic busiest on 30 Sep?" and req["tool"] == "get_hourly_traffic"
    assert req["list_lengths"]["/hours"] == 24 and len(req["data_model"]["hours"]) == 3
    assert comps["u-peak"][1]["value"] == {"path": "/summary/stats/peak_hour/value"}
    assert body["reply"] == "Traffic peaked in the evening."


def test_invalid_layout_is_repaired_once_then_falls_back_to_the_template():
    bad = {"root": "x", "components": [{"id": "x", "type": "Stat", "label": "Peak", "value": "987654321"}]}
    router = hourly_chat([bad, "not json at all"])
    with build(router) as client:
        body = client.post("/api/v1/chat", json={"message": "hourly traffic 30 Sep"}).json()
    assert len(router.layout_requests) == 2
    assert "rejected" in router.layout_requests[1]["messages"][-1]["content"]
    comps = components(body["ui"])
    assert not any(cid.startswith("u-") for cid in comps)  # template layout
    assert any(t == "BarChart" for t, _ in comps.values())


def test_repaired_layout_is_used():
    bad = {"root": "x", "components": [{"id": "x", "type": "Sparkline", "data": "/hours"}]}
    router = hourly_chat([bad, HOURLY_LAYOUT])
    with build(router) as client:
        body = client.post("/api/v1/chat", json={"message": "hourly traffic 30 Sep"}).json()
    assert "u-chart" in components(body["ui"])


def test_filter_change_keeps_the_llm_layout_without_another_llm_call():
    router = hourly_chat([HOURLY_LAYOUT])
    with build(router) as client:
        body = client.post("/api/v1/chat", json={"message": "hourly traffic 30 Sep"}).json()
        (sid,) = check_surfaces(body["ui"])
        r = action(client, "hourly_traffic", sid, {"date": "2026-09-29", "junction_id": ["JN-002"]})
    assert r.status_code == 200
    assert len(router.layout_requests) == 1
    comps = components(r.json()["messages"])
    assert "u-chart" in comps and "Donut" not in {t for t, _ in comps.values()}


def test_navigation_from_a_panel_gets_a_fresh_llm_layout():
    evidence_layout = {"root": "r", "components": [
        {"id": "r", "type": "Column", "children": ["h", "frames"]},
        {"id": "h", "type": "Text", "text": {"path": "/summary/title"}, "hint": "h4"},
        {"id": "frames", "type": "List", "items": "/evidence", "item": "f", "direction": "horizontal"},
        {"id": "f", "type": "EvidenceFrame", "kind": {"path": "kind"}, "label": {"path": "label"},
         "uri": {"path": "uri"}},
    ]}
    router = Router(chat=[lambda r: completion("ok")], layouts=[evidence_layout])
    with build(router) as client:
        r = action(client, "open_evidence", "search-vehicle-abc12345", {"detection_id": "DET-0001"})
    assert "clicked 'open_evidence'" in json.loads(router.layout_requests[0]["messages"][1]["content"])["request"]
    assert "u-f" in components(r.json()["messages"])


# validation ------------------------------------------------------------------

@pytest.fixture(scope="module")
def hourly_surface():
    settings = Settings(_env_file=None, mcp_servers=[MCPServerConfig(name="analytics", url="http://a.invalid/mcp")])
    with TestClient(create_app(settings, client_factory=lambda c: Client(analytics_server))) as client:
        result = call(client, "get_hourly_traffic", date="2026-09-30")["result"]
        surface, _ = client.portal.call(client.app.state.genui.composer.build, "get_hourly_traffic", {}, result)
    return surface


def layout(*comps: dict, root: str = "a") -> str:
    return json.dumps({"root": root, "components": list(comps)})


@pytest.mark.parametrize("reply,error", [
    ("Here is a panel!", "no JSON"),
    (layout({"id": "a", "type": "Stat", "label": "Vehicles", "value": "123456789"}), "number not in the data"),
    (layout({"id": "a", "type": "Text", "text": {"path": "/nope"}}), "does not exist"),
    (layout({"id": "a", "type": "Text", "text": {"path": "label"}}), "outside a List"),
    (layout({"id": "a", "type": "Text", "text": {"path": "/hours"}}), "not a single value"),
    (layout({"id": "a", "type": "Donut", "data": "/summary"}), "label, value"),
    (layout({"id": "a", "type": "Button", "label": "Go", "action": "delete_everything"}), "unknown action"),
    (layout({"id": "a", "type": "Iframe", "src": "x"}), "unknown type"),
    (layout({"id": "a", "type": "Text", "text": "hi", "onClick": "x"}), "unknown props"),
    (layout({"id": "a", "type": "Column", "children": ["a"]}), "contains itself"),
    (layout({"id": "a", "type": "Column", "children": ["b"]}), "unknown component"),
    (layout({"id": "a", "type": "Block", "name": "search"}), "not available"),
    (layout({"id": "a", "type": "Text", "text": "x", "hint": "h1"}), "must be one of"),
])
def test_layout_rules(hourly_surface, reply, error):
    with pytest.raises(LayoutError, match=error):
        compile_layout(parse_layout(reply), hourly_surface)


def test_list_items_bind_relative_paths(hourly_surface):
    reply = layout(
        {"id": "a", "type": "List", "items": "/hours", "item": "row"},
        {"id": "row", "type": "Row", "children": ["h", "n"]},
        {"id": "h", "type": "Text", "text": {"path": "label"}},
        {"id": "n", "type": "Text", "text": {"path": "value"}},
    )
    comps = components(compile_layout(parse_layout(reply), hourly_surface))
    assert comps["u-a"][1]["children"]["template"] == {"dataBinding": "/hours", "componentId": "u-row"}


def test_literal_digits_that_appear_in_the_data_are_allowed(hourly_surface):
    reply = layout({"id": "a", "type": "Text", "text": "Hourly traffic, 30 September 2026"})
    assert compile_layout(parse_layout(reply), hourly_surface)
