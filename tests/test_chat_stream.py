"""POST /api/v1/chat/stream (Server-Sent Events) with the real OpenAI-compatible
streaming parser, a faked LLM HTTP API and the real Investigation tools."""

import json

import httpx

from tests.test_llm_chat import (
    FakeLLM,
    build,
    completion,
    last_tool_data,
    tc,
)


def sse_response(comp: dict) -> httpx.Response:
    """Turn a non-streaming completion dict into an OpenAI-style SSE stream."""
    msg = comp["choices"][0]["message"]
    chunks: list[dict] = []
    text = msg.get("content") or ""
    for i in range(0, len(text), 5):
        chunks.append({"choices": [{"delta": {"content": text[i : i + 5]}}]})
    for idx, call in enumerate(msg.get("tool_calls") or []):
        args = call["function"]["arguments"]
        half = len(args) // 2
        chunks.append({"choices": [{"delta": {"tool_calls": [
            {"index": idx, "id": call["id"], "function": {"name": call["function"]["name"], "arguments": args[:half]}}
        ]}}]})
        chunks.append({"choices": [{"delta": {"tool_calls": [
            {"index": idx, "function": {"arguments": args[half:]}}
        ]}}]})
    body = ": keep-alive\n\n" + "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


class StreamFake(FakeLLM):
    def __call__(self, request: httpx.Request) -> httpx.Response:
        out = super().__call__(request)
        body = self.requests[-1]
        if body.get("stream") and out.status_code == 200:
            return sse_response(json.loads(out.content))
        return out


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def stream(client, message, session_id=None):
    return client.post("/api/v1/chat/stream", json={"message": message, "session_id": session_id})


def test_stream_plain_answer_arrives_in_deltas():
    fake = StreamFake(lambda r: completion("Hello from the assistant."))
    with build(fake) as client:
        r = stream(client, "hi")
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert events[0][0] == "session"
    deltas = [d["text"] for k, d in events if k == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == "Hello from the assistant."
    kind, done = events[-1]
    assert kind == "done" and done["reply"] == "Hello from the assistant." and done["session_id"] == events[0][1]["session_id"]
    assert fake.requests[0]["stream"] is True


def test_stream_tool_call_flow_and_reassembled_arguments():
    fake = StreamFake(
        lambda r: completion(tool_calls=[tc("s1", "investigation__search_vehicle", {"registration_number": "MH12XY9876"})]),
        lambda r: completion(f"Found {len(last_tool_data(r)['records'])} record (mock data)."),
    )
    with build(fake) as client:
        events = parse_sse(stream(client, "search MH12XY9876").text)
    kinds = [k for k, _ in events]
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("done")
    call = next(d for k, d in events if k == "tool_call")
    assert call["name"] == "investigation__search_vehicle" and call["arguments"] == {"registration_number": "MH12XY9876"}
    assert next(d for k, d in events if k == "tool_result")["is_error"] is False
    done = events[-1][1]
    assert done["reply"] == "Found 1 record (mock data)."
    assert done["tool_results"][0]["content"]["found"] is True


def test_stream_llm_failure_is_an_error_event():
    fake = StreamFake(lambda r: httpx.Response(401, json={"error": {"message": "invalid api key"}}))
    with build(fake) as client:
        r = stream(client, "hi")
        assert client.get("/health").status_code == 200
    assert r.status_code == 200  # stream already open; failure reported in-band
    kind, data = parse_sse(r.text)[-1]
    assert kind == "error" and data["code"] == "llm_error" and "invalid api key" in data["message"]
    assert "sk-test-secret" not in r.text


def test_stream_unknown_session_is_404():
    with build(StreamFake(lambda r: completion("x"))) as client:
        r = stream(client, "hi", "gone")
    assert r.status_code == 404 and r.json()["error"]["code"] == "session_not_found"


def test_stream_keeps_session_history():
    fake = StreamFake(lambda r: completion("first"), lambda r: completion("second"))
    with build(fake) as client:
        sid = parse_sse(stream(client, "one").text)[0][1]["session_id"]
        stream(client, "two", sid)
        stored = client.get(f"/api/v1/sessions/{sid}").json()["messages"]
    assert [m["role"] for m in stored] == ["user", "assistant", "user", "assistant"]
    assert [m["role"] for m in fake.requests[1]["messages"]] == ["system", "user", "assistant", "user"]


def test_stream_retries_a_short_rate_limit():
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from tests.test_llm_chat import RATE_LIMITED, _no_sleep_provider

    fake = StreamFake(lambda r: httpx.Response(429, json=RATE_LIMITED), lambda r: completion("streamed after wait"))
    provider = _no_sleep_provider(fake)
    with TestClient(create_app(Settings(_env_file=None, mcp_servers=[]), llm_provider=provider)) as client:
        events = parse_sse(client.post("/api/v1/chat/stream", json={"message": "hi"}).text)
    assert events[-1][0] == "done" and events[-1][1]["reply"] == "streamed after wait"
    assert len(provider.waits) == 1
