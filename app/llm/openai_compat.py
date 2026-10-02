"""Provider for any OpenAI-compatible /chat/completions API with native tool calling
(OpenRouter, OpenAI, vLLM, Ollama's OpenAI endpoint, ...)."""

import json
import logging
import uuid
from typing import Any

import httpx

from app.core.errors import LLMProviderError, LLMTimeoutError
from app.llm.base import LLMResponse
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

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages_to_openai(messages, system),
        }
        if tools:
            payload["tools"] = tools_to_openai(tools)
            payload["tool_choice"] = "auto"
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
        if resp.status_code >= 400 or not isinstance(body, dict) or "error" in body:
            detail = ""
            if isinstance(body, dict):
                err = body.get("error")
                detail = err.get("message", "") if isinstance(err, dict) else str(err or "")
            logger.warning("LLM API error status=%s detail=%s", resp.status_code, detail)
            raise LLMProviderError(f"LLM API error (HTTP {resp.status_code}): {detail or 'no detail'}")

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
