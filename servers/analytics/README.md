# Analytics MCP Server

Standalone FastMCP server with traffic analytics over **mock** data (deterministic, generated in `data.py`). It does not connect to any ANPR system or database. Junction IDs (`JN-001` to `JN-016`) match the Investigation server's mock detections.

## Run
```powershell
uv run python -m servers.analytics
```
Streamable HTTP at `http://127.0.0.1:8102/mcp`. Override with `ANALYTICS_HOST`, `ANALYTICS_PORT`, `LOG_LEVEL`.

## Tools
All results carry `found`, `message`, `mock_data: true`. Timestamps are ISO 8601 (IST when no offset); ranges are `[start_time, end_time)`, max 31 days. Data covers 2026-09-19 to 2026-10-02 (IST, all 16 junctions in servers/common/chennai.py); hours outside it count as 0 and the message says so. Unknown junctions return `found: false`; malformed input returns a tool error.

| Tool | Inputs | Returns |
|---|---|---|
| `get_vehicle_count` | `start_time`, `end_time`, `junction_id?` | total vehicles + filters |
| `get_junction_statistics` | `junction_id`, `start_time`, `end_time` | total, avg/hour, busiest hour, counts by type |
| `get_vehicle_type_distribution` | `start_time`, `end_time`, `junction_id?` | count and % per vehicle type |
| `get_hourly_traffic` | `date` (YYYY-MM-DD), `junction_id?` | 24 hourly counts + peak hour |
| `compare_junctions` | `junction_ids` (2-10), `start_time`, `end_time` | per-junction stats, share %, busiest first |

## Test
`uv run pytest tests/test_analytics_server.py tests/test_multi_server_host.py`

## Connect to the runtime
Add to `MCP_SERVERS` in `.env` (alongside investigation): `{"name":"analytics","url":"http://127.0.0.1:8102/mcp"}`. Tools appear as `analytics__<tool>`.

## Layout
`models.py` schemas/validation · `data.py` mock data · `repository.py` data access · `tools.py` logic · `server.py` FastMCP wiring.
