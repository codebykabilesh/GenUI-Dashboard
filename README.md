# GenUI MCP Runtime

FastAPI MCP host for the GenUI app.
Flow: Frontend → FastAPI Runtime → MCP Client (FastMCP) → MCP Servers → ANPR APIs.

The Investigation MCP server lives in `servers/investigation` (mock ANPR data). With no MCP servers configured the app still starts and `/api/v1/tools` is empty.

## Run

```powershell
uv sync
copy .env.example .env      # optional
uv run uvicorn app.main:app --reload
uv run pytest
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, provider, server counts |
| GET | `/api/v1/servers` | configured servers + real status (`connected`/`failed`/`disabled`) |
| GET | `/api/v1/tools` | tools from connected servers, named `<server>__<tool>` |
| POST | `/api/v1/chat` | `{message, session_id?}` → reply, tool calls/results |
| GET | `/api/v1/sessions/{id}` | conversation history |

## Configuring MCP servers

Set `MCP_SERVERS` (JSON list) or `MCP_SERVERS_FILE` in `.env`:

```json
[{"name": "investigation", "url": "http://localhost:9001/mcp"},
 {"name": "local", "command": "python", "args": ["server.py"]}]
```

Unreachable servers are reported as `failed` with the error; they are retried on next tool call.

## Layout

`app/core` config, errors, DI · `app/sessions` in-memory sessions · `app/mcp` FastMCP client manager · `app/llm` gateway + mock provider · `app/orchestrator` chat loop · `app/api/routes` · `app/schemas`.

## LLM and automatic tool calling

`POST /api/v1/chat` runs: user message -> LLM -> tool calls -> MCP -> tool results -> LLM -> answer, repeating up to `MAX_TOOL_ROUNDS`. Parallel tool calls in one response are executed concurrently. Tool schemas are the ones discovered from the MCP servers; only discovered tools can run, arguments are validated against their schema, and tool output is passed back to the model as labelled untrusted data. Errors (bad arguments, unavailable server) are returned to the model as tool errors; LLM failures return 502/504 (`llm_error`/`llm_timeout`).

Providers (`LLM_PROVIDER`): `mock` (no key, replies prefixed `[mock LLM]`), `openrouter`, `openai_compatible` (any `/chat/completions` API with native tool calling; set `LLM_BASE_URL`). Configure `LLM_MODEL` and `LLM_API_KEY` (openrouter also reads `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`). The model must support tool calling. To add a non-OpenAI-style provider, implement `LLMProvider` (`app/llm/base.py`) and register it in `create_provider`.
