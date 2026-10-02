"""Chennai road network used by the development datasets of every MCP server.

A stand-in for the ANPR platform's junction/camera registry, so investigation sightings
and analytics counts describe the same places. Coordinates are approximate real-world
locations; volumes are typical peak-hour vehicles per hour across all approaches.
All local times are Indian Standard Time.
"""

import math
from dataclasses import dataclass
from datetime import timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


@dataclass(frozen=True)
class Junction:
    id: str
    name: str
    area: str
    lat: float
    lon: float
    peak_volume: int  # vehicles per hour at the busiest hour, all approaches
    cameras: int  # ANPR cameras (one per approach)
    truck_route: bool = False  # on a heavy-vehicle corridor (night freight)


JUNCTIONS: tuple[Junction, ...] = (
    Junction("JN-001", "Kathipara Junction", "Guindy", 13.0067, 80.2006, 2600, 4),
    Junction("JN-002", "Gemini Flyover", "Anna Salai", 13.0569, 80.2425, 2200, 4),
    Junction("JN-003", "Koyambedu Junction", "Koyambedu", 13.0694, 80.1948, 2400, 4, truck_route=True),
    Junction("JN-004", "Vadapalani Junction", "Vadapalani", 13.0500, 80.2121, 1900, 4),
    Junction("JN-005", "Ashok Pillar", "Ashok Nagar", 13.0359, 80.2121, 1700, 4),
    Junction("JN-006", "Porur Junction", "Porur", 13.0358, 80.1569, 2000, 4, truck_route=True),
    Junction("JN-007", "Madhya Kailash", "Adyar", 13.0060, 80.2467, 2100, 3),
    Junction("JN-008", "Teynampet Signal", "Teynampet", 13.0418, 80.2504, 1800, 4),
    Junction("JN-009", "Saidapet Junction", "Saidapet", 13.0213, 80.2231, 1600, 3),
    Junction("JN-010", "Thiruvanmiyur Signal", "ECR", 12.9830, 80.2594, 1500, 3),
    Junction("JN-011", "Vijayanagar Junction", "Velachery", 12.9791, 80.2180, 1700, 4),
    Junction("JN-012", "Perungudi Toll Plaza", "OMR", 12.9654, 80.2461, 1900, 2),
    Junction("JN-013", "Anna Nagar Roundtana", "Anna Nagar", 13.0850, 80.2101, 1500, 4),
    Junction("JN-014", "Tidel Park Junction", "OMR", 12.9894, 80.2486, 2300, 4),
    Junction("JN-015", "Tambaram Junction", "GST Road", 12.9249, 80.1000, 2000, 3, truck_route=True),
    Junction("JN-016", "Madhavaram Roundana", "Red Hills Road", 13.1488, 80.2306, 1300, 3, truck_route=True),
)
BY_ID: dict[str, Junction] = {j.id: j for j in JUNCTIONS}

_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def distance_km(a: Junction, b: Junction) -> float:
    """Great-circle distance."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a: Junction, b: Junction) -> str:
    """8-point compass heading when travelling from a to b."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dl = math.radians(b.lon - a.lon)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(x, y)) + 360) % 360
    return _COMPASS[int((deg + 22.5) // 45) % 8]


def neighbours(j: Junction, max_km: float = 7.5) -> list[Junction]:
    """Nearby junctions, nearest first. Outlying ones (Tambaram, Madhavaram) still get their two nearest."""
    others = sorted((o for o in JUNCTIONS if o.id != j.id), key=lambda o: distance_km(j, o))
    near = [o for o in others if distance_km(j, o) <= max_km]
    return near if len(near) >= 2 else others[:2]


def travel_minutes(a: Junction, b: Junction, speed_kmph: float) -> float:
    """Road distance is ~1.35x the straight line in Chennai's grid."""
    return distance_km(a, b) * 1.35 / speed_kmph * 60
