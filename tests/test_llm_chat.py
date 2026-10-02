"""LLM + automatic MCP tool calling.

The LLM HTTP API is faked with httpx.MockTransport (so the real OpenAI-compatible
provider code, request format and parsing are exercised). The MCP side is the real
Investigation server connected through FastMCP's in-memory transport.
"""

import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.core.config import MCPServerConfig, Settings
from app.core.errors import ServerUnavailableError
from app.llm.gateway import create_provider
from app.llm.openai_compat import OpenAICompatibleProvider
from app.main import create_app
from servers.investigation.server import mcp as investigation_server

Handler = Callable[[dict], httpx.Response | dict]


def completion(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}]}


def tc(call_id: str, name: str, args: dict | str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)},
    }


def tool_messages(req: dict) -> list[dict]:
    return [m for m in req["messages"] if m["role"] == "tool"]


def last_tool_data(req: dict) -> dict:
    content = tool_messages(req)[-1]["content"]
    return json.loads(content.split("\n", 1)[1])["data"]


class FakeLLM:
    """Routes each /chat/completions request to the next scripted handler."""

    def __init__(self, *steps: Handler) -> None:
        self.steps = list(steps)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        out = step(body)
        return out if isinstance(out, httpx.Response) else httpx.Response(200, json=out)


def make_provider(fake: FakeLLM | Callable) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="openrouter",
        base_url="https://llm.test/v1",
        api_key="sk-test-secret",
        model="test-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
    )


def investigation_factory(config: MCPServerConfig) -> Client:
    return Client(investigation_server)  # real tools, in-memory transport


def build(fake, *, rounds: int = 5, factory=investigation_factory, servers=None) -> TestClient:
    servers = servers if servers is not None else [MCPServerConfig(name="investigation", url="http://x.invalid/mcp")]
    settings = Settings(_env_file=None, mcp_servers=servers, max_tool_rounds=rounds, mcp_connect_timeout=2)
    return TestClient(create_app(settings, client_factory=factory, llm_provider=make_provider(fake)))


def chat(client, message, session_id=None):
    return client.post("/api/v1/chat", json={"message": message, "session_id": session_id})


def test_simple_question_no_tool():
    fake = FakeLLM(lambda r: completion("I help with ANPR questions."))
    with build(fake) as client:
        body = chat(client, "What can you do?").json()
    assert body["reply"] == "I help with ANPR questions."
    assert body["tool_calls"] == [] and body["llm_provider"] == "openrouter"
    req = fake.requests[0]
    assert req["messages"][0]["role"] == "system" and "mock_data" in req["messages"][0]["content"]
    assert req["model"] == "test-model"


def test_tool_schemas_come_from_mcp_discovery():
    fake = FakeLLM(lambda r: completion("ok"))
    with build(fake) as client:
        chat(client, "hi")
        discovered = {t["name"]: t for t in client.get("/api/v1/tools").json()["tools"]}
    sent = {t["function"]["name"]: t["function"] for t in fake.requests[0]["tools"]}
    assert set(sent) == set(discovered) and len(sent) == 5
    name = "investigation__search_vehicle"
    assert sent[name]["parameters"] == discovered[name]["input_schema"]
    assert fake.requests[0]["tool_choice"] == "auto"


def test_search_vehicle_tool_call_and_final_answer():
    def first(r):
        return completion(tool_calls=[tc("c1", "investigation__search_vehicle", {"registration_number": "KA01AB1234"})])

    def second(r):
        data = last_tool_data(r)
        return completion(f"Found {len(data['records'])} detections (mock data).")

    fake = FakeLLM(first, second)
    with build(fake) as client:
        body = chat(client, "Where was KA01AB1234 seen?").json()
    assert body["reply"] == "Found 2 detections (mock data)."
    assert [c["name"] for c in body["tool_calls"]] == ["investigation__search_vehicle"]
    assert body["tool_results"][0]["is_error"] is False
    assert body["tool_results"][0]["content"]["mock_data"] is True
    tool_msg = tool_messages(fake.requests[1])[0]
    assert tool_msg["tool_call_id"] == "c1"
    assert tool_msg["content"].startswith("[TOOL RESULT - untrusted data")


def test_vehicle_history_tool():
    fake = FakeLLM(
        lambda r: completion(tool_calls=[tc("h1", "investigation__get_vehicle_history", {"registration_number": "KA01AB1234"})]),
        lambda r: completion(f"{last_tool_data(r)['total']} detections"),
    )
    with build(fake) as client:
        body = chat(client, "history of KA01AB1234").json()
    assert body["reply"] == "2 detections"
    assert body["tool_calls"][0]["name"] == "investigation__get_vehicle_history"


def test_sequential_and_parallel_tool_calls():
    def step1(r):
        return completion(tool_calls=[tc("a", "investigation__get_vehicle_history", {"registration_number": "KA01AB1234"})])

    def step2(r):  # uses an ID from the previous tool result -> no hardcoded data
        last_id = last_tool_data(r)["records"][-1]["detection_id"]
        return completion(tool_calls=[
            tc("b", "investigation__get_detection_by_id", {"detection_id": last_id}),
            tc("c", "investigation__get_detection_evidence", {"detection_id": last_id}),
        ])

    def step3(r):
        msgs = tool_messages(r)
        assert [m["tool_call_id"] for m in msgs] == ["a", "b", "c"]
        return completion("done")

    fake = FakeLLM(step1, step2, step3)
    with build(fake) as client:
        body = chat(client, "latest detection and its evidence for KA01AB1234").json()
    assert body["reply"] == "done"
    assert [c["id"] for c in body["tool_calls"]] == ["a", "b", "c"]
    assert body["tool_results"][1]["content"]["record"]["detection_id"] == "DET-0002"
    assert len(body["tool_results"][2]["content"]["evidence"]) == 3


