# GenUI MCP Runtime

FastAPI MCP host for the GenUI app.
Flow: Frontend → FastAPI Runtime → MCP Client (FastMCP) → MCP Servers → ANPR APIs.

MCP servers live in `servers/investigation` and `servers/analytics` (development data). The frontend in `frontend/` is the ANPR Console. With no MCP servers configured the app still starts and `/api/v1/tools` is empty.

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
| POST | `/api/v1/chat/stream` | same as chat, streamed as Server-Sent Events: `session`, `delta`, `tool_call`, `tool_result`, then `a2ui`, then `done` (or `error`) |
| POST | `/api/v1/ui/action` | A2UI `userAction` from a panel → runs the mapped tool, returns A2UI messages |
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

Providers (`LLM_PROVIDER`): `mock` (no key, replies prefixed `[mock LLM]`), `groq` (reads `GROQ_API_KEY`/`GROQ_MODEL`, e.g. `openai/gpt-oss-120b`), `openrouter`, `openai_compatible` (any `/chat/completions` API with native tool calling; set `LLM_BASE_URL`). Configure `LLM_MODEL` and `LLM_API_KEY` (openrouter also reads `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`). The model must support tool calling. To add a non-OpenAI-style provider, implement `LLMProvider` (`app/llm/base.py`) and register it in `create_provider`.

## Generative UI (A2UI)

Each tool result is rendered as an interactive panel using [A2UI v0.8](https://a2ui.org/specification/v0.8-a2ui/): the runtime emits `surfaceUpdate` / `dataModelUpdate` / `beginRendering` messages (`app/genui/`), streamed as `a2ui` events and returned in `ChatResponse.ui`. The frontend renders them with a small React renderer (`frontend/src/a2ui/`) covering the standard catalog plus custom components (catalog `genui-anpr/v1`, listed in `CUSTOM_COMPONENTS` in `app/genui/a2ui.py`). The frontend follows `UI_THEME.md`: all colours come from `frontend/src/tokens.css` (light default, `data-theme="dark"` for dark).

The LLM chooses tools; panels are composed from tool results by the runtime, so they only ever show tool data. Buttons, filters and plates send A2UI `userAction`s to `POST /api/v1/ui/action`, which maps whitelisted action names to tools (`app/genui/actions.py`), validates arguments against the tool schema, and returns updated A2UI messages without an LLM round-trip. Filter changes re-render the same panel; navigation (evidence, vehicle record) adds a new one. Actions are recorded in the session so follow-up questions have context.
