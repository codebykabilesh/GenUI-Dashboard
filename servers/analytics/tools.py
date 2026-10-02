"""Tool logic (service layer), independent of the MCP server wiring."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from servers.analytics.models import (
    MAX_COMPARE_JUNCTIONS,
    CompareJunctionsResult,
    HourCount,
    HourlyTrafficResult,
    JunctionComparison,
    JunctionStatistics,
    JunctionStatisticsResult,
    TypeCount,
    VehicleCountResult,
    VehicleTypeDistributionResult,
    normalize_junction,
    parse_range,
    parse_timestamp,
)
from servers.analytics.repository import MockTrafficRepository

logger = logging.getLogger(__name__)

_default_repo = MockTrafficRepository()


class InvalidInputError(ValueError):
    """Raised when a tool argument fails validation."""


def _checked_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    try:
        return parse_range(start_time, end_time)
    except ValueError as exc:
        logger.warning("rejected time range %r..%r: %s", start_time, end_time, exc)
        raise InvalidInputError(str(exc)) from exc


def _checked_junction(junction_id: str) -> str:
    try:
        return normalize_junction(junction_id)
    except ValueError as exc:
        logger.warning("rejected junction id %r: %s", junction_id, exc)
        raise InvalidInputError(str(exc)) from exc


def _unknown_junction_message(junction_id: str, repo: MockTrafficRepository) -> str:
    return f"Unknown junction {junction_id}. Known (mock) junctions: {', '.join(repo.junction_ids)}."


def _coverage_note(start: datetime, end: datetime, repo: MockTrafficRepository) -> str:
    if start >= repo.coverage_start and end <= repo.coverage_end:
        return ""
    return (
        f" Mock data only covers {repo.coverage_start:%Y-%m-%d} to "
        f"{(repo.coverage_end - timedelta(seconds=1)):%Y-%m-%d} (IST); hours outside it count as 0."
    )


def _junction_stats(
    junction_id: str, start: datetime, end: datetime, repo: MockTrafficRepository
) -> JunctionStatistics:
    buckets = repo.hourly(start, end, [junction_id])
    by_hour = [(hour, sum(by_type.values())) for _, hour, by_type in buckets]
    total = sum(count for _, count in by_hour)
    busiest = max(by_hour, key=lambda h: h[1], default=None)
    by_type: dict[str, int] = defaultdict(int)
    for _, _, counts in buckets:
        for vtype, n in counts.items():
            by_type[vtype] += n
    return JunctionStatistics(
        junction_id=junction_id,
        junction_name=repo.junction_name(junction_id),
        total_detections=total,
        average_per_hour=round(total / len(by_hour), 1) if by_hour else 0.0,
        busiest_hour_start=busiest[0] if busiest and busiest[1] > 0 else None,
        busiest_hour_count=busiest[1] if busiest else 0,
        by_vehicle_type=dict(sorted(by_type.items())),
    )


def get_vehicle_count(
    start_time: str,
    end_time: str,
    junction_id: str | None = None,
    repo: MockTrafficRepository = _default_repo,
) -> VehicleCountResult:
    start, end = _checked_range(start_time, end_time)
    jn = _checked_junction(junction_id) if junction_id else None
    if jn and not repo.has_junction(jn):
        return VehicleCountResult(
            found=False, message=_unknown_junction_message(jn, repo),
            start_time=start, end_time=end, junction_id=jn,
        )
    included = [jn] if jn else repo.junction_ids
    total = sum(repo.type_totals(start, end, included).values())
    logger.info("get_vehicle_count junction=%s total=%d", jn, total)
    scope = jn or "all junctions"
    return VehicleCountResult(
        message=f"{total} vehicle(s) at {scope} (mock data).{_coverage_note(start, end, repo)}",
        start_time=start, end_time=end, junction_id=jn,
        junctions_included=included, total_vehicles=total,
    )


def get_junction_statistics(
    junction_id: str,
    start_time: str,
    end_time: str,
    repo: MockTrafficRepository = _default_repo,
) -> JunctionStatisticsResult:
    start, end = _checked_range(start_time, end_time)
    jn = _checked_junction(junction_id)
    if not repo.has_junction(jn):
        return JunctionStatisticsResult(
            found=False, message=_unknown_junction_message(jn, repo), start_time=start, end_time=end
        )
    stats = _junction_stats(jn, start, end, repo)
    logger.info("get_junction_statistics junction=%s total=%d", jn, stats.total_detections)
    return JunctionStatisticsResult(
        message=f"Statistics for {jn} ({stats.junction_name}) (mock data).{_coverage_note(start, end, repo)}",
        start_time=start, end_time=end, statistics=stats,
    )


def get_vehicle_type_distribution(
    start_time: str,
    end_time: str,
    junction_id: str | None = None,
    repo: MockTrafficRepository = _default_repo,
) -> VehicleTypeDistributionResult:
    start, end = _checked_range(start_time, end_time)
    jn = _checked_junction(junction_id) if junction_id else None
    if jn and not repo.has_junction(jn):
        return VehicleTypeDistributionResult(
            found=False, message=_unknown_junction_message(jn, repo),
            start_time=start, end_time=end, junction_id=jn,
        )
    totals = repo.type_totals(start, end, [jn] if jn else repo.junction_ids)
    total = sum(totals.values())
    distribution = [
        TypeCount(vehicle_type=t, count=n, percentage=round(100 * n / total, 1) if total else 0.0)
        for t, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    logger.info("get_vehicle_type_distribution junction=%s total=%d", jn, total)
    return VehicleTypeDistributionResult(
        message=f"Vehicle types at {jn or 'all junctions'} (mock data).{_coverage_note(start, end, repo)}",
        start_time=start, end_time=end, junction_id=jn, total_vehicles=total, distribution=distribution,
    )


def get_hourly_traffic(
    date: str, junction_id: str | None = None, repo: MockTrafficRepository = _default_repo
) -> HourlyTrafficResult:
    try:
        day = parse_timestamp(date, "date").replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError as exc:
        logger.warning("rejected date %r", date)
        raise InvalidInputError("date must be YYYY-MM-DD, e.g. 2026-09-30") from exc
    jn = _checked_junction(junction_id) if junction_id else None
    day_str = f"{day:%Y-%m-%d}"
    if jn and not repo.has_junction(jn):
        return HourlyTrafficResult(
            found=False, message=_unknown_junction_message(jn, repo), date=day_str, junction_id=jn
        )
    per_hour: dict[datetime, int] = defaultdict(int)
    for _, hour, by_type in repo.hourly(day, day + timedelta(days=1), [jn] if jn else repo.junction_ids):
        per_hour[hour] += sum(by_type.values())
    hours = [
        HourCount(hour=h, hour_start=day + timedelta(hours=h), vehicle_count=per_hour.get(day + timedelta(hours=h), 0))
        for h in range(24)
    ]
    total = sum(h.vehicle_count for h in hours)
    in_coverage = repo.coverage_start <= day < repo.coverage_end
    peak = max(hours, key=lambda h: h.vehicle_count).hour if total else None
    logger.info("get_hourly_traffic date=%s junction=%s total=%d", day_str, jn, total)
    note = "" if in_coverage else (
        f" No mock data for {day_str}; coverage is {repo.coverage_start:%Y-%m-%d} to "
        f"{(repo.coverage_end - timedelta(seconds=1)):%Y-%m-%d}."
    )
    return HourlyTrafficResult(
        message=f"Hourly traffic for {day_str} at {jn or 'all junctions'} (IST, mock data).{note}",
        date=day_str, junction_id=jn, total_vehicles=total, peak_hour=peak, hours=hours,
    )


def compare_junctions(
    junction_ids: list[str],
    start_time: str,
    end_time: str,
    repo: MockTrafficRepository = _default_repo,
) -> CompareJunctionsResult:
    start, end = _checked_range(start_time, end_time)
    ids = list(dict.fromkeys(_checked_junction(j) for j in junction_ids))  # dedupe, keep order
    if len(ids) < 2:
        raise InvalidInputError("provide at least two distinct junction ids to compare")
    if len(ids) > MAX_COMPARE_JUNCTIONS:
        raise InvalidInputError(f"at most {MAX_COMPARE_JUNCTIONS} junctions can be compared")
    known = [j for j in ids if repo.has_junction(j)]
    unknown = [j for j in ids if not repo.has_junction(j)]
    if not known:
        return CompareJunctionsResult(
            found=False, message=_unknown_junction_message(", ".join(unknown), repo),
            start_time=start, end_time=end, unknown_junctions=unknown,
        )
    stats = [_junction_stats(j, start, end, repo) for j in known]
    grand_total = sum(s.total_detections for s in stats)
    junctions = sorted(
        (
            JunctionComparison(
                **s.model_dump(),
                share_of_total_pct=round(100 * s.total_detections / grand_total, 1) if grand_total else 0.0,
            )
            for s in stats
        ),
        key=lambda c: -c.total_detections,
    )
    logger.info("compare_junctions junctions=%s unknown=%s", known, unknown)
    extra = f" Unknown junctions ignored: {', '.join(unknown)}." if unknown else ""
    return CompareJunctionsResult(
        message=f"Compared {len(junctions)} junction(s), busiest first (mock data).{extra}{_coverage_note(start, end, repo)}",
        start_time=start, end_time=end, junctions=junctions,
        busiest_junction=junctions[0].junction_id if grand_total else None,
        unknown_junctions=unknown,
    )
