import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from servers.analytics.server import mcp

TOOLS = {
    "get_vehicle_count",
    "get_junction_statistics",
    "get_vehicle_type_distribution",
    "get_hourly_traffic",
    "compare_junctions",
}
DAY = {"start_time": "2026-09-30T00:00:00+05:30", "end_time": "2026-10-01T00:00:00+05:30"}  # one IST day


async def call(name: str, args: dict) -> dict:
    async with Client(mcp) as c:
        return (await c.call_tool(name, args)).structured_content


async def test_five_tools_with_descriptions():
    async with Client(mcp) as c:
        tools = await c.list_tools()
    assert {t.name for t in tools} == TOOLS
    assert all(t.description for t in tools)
    count = next(t for t in tools if t.name == "get_vehicle_count")
    assert count.input_schema["required"] == ["start_time", "end_time"]
    assert "description" in count.input_schema["properties"]["start_time"]


async def test_vehicle_count_all_and_single_junction():
    total = await call("get_vehicle_count", DAY)
    one = await call("get_vehicle_count", {**DAY, "junction_id": "jn-001"})
    assert total["found"] and total["mock_data"] is True and total["total_vehicles"] > 0
    assert one["junction_id"] == "JN-001" and one["junctions_included"] == ["JN-001"]
    assert 0 < one["total_vehicles"] < total["total_vehicles"]
    assert len(total["junctions_included"]) == 16


async def test_results_are_consistent_across_tools():
    count = (await call("get_vehicle_count", {**DAY, "junction_id": "JN-014"}))["total_vehicles"]
    stats = (await call("get_junction_statistics", {"junction_id": "JN-014", **DAY}))["statistics"]
    dist = await call("get_vehicle_type_distribution", {**DAY, "junction_id": "JN-014"})
    hourly = await call("get_hourly_traffic", {"date": "2026-09-30", "junction_id": "JN-014"})
    assert stats["total_detections"] == count == dist["total_vehicles"] == hourly["total_vehicles"]
    assert sum(stats["by_vehicle_type"].values()) == count
    assert sum(d["count"] for d in dist["distribution"]) == count
    assert abs(sum(d["percentage"] for d in dist["distribution"]) - 100) < 0.5
    assert stats["junction_name"] and stats["busiest_hour_start"] and stats["average_per_hour"] > 0


async def test_hourly_traffic_has_24_hours_and_peak():
    data = await call("get_hourly_traffic", {"date": "2026-09-30"})
    assert [h["hour"] for h in data["hours"]] == list(range(24))
    assert data["peak_hour"] in (9, 18)  # Chennai morning / evening peaks (IST)
    assert data["mock_data"] is True


async def test_compare_junctions():
    data = await call("compare_junctions", {"junction_ids": ["JN-001", "JN-014", "JN-003", "JN-999"], **DAY})
    ids = [j["junction_id"] for j in data["junctions"]]
    totals = [j["total_detections"] for j in data["junctions"]]
    assert totals == sorted(totals, reverse=True) and ids[0] == data["busiest_junction"]  # busiest first
    assert set(ids) == {"JN-001", "JN-014", "JN-003"} and data["unknown_junctions"] == ["JN-999"]
    assert abs(sum(j["share_of_total_pct"] for j in data["junctions"]) - 100) < 0.5
    single = (await call("get_junction_statistics", {"junction_id": "JN-001", **DAY}))["statistics"]
    assert next(j for j in data["junctions"] if j["junction_id"] == "JN-001")["total_detections"] == single["total_detections"]


async def test_unknown_junction_is_graceful():
    for name, args in [
        ("get_vehicle_count", {**DAY, "junction_id": "JN-999"}),
        ("get_junction_statistics", {"junction_id": "JN-999", **DAY}),
        ("get_vehicle_type_distribution", {**DAY, "junction_id": "JN-999"}),
        ("get_hourly_traffic", {"date": "2026-09-30", "junction_id": "JN-999"}),
        ("compare_junctions", {"junction_ids": ["JN-998", "JN-999"], **DAY}),
    ]:
        data = await call(name, args)
        assert data["found"] is False and "Unknown junction" in data["message"] and data["mock_data"] is True


