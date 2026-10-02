import logging
import os
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from servers.analytics import tools
from servers.analytics.models import (
    CompareJunctionsResult,
    HourlyTrafficResult,
    JunctionStatisticsResult,
    VehicleCountResult,
    VehicleTypeDistributionResult,
)

logger = logging.getLogger("analytics")

T = TypeVar("T")

mcp = FastMCP(
    "analytics",
    instructions=(
        "Traffic analytics over MOCK ANPR aggregates (no real ANPR system is connected). "
        "Timestamps are ISO 8601 (IST, +05:30, if no offset); time ranges are [start_time, end_time)."
    ),
)

StartTime = Annotated[str, Field(description="Range start, ISO 8601, e.g. 2026-09-30T00:00:00+05:30 (IST if no offset)")]
EndTime = Annotated[str, Field(description="Range end (exclusive), ISO 8601, after start_time; max 31 days")]
OptionalJunction = Annotated[
    str | None, Field(description="Junction ID such as JN-001. Omit to include all junctions.")
]


def _guarded(fn: Callable[..., T], what: str, **kwargs: Any) -> T:
    """Run a tool function, mapping failures to clean MCP tool errors."""
    try:
        return fn(**kwargs)
    except tools.InvalidInputError as exc:
        raise ToolError(f"Invalid input: {exc}") from exc
    except Exception:
        logger.exception("%s failed", what)
        raise ToolError(f"Internal error in {what}") from None


@mcp.tool()
def get_vehicle_count(
    start_time: StartTime, end_time: EndTime, junction_id: OptionalJunction = None
) -> VehicleCountResult:
    """Total number of vehicles detected in a time range, optionally for one junction (mock data)."""
    return _guarded(
        tools.get_vehicle_count, "get_vehicle_count",
        start_time=start_time, end_time=end_time, junction_id=junction_id,
    )


@mcp.tool()
def get_junction_statistics(
    junction_id: Annotated[str, Field(description="Junction ID such as JN-001")],
    start_time: StartTime,
    end_time: EndTime,
) -> JunctionStatisticsResult:
    """Detections, average per hour, busiest hour and per-vehicle-type counts for one junction (mock data)."""
    return _guarded(
        tools.get_junction_statistics, "get_junction_statistics",
        junction_id=junction_id, start_time=start_time, end_time=end_time,
    )


@mcp.tool()
def get_vehicle_type_distribution(
    start_time: StartTime, end_time: EndTime, junction_id: OptionalJunction = None
) -> VehicleTypeDistributionResult:
    """Vehicle counts and percentages grouped by vehicle type, optionally for one junction (mock data)."""
    return _guarded(
        tools.get_vehicle_type_distribution, "get_vehicle_type_distribution",
        start_time=start_time, end_time=end_time, junction_id=junction_id,
    )


@mcp.tool()
def get_hourly_traffic(
    date: Annotated[str, Field(description="Day to report, YYYY-MM-DD (IST)")],
    junction_id: OptionalJunction = None,
) -> HourlyTrafficResult:
    """Vehicle counts for each of the 24 hours of a day, optionally for one junction (mock data)."""
    return _guarded(tools.get_hourly_traffic, "get_hourly_traffic", date=date, junction_id=junction_id)


@mcp.tool()
def compare_junctions(
    junction_ids: Annotated[list[str], Field(description="2 to 10 junction IDs, e.g. [\"JN-001\", \"JN-014\"]")],
    start_time: StartTime,
    end_time: EndTime,
) -> CompareJunctionsResult:
    """Compare totals, hourly average, busiest hour, vehicle mix and traffic share across junctions (mock data)."""
    return _guarded(
        tools.compare_junctions, "compare_junctions",
        junction_ids=junction_ids, start_time=start_time, end_time=end_time,
    )


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("ANALYTICS_HOST", "127.0.0.1")
    port = int(os.getenv("ANALYTICS_PORT", "8102"))
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
