# Investigation MCP Server

Standalone FastMCP server exposing `search_vehicle` over **mock** ANPR data. It does not connect to any ANPR system or database.

## Install
Uses the project environment: `uv sync` (from the repo root).

## Run
```powershell
uv run python -m servers.investigation
```
Serves streamable HTTP at `http://127.0.0.1:8101/mcp`. Override with `INVESTIGATION_HOST`, `INVESTIGATION_PORT`, `LOG_LEVEL`.

## Tools
All results share an envelope: `found`, `message`, `mock_data: true`. Unknown vehicles/IDs return `found: false`; malformed input returns a tool error.

| Tool | Input | Returns |
|---|---|---|
| `search_vehicle` | `registration_number` | matching detection records |
| `get_vehicle_details` | `registration_number` | make, model, colour, registered state |
| `get_vehicle_history` | `registration_number` | all detections, oldest first |
| `get_detection_by_id` | `detection_id` (e.g. `DET-0001`) | one detection record |
| `get_detection_evidence` | `detection_id` | placeholder `mock://` evidence references |

Plates are normalised (case, spaces, hyphens ignored). Each sighting has a camera ID, lane and speed.

Reference plates: `KA01AB1234` (DET-0001, DET-0002), `KA05MN4321` (DET-0003), `MH12XY9876` (DET-0004). The full development dataset (`data.py`) has ~85 registered vehicles and ~3,600 sightings from 19 Sep to 2 Oct 2026 (IST) across 16 Chennai junctions (`servers/common/chennai.py`). Searches return the latest 20 sightings and histories the latest 50; `total` gives the full count.

## Test
`uv run pytest tests/`

## Connect to the runtime
In `.env`: `MCP_SERVERS=[{"name":"investigation","url":"http://127.0.0.1:8101/mcp"}]`
The tool then appears as `investigation__search_vehicle`.

## Layout
`models.py` schemas · `data.py` mock data · `repository.py` shared data access · `tools.py` logic · `server.py` FastMCP wiring/transport.
