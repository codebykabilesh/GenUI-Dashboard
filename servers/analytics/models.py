from datetime import datetime

from servers.common.chennai import IST

from pydantic import BaseModel, Field

MAX_RANGE_DAYS = 31
MAX_COMPARE_JUNCTIONS = 10


def parse_timestamp(value: str, field: str) -> datetime:
    """ISO 8601 -> aware datetime in IST. Values without an offset are local time (IST)."""
    try:
        dt = datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be an ISO 8601 timestamp, e.g. 2026-09-30T08:00:00+05:30") from exc
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def parse_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    start = parse_timestamp(start_time, "start_time")
    end = parse_timestamp(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be after start_time")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"time range must not exceed {MAX_RANGE_DAYS} days")
    return start, end


def normalize_junction(value: str) -> str:
    jn = value.strip().upper()
    if not jn or len(jn) > 20 or not all(c.isalnum() or c in "-_" for c in jn):
        raise ValueError("junction_id must be letters, digits, '-' or '_' (e.g. JN-001)")
    return jn


class _MockResult(BaseModel):
    """Envelope shared by every tool result."""

    found: bool = True
    message: str
    mock_data: bool = True


class _Window(_MockResult):
    start_time: datetime
    end_time: datetime


class VehicleCountResult(_Window):
    junction_id: str | None = None
    junctions_included: list[str] = Field(default_factory=list)
    total_vehicles: int = 0


class JunctionStatistics(BaseModel):
    junction_id: str
    junction_name: str
    total_detections: int
    average_per_hour: float
    busiest_hour_start: datetime | None = None
    busiest_hour_count: int = 0
    by_vehicle_type: dict[str, int] = Field(default_factory=dict)


class JunctionStatisticsResult(_Window):
    statistics: JunctionStatistics | None = None


class TypeCount(BaseModel):
    vehicle_type: str
    count: int
    percentage: float


class VehicleTypeDistributionResult(_Window):
    junction_id: str | None = None
    total_vehicles: int = 0
    distribution: list[TypeCount] = Field(default_factory=list)


class HourCount(BaseModel):
    hour: int = Field(ge=0, le=23)
    hour_start: datetime
    vehicle_count: int


class HourlyTrafficResult(_MockResult):
    date: str
    junction_id: str | None = None
    total_vehicles: int = 0
    peak_hour: int | None = None
    hours: list[HourCount] = Field(default_factory=list)


class JunctionComparison(JunctionStatistics):
    share_of_total_pct: float


class CompareJunctionsResult(_Window):
    junctions: list[JunctionComparison] = Field(default_factory=list)
    busiest_junction: str | None = None
    unknown_junctions: list[str] = Field(default_factory=list)
