import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from servers.investigation.server import mcp
from servers.investigation.tools import get_detection_by_id, search_vehicle

TOOLS = {
    "search_vehicle",
    "get_vehicle_details",
    "get_vehicle_history",
    "get_detection_evidence",
    "get_detection_by_id",
}


async def call(name: str, args: dict) -> dict:
    async with Client(mcp) as c:
        return (await c.call_tool(name, args)).structured_content


async def test_five_tools_registered():
    async with Client(mcp) as c:
        assert {t.name for t in await c.list_tools()} == TOOLS


async def test_search_success_via_mcp():
    data = await call("search_vehicle", {"registration_number": "ka-01 ab 1234"})
    assert data["found"] is True and data["query"] == "KA01AB1234" and data["mock_data"] is True
    assert len(data["records"]) == 2
    assert set(data["records"][0]) == {
        "detection_id", "plate_number", "vehicle_type", "confidence", "junction_id", "timestamp", "direction"
    }


async def test_search_not_found_via_mcp():
    data = await call("search_vehicle", {"registration_number": "ZZ99ZZ9999"})
    assert data["found"] is False and data["records"] == []
    assert "No vehicle found" in data["message"]


async def test_vehicle_details():
    data = await call("get_vehicle_details", {"registration_number": "MH12XY9876"})
    assert data["found"] and data["vehicle"]["make"] == "Tata"
    missing = await call("get_vehicle_details", {"registration_number": "ZZ99ZZ9999"})
    assert missing["found"] is False and missing["vehicle"] is None


async def test_vehicle_history_ordered():
    data = await call("get_vehicle_history", {"registration_number": "KA01AB1234"})
    assert data["total"] == 2
    assert [r["detection_id"] for r in data["records"]] == ["DET-0001", "DET-0002"]
    assert (await call("get_vehicle_history", {"registration_number": "ZZ99ZZ9999"}))["found"] is False


async def test_detection_by_id_and_evidence():
    data = await call("get_detection_by_id", {"detection_id": "det-0003"})
    assert data["found"] and data["record"]["plate_number"] == "KA05MN4321"
    ev = await call("get_detection_evidence", {"detection_id": "DET-0003"})
    assert ev["found"] and {e["kind"] for e in ev["evidence"]} == {"vehicle_image", "plate_crop", "video_clip"}
    assert all(e["uri"].startswith("mock://") for e in ev["evidence"])


async def test_unknown_detection_id_is_graceful():
    assert (await call("get_detection_by_id", {"detection_id": "DET-9999"}))["found"] is False
    assert (await call("get_detection_evidence", {"detection_id": "DET-9999"}))["found"] is False


async def test_invalid_input_is_tool_error():
    async with Client(mcp) as c:
        with pytest.raises(ToolError, match="Invalid input"):
            await c.call_tool("search_vehicle", {"registration_number": "!!"})
        with pytest.raises(ToolError, match="Invalid input"):
            await c.call_tool("get_detection_by_id", {"detection_id": "nope"})


def test_logic_directly():
    assert search_vehicle("MH12XY9876").records[0].vehicle_type == "truck"
    assert not search_vehicle("NOPE1234").found
    assert get_detection_by_id("DET-0001").record.junction_id == "JN-001"
