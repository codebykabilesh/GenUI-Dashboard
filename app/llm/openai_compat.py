"""Provider for any OpenAI-compatible /chat/completions API with native tool calling
(OpenRouter, OpenAI, vLLM, Ollama's OpenAI endpoint, ...)."""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.errors import LLMProviderError, LLMTimeoutError
from app.llm.base import LLMResponse, StreamEvent
from app.schemas.common import Message, ToolCall, ToolInfo

logger = logging.getLogger(__name__)


def tools_to_openai(tools: list[ToolInfo]) -> list[dict[str, Any]]:
    """MCP tool definitions -> OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def messages_to_openai(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in m.tool_calls
                ]
            out.append(entry)
        elif m.role == "tool" and m.tool_result:
            out.append(
                {"role": "tool", "tool_call_id": m.tool_result.call_id, "content": m.content}
            )
    return out


MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT = 20.0  # seconds; longer waits are reported instead of retried


class _RateLimited(Exception):
    """HTTP 429 with a short, known wait: safe to retry."""

    def __init__(self, wait: float, body: Any) -> None:
        super().__init__(f"rate limited, retry in {wait:.1f}s")
        self.wait = wait
        self.body = body


def _retry_after(headers: httpx.Headers, body: Any) -> float | None:
    """Seconds to wait, from the Retry-After header or a 'try again in 1m2.5s' message."""
    header = headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    message = ""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = str(body["error"].get("message", ""))
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", message)
    if not m:
        return None
    value = float(m.group(2)) / (1000 if m.group(3) == "ms" else 1)
    return int(m.group(1) or 0) * 60 + value


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._timeout = timeout
        self._sleep = asyncio.sleep  # replaceable in tests

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages_to_openai(messages, system),
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools_to_openai(tools)
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    def _api_error(status: int, body: Any) -> LLMProviderError:
        detail = ""
        if isinstance(body, dict):
            err = body.get("error")
            detail = err.get("message", "") if isinstance(err, dict) else str(err or "")
        logger.warning("LLM API error status=%s detail=%s", status, detail)
        return LLMProviderError(f"LLM API error (HTTP {status}): {detail or 'no detail'}")

    async def _backoff(self, attempt: int, limited: _RateLimited) -> None:
        """Wait out a short rate limit, or give up with the provider's error."""
        if attempt >= MAX_RATE_LIMIT_RETRIES or limited.wait > MAX_RATE_LIMIT_WAIT:
            raise self._api_error(429, limited.body)
        logger.info("LLM rate limited; retrying in %.1fs (attempt %d)", limited.wait, attempt + 1)
        await self._sleep(limited.wait + 0.25)

    async def stream(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Server-sent-events streaming; yields text deltas then one final event.

        A 429 arrives before any data, so retrying it never repeats output.
        """
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                async for event in self._stream_once(messages, tools, system):
                    yield event
                return
            except _RateLimited as limited:
                await self._backoff(attempt, limited)

    async def _stream_once(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None
    ) -> AsyncIterator[StreamEvent]:
        payload = self._payload(messages, tools, system, stream=True)
        content: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        try:
            async with self._client.stream(
                "POST", self._url, json=payload, headers=self._headers, timeout=self._timeout
            ) as resp:
                if resp.status_code >= 400:
                    raw = await resp.aread()
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        body = None
                    wait = _retry_after(resp.headers, body) if resp.status_code == 429 else None
                    if wait is not None:
                        raise _RateLimited(wait, body)
                    raise self._api_error(resp.status_code, body)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # blank lines and ": keep-alive" comments
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if "error" in chunk:
                        raise self._api_error(resp.status_code, chunk)
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if text := delta.get("content"):
                            content.append(text)
                            yield StreamEvent(kind="delta", text=text)
                        for part in delta.get("tool_calls") or []:
                            slot = calls.setdefault(
                                part.get("index", 0), {"id": None, "name": "", "arguments": ""}
                            )
                            slot["id"] = part.get("id") or slot["id"]
                            fn = part.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"LLM request timed out after {self._timeout:g}s") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"LLM request failed: {type(exc).__name__}: {exc}") from exc

        tool_calls = [
            self._parse_call(
                {"id": c["id"], "function": {"name": c["name"], "arguments": c["arguments"]}}
            )
            for _, c in sorted(calls.items())
        ]
        yield StreamEvent(
            kind="final", response=LLMResponse(content="".join(content), tool_calls=tool_calls)
        )

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                return await self._complete_once(messages, tools, system)
            except _RateLimited as limited:
                await self._backoff(attempt, limited)
        raise AssertionError("unreachable")

    async def _complete_once(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None
    ) -> LLMResponse:
        payload = self._payload(messages, tools, system, stream=False)
        try:
            resp = await self._client.post(
                self._url, json=payload, headers=self._headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"LLM request timed out after {self._timeout:g}s") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"LLM request failed: {type(exc).__name__}: {exc}") from exc

        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code == 429 and (wait := _retry_after(resp.headers, body)) is not None:
            raise _RateLimited(wait, body)
        if resp.status_code >= 400 or not isinstance(body, dict) or "error" in body:
            raise self._api_error(resp.status_code, body)

        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("LLM API returned an unexpected response shape") from exc
        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=[self._parse_call(c) for c in msg.get("tool_calls") or []],
        )

    @staticmethod
    def _parse_call(raw: dict[str, Any]) -> ToolCall:
        fn = raw.get("function", {})
        call_id = raw.get("id") or uuid.uuid4().hex[:12]
        name = fn.get("name", "")
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
            return ToolCall(id=call_id, name=name, arguments=args)
        except ValueError as exc:
            return ToolCall(id=call_id, name=name, argument_error=f"Unparseable arguments: {exc}")