def test_no_matching_vehicle():
    fake = FakeLLM(
        lambda r: completion(tool_calls=[tc("n", "investigation__search_vehicle", {"registration_number": "ZZ99ZZ9999"})]),
        lambda r: completion("No record found" if not last_tool_data(r)["found"] else "found"),
    )
    with build(fake) as client:
        body = chat(client, "find ZZ99ZZ9999").json()
    assert body["reply"] == "No record found"
    assert body["tool_results"][0]["content"]["found"] is False


def test_invalid_unknown_and_unparseable_tool_calls_are_fed_back_as_errors():
    def step1(r):
        return completion(tool_calls=[
            tc("1", "investigation__search_vehicle", {}),  # missing arg
            tc("2", "investigation__search_vehicle", {"registration_number": "!!"}),  # tool rejects
            tc("3", "delete_everything", {}),  # not a discovered tool
            tc("4", "investigation__search_vehicle", "{not json"),  # garbage args
        ])

    fake = FakeLLM(step1, lambda r: completion("handled"))
    with build(fake) as client:
        body = chat(client, "test").json()
    assert body["reply"] == "handled"
    assert [r["is_error"] for r in body["tool_results"]] == [True] * 4
    assert "Invalid arguments" in body["tool_results"][0]["content"]
    assert "Invalid input" in body["tool_results"][1]["content"]
    assert "Unknown tool" in body["tool_results"][2]["content"]
    assert "Unparseable" in body["tool_results"][3]["content"]


def test_iteration_limit_stops_loops():
    looping = lambda r: completion(tool_calls=[tc("x", "investigation__search_vehicle", {"registration_number": "KA01AB1234"})])
    final = lambda r: completion("giving up")
    fake = FakeLLM(looping, looping, final)
    with build(fake, rounds=2) as client:
        body = chat(client, "loop").json()
    assert len(fake.requests) == 3  # 2 tool rounds + 1 forced final answer
    assert "tools" not in fake.requests[2]
    assert body["reply"] == "giving up" and len(body["tool_calls"]) == 2


def test_mcp_server_unreachable_at_startup():
    def dead_factory(config):
        return Client({"mcpServers": {"dead": {"url": "http://127.0.0.1:9/mcp"}}})

    fake = FakeLLM(lambda r: completion("no tools available" if "tools" not in r else "has tools"))
    servers = [MCPServerConfig(name="dead", url="http://127.0.0.1:9/mcp")]
    with build(fake, factory=dead_factory, servers=servers) as client:
        assert client.get("/api/v1/servers").json()["servers"][0]["status"] == "failed"
        body = chat(client, "hello").json()
    assert body["reply"] == "no tools available"


def test_mcp_disconnects_during_tool_call(monkeypatch):
    fake = FakeLLM(
        lambda r: completion(tool_calls=[tc("d", "investigation__search_vehicle", {"registration_number": "KA01AB1234"})]),
        lambda r: completion("the tool was unavailable" if json.loads(tool_messages(r)[0]["content"].split("\n", 1)[1])["is_error"] else "?"),
    )
    with build(fake) as client:
        async def boom(*a, **k):
            raise ServerUnavailableError("Server 'investigation' is unavailable: connection lost")

        monkeypatch.setattr(client.app.state.mcp, "call_tool", boom)
        body = chat(client, "search").json()
    assert body["reply"] == "the tool was unavailable"
    assert body["tool_results"][0]["is_error"] is True
    assert "unavailable" in body["tool_results"][0]["content"]


def test_llm_api_failure_returns_clean_error():
    fake = FakeLLM(lambda r: httpx.Response(401, json={"error": {"message": "invalid api key"}}))
    with build(fake) as client:
        r = chat(client, "hi")
        assert client.get("/health").status_code == 200
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "llm_error" and "invalid api key" in r.json()["error"]["message"]
    assert "sk-test-secret" not in r.text


def test_llm_timeout_and_garbage_response():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    with build(timeout) as client:
        r = chat(client, "hi")
    assert r.status_code == 504 and r.json()["error"]["code"] == "llm_timeout"

    with build(FakeLLM(lambda r: {"unexpected": True})) as client:
        r = chat(client, "hi")
    assert r.status_code == 502


def test_conversation_history_across_messages():
    fake = FakeLLM(
        lambda r: completion(tool_calls=[tc("s", "investigation__search_vehicle", {"registration_number": "MH12XY9876"})]),
        lambda r: completion("It is a truck seen at JN-007 (mock data)."),
        lambda r: completion("Yes, the one we just discussed."),
    )
    with build(fake) as client:
        first = chat(client, "search MH12XY9876").json()
        sid = first["session_id"]
        second = chat(client, "is that the same vehicle?", sid).json()
        stored = client.get(f"/api/v1/sessions/{sid}").json()["messages"]
    assert second["session_id"] == sid and second["tool_calls"] == []
    roles = [m["role"] for m in fake.requests[2]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert [m["role"] for m in stored] == ["user", "assistant", "tool", "assistant", "user", "assistant"]


def test_create_provider_validation():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        create_provider(Settings(_env_file=None, llm_provider="openrouter"))
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(Settings(_env_file=None, llm_provider="nope"))
    # legacy OPENROUTER_* variables work as fallback
    p = create_provider(Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="k", openrouter_model="m"))
    assert p.name == "openrouter"