async def test_out_of_coverage_returns_zero_with_note():
    data = await call("get_vehicle_count", {"start_time": "2030-01-01T00:00:00Z", "end_time": "2030-01-02T00:00:00Z"})
    assert data["found"] and data["total_vehicles"] == 0 and "only covers" in data["message"]
    hourly = await call("get_hourly_traffic", {"date": "2030-01-01"})
    assert hourly["total_vehicles"] == 0 and hourly["peak_hour"] is None


@pytest.mark.parametrize(
    "name,args,match",
    [
        ("get_vehicle_count", {"start_time": "yesterday", "end_time": "2026-10-01T00:00:00Z"}, "ISO 8601"),
        ("get_vehicle_count", {"start_time": "2026-10-01T00:00:00Z", "end_time": "2026-09-30T00:00:00Z"}, "after start_time"),
        ("get_vehicle_count", {"start_time": "2026-01-01T00:00:00Z", "end_time": "2026-06-01T00:00:00Z"}, "exceed"),
        ("get_vehicle_count", {**DAY, "junction_id": "bad id!"}, "junction_id"),
        ("get_hourly_traffic", {"date": "30/09/2026"}, "YYYY-MM-DD"),
        ("compare_junctions", {"junction_ids": ["JN-001"], **DAY}, "at least two"),
        ("compare_junctions", {"junction_ids": ["JN-001", "jn-001"], **DAY}, "at least two"),
        ("compare_junctions", {"junction_ids": [f"JN-{i:03d}" for i in range(11)], **DAY}, "at most"),
    ],
)
async def test_invalid_input_is_tool_error(name, args, match):
    async with Client(mcp) as c:
        with pytest.raises(ToolError, match=match):
            await c.call_tool(name, args)


async def test_timezone_offsets_are_normalised():
    a = await call("get_vehicle_count", {"start_time": "2026-09-30T05:30:00+05:30", "end_time": "2026-10-01T05:30:00+05:30"})
    b = await call("get_vehicle_count", {"start_time": "2026-09-30T00:00:00Z", "end_time": "2026-10-01T05:30:00"})  # no offset = IST
    assert a["total_vehicles"] == b["total_vehicles"]


async def test_traffic_patterns_are_realistic():
    weekday = (await call("get_hourly_traffic", {"date": "2026-09-30"}))["total_vehicles"]  # Wednesday
    sunday = (await call("get_hourly_traffic", {"date": "2026-09-27"}))["total_vehicles"]
    holiday = (await call("get_hourly_traffic", {"date": "2026-10-02"}))["total_vehicles"]  # Gandhi Jayanti
    assert sunday < weekday * 0.8 and holiday < weekday * 0.75
    hours = (await call("get_hourly_traffic", {"date": "2026-09-30"}))["hours"]
    assert hours[3]["vehicle_count"] < hours[18]["vehicle_count"] / 10  # quiet small hours

    def share(dist, vtype):
        return next(d["percentage"] for d in dist["distribution"] if d["vehicle_type"] == vtype)

    night = await call("get_vehicle_type_distribution",
                       {"start_time": "2026-09-30T23:00:00", "end_time": "2026-10-01T05:00:00", "junction_id": "JN-016"})
    day = await call("get_vehicle_type_distribution",
                     {"start_time": "2026-09-30T10:00:00", "end_time": "2026-09-30T17:00:00", "junction_id": "JN-016"})
    assert share(night, "truck") > 35 > 10 > share(day, "truck")  # night freight on the Red Hills corridor
    assert day["distribution"][0]["vehicle_type"] == "motorcycle"  # two-wheelers dominate by day
