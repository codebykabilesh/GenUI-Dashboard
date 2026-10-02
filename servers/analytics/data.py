"""Development traffic-count dataset for the Analytics server.

Hourly vehicle counts per junction and vehicle type, shaped like the aggregate tables of
the Chennai City ANPR platform, for COVERAGE_START..COVERAGE_END (IST). Generated
deterministically from the shared road network (servers/common/chennai.py):

- Chennai's two-peak day: morning 08:00-11:00 and a stronger evening 17:00-21:00.
- Mix dominated by two-wheelers, then cars and autos; buses peak with commuters.
- Heavy trucks are restricted by day, so their share rises sharply 22:00-06:00, most of
  all on freight corridors (Koyambedu, Porur, Tambaram, Madhavaram).
- Saturdays run ~12% lighter, Sundays ~30% lighter, public holidays ~35% lighter.
- Day-to-day and hour-to-hour variation of a few percent, as in real counts.

Not connected to any real ANPR system.
"""

import zlib
from datetime import datetime, timedelta

from servers.common.chennai import IST, JUNCTIONS as NETWORK

COVERAGE_START = datetime(2026, 9, 19, tzinfo=IST)
COVERAGE_END = datetime(2026, 10, 3, tzinfo=IST)  # exclusive
HOLIDAYS = {datetime(2026, 10, 2).date()}  # Gandhi Jayanti

# junction_id -> (name, peak vehicles per hour)
JUNCTIONS: dict[str, tuple[str, float]] = {j.id: (j.name, j.peak_volume) for j in NETWORK}
_TRUCK_ROUTES = {j.id for j in NETWORK if j.truck_route}

# Share of the junction's peak volume, by local hour.
HOURLY_PROFILE: list[float] = [
    0.13, 0.08, 0.06, 0.05, 0.08, 0.18, 0.38, 0.62, 0.86, 0.97, 0.88, 0.74,
    0.68, 0.66, 0.64, 0.69, 0.80, 0.93, 1.00, 0.96, 0.80, 0.58, 0.38, 0.22,
]

DAY_MIX = {"motorcycle": 0.47, "car": 0.29, "auto_rickshaw": 0.12, "bus": 0.05, "truck": 0.07}
NIGHT_MIX = {"motorcycle": 0.30, "car": 0.34, "auto_rickshaw": 0.08, "bus": 0.02, "truck": 0.26}
NIGHT_MIX_CORRIDOR = {"motorcycle": 0.20, "car": 0.27, "auto_rickshaw": 0.04, "bus": 0.02, "truck": 0.47}


def _noise(key: str, spread: float) -> float:
    """Deterministic multiplier in [1 - spread, 1 + spread]."""
    return 1 - spread + (zlib.crc32(key.encode()) % 1000) / 1000 * 2 * spread


def _day_factor(hour: datetime) -> float:
    d = hour.date()
    if d in HOLIDAYS:
        f = 0.65
    elif hour.weekday() == 6:
        f = 0.70
    elif hour.weekday() == 5:
        f = 0.88
    else:
        f = 1.0
    return f * _noise(f"day|{d}", 0.05)


def _mix(junction_id: str, hour: int) -> dict[str, float]:
    if 6 <= hour < 22:
        return DAY_MIX
    return NIGHT_MIX_CORRIDOR if junction_id in _TRUCK_ROUTES else NIGHT_MIX


def generate_hourly_counts() -> dict[tuple[str, datetime], dict[str, int]]:
    counts: dict[tuple[str, datetime], dict[str, int]] = {}
    hour = COVERAGE_START
    while hour < COVERAGE_END:
        day_factor = _day_factor(hour)
        for junction_id, (_, peak) in JUNCTIONS.items():
            total = peak * HOURLY_PROFILE[hour.hour] * day_factor * _noise(f"{junction_id}|{hour.isoformat()}", 0.07)
            counts[(junction_id, hour)] = {
                vtype: round(total * share * _noise(f"{junction_id}|{hour.isoformat()}|{vtype}", 0.10))
                for vtype, share in _mix(junction_id, hour.hour).items()
            }
        hour += timedelta(hours=1)
    return counts
