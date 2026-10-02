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
        "detection_id", "plate_number", "vehicle_type", "confidence", "junction_id", "timestamp", "direction",
        "camera_id", "lane", "speed_kmph"
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
    assert all(e["uri"].startswith("s3://chn-anpr-evidence/2026/09/30/JN-003/CAM-003-03/DET-0003/") for e in ev["evidence"])


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


def test_dataset_looks_like_a_real_feed():
    from collections import Counter

    from servers.common.chennai import BY_ID, bearing
    from servers.investigation.data import COVERAGE_END, COVERAGE_START, MOCK_RECORDS, MOCK_VEHICLES

    assert len(MOCK_RECORDS) > 2000 and len(MOCK_VEHICLES) > 60
    assert len({r.detection_id for r in MOCK_RECORDS}) == len(MOCK_RECORDS)
    assert all(COVERAGE_START <= r.timestamp < COVERAGE_END for r in MOCK_RECORDS[4:])
    assert sum(v.plate_number.startswith("TN") for v in MOCK_VEHICLES) / len(MOCK_VEHICLES) > 0.8
    assert all(r.camera_id.startswith(f"CAM-{r.junction_id[3:]}-") for r in MOCK_RECORDS)

    # heavy trucks run at night (light goods vehicles may run by day)
    heavy = {v.plate_number for v in MOCK_VEHICLES if v.vehicle_type == "truck" and v.model not in ("Dost+", "Ace Gold")}
    hours = [r.timestamp.hour for r in MOCK_RECORDS[4:] if r.plate_number in heavy]
    assert hours and all(h >= 22 or h < 6 for h in hours)

    # consecutive sightings in one trip head roughly towards the next junction
    by_plate: dict[str, list] = {}
    for r in MOCK_RECORDS[4:]:
        by_plate.setdefault(r.plate_number, []).append(r)
    checked = agree = 0
    for rows in by_plate.values():
        for a, b in zip(rows, rows[1:]):
            if a.junction_id != b.junction_id and (b.timestamp - a.timestamp).total_seconds() < 1800:
                checked += 1
                agree += a.direction == bearing(BY_ID[a.junction_id], BY_ID[b.junction_id])
    assert checked > 200 and agree / checked > 0.6

    # some reads have no registry record (misreads), with low confidence
    registered = {v.plate_number for v in MOCK_VEHICLES}
    misreads = [r for r in MOCK_RECORDS if r.plate_number not in registered]
    assert misreads and all(r.confidence < 0.75 for r in misreads)
    assert Counter(r.vehicle_type for r in MOCK_RECORDS).most_common(1)[0][0] in ("car", "motorcycle")


def test_long_histories_are_capped():
    from servers.investigation.data import MOCK_RECORDS
    from servers.investigation.tools import HISTORY_LIMIT, SEARCH_LIMIT, get_vehicle_history

    busiest = max({r.plate_number for r in MOCK_RECORDS}, key=lambda p: sum(r.plate_number == p for r in MOCK_RECORDS))
    hist = get_vehicle_history(busiest)
    assert hist.total > HISTORY_LIMIT and len(hist.records) == HISTORY_LIMIT
    assert hist.records[-1].timestamp == max(r.timestamp for r in MOCK_RECORDS if r.plate_number == busiest)
    found = search_vehicle(busiest)
    assert found.total == hist.total and len(found.records) == SEARCH_LIMIT
