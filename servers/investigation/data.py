"""Development ANPR dataset for the Investigation server.

Shaped like the output of the Chennai City ANPR platform: a vehicle registry (RTO
records) and camera sightings at monitored junctions. Generated deterministically from
the shared road network, so every run produces the same data:

- Commuters drive home -> work on weekday mornings (07:45-10:00) and back in the
  evening (17:30-20:30), with occasional weekend trips.
- Autos make short hops around their area all day; buses run fixed routes.
- Heavy trucks move at night (22:00-05:30, the city's daytime heavy-vehicle ban) on
  freight corridors; light goods vehicles run by day.
- Sightings follow road geometry: travel times from distance and time-of-day speed,
  heading from the bearing between junctions, ~8% of passes missed by the cameras.
- A few plates are unregistered misreads with low confidence, as in a real feed.

Not connected to any real ANPR system or database.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from servers.common.chennai import BY_ID, IST, JUNCTIONS, Junction, bearing, distance_km, neighbours, travel_minutes
from servers.investigation.models import ANPRRecord, VehicleDetails

COVERAGE_START = datetime(2026, 9, 19, tzinfo=IST)
COVERAGE_END = datetime(2026, 10, 3, tzinfo=IST)  # exclusive
HOLIDAYS = {datetime(2026, 10, 2, tzinfo=IST).date()}  # Gandhi Jayanti

_SEED = 20260919
_MISS_RATE = 0.08

# --- reference records (stable IDs used in docs, demos and tests) -------------------
REFERENCE_VEHICLES: list[VehicleDetails] = [
    VehicleDetails(plate_number="KA01AB1234", vehicle_type="car", make="Maruti Suzuki", model="Swift",
                   colour="white", registered_state="Karnataka", registering_office="Bengaluru Central (KA01)",
                   fuel_type="Petrol", registration_year=2021),
    VehicleDetails(plate_number="KA05MN4321", vehicle_type="motorcycle", make="Honda", model="Activa 6G",
                   colour="black", registered_state="Karnataka", registering_office="Bengaluru South (KA05)",
                   fuel_type="Petrol", registration_year=2022),
    VehicleDetails(plate_number="MH12XY9876", vehicle_type="truck", make="Tata", model="Signa 2823",
                   colour="blue", registered_state="Maharashtra", registering_office="Pune (MH12)",
                   fuel_type="Diesel", registration_year=2019),
]

REFERENCE_RECORDS: list[ANPRRecord] = [
    ANPRRecord(detection_id="DET-0001", plate_number="KA01AB1234", vehicle_type="car", confidence=0.97,
               junction_id="JN-001", timestamp="2026-09-30T08:15:22+05:30", direction="N",
               camera_id="CAM-001-01", lane=2, speed_kmph=31),
    ANPRRecord(detection_id="DET-0002", plate_number="KA01AB1234", vehicle_type="car", confidence=0.91,
               junction_id="JN-014", timestamp="2026-09-30T08:42:05+05:30", direction="E",
               camera_id="CAM-014-02", lane=1, speed_kmph=27),
    ANPRRecord(detection_id="DET-0003", plate_number="KA05MN4321", vehicle_type="motorcycle", confidence=0.88,
               junction_id="JN-003", timestamp="2026-09-30T09:03:47+05:30", direction="S",
               camera_id="CAM-003-03", lane=1, speed_kmph=36),
    ANPRRecord(detection_id="DET-0004", plate_number="MH12XY9876", vehicle_type="truck", confidence=0.94,
               junction_id="JN-007", timestamp="2026-10-01T22:10:11+05:30", direction="W",
               camera_id="CAM-007-04", lane=3, speed_kmph=42),
]

# --- registry building blocks ---------------------------------------------------------
CHENNAI_RTO = {
    "TN01": "Chennai Central", "TN02": "Chennai North West", "TN04": "Chennai East", "TN05": "Chennai North",
    "TN06": "Chennai South East", "TN07": "Chennai South", "TN09": "Chennai West", "TN10": "Valasaravakkam",
    "TN11": "Tambaram", "TN12": "Poonamallee", "TN13": "Ambattur", "TN14": "Sholinganallur",
    "TN18": "Red Hills", "TN22": "Meenambakkam",
}
OUTSTATION = [  # (state code, state, RTO codes and office names)
    ("KA", "Karnataka", {"01": "Bengaluru Central", "03": "Bengaluru East", "51": "Electronic City"}),
    ("AP", "Andhra Pradesh", {"39": "Tirupati", "16": "Vijayawada"}),
    ("KL", "Kerala", {"07": "Ernakulam", "01": "Thiruvananthapuram"}),
    ("PY", "Puducherry", {"01": "Puducherry"}),
    ("TS", "Telangana", {"09": "Hyderabad Central"}),
]
MODELS: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {
    "car": [
        ("Maruti Suzuki", "Swift", ("Petrol", "CNG")), ("Maruti Suzuki", "Dzire", ("Petrol", "CNG")),
        ("Maruti Suzuki", "Baleno", ("Petrol",)), ("Maruti Suzuki", "Ertiga", ("Petrol", "CNG")),
        ("Hyundai", "i20", ("Petrol",)), ("Hyundai", "Creta", ("Petrol", "Diesel")), ("Hyundai", "Venue", ("Petrol",)),
        ("Tata", "Nexon", ("Petrol", "Diesel", "Electric")), ("Tata", "Punch", ("Petrol", "CNG")),
        ("Mahindra", "XUV700", ("Diesel", "Petrol")), ("Mahindra", "Scorpio-N", ("Diesel",)),
        ("Toyota", "Innova Crysta", ("Diesel",)), ("Honda", "City", ("Petrol",)), ("Kia", "Seltos", ("Petrol", "Diesel")),
        ("MG", "ZS EV", ("Electric",)),
    ],
    "motorcycle": [
        ("Honda", "Activa 6G", ("Petrol",)), ("TVS", "Jupiter", ("Petrol",)), ("TVS", "Apache RTR 160", ("Petrol",)),
        ("Bajaj", "Pulsar 150", ("Petrol",)), ("Royal Enfield", "Classic 350", ("Petrol",)),
        ("Hero", "Splendor Plus", ("Petrol",)), ("Ather", "450X", ("Electric",)), ("Ola", "S1 Pro", ("Electric",)),
        ("Yamaha", "FZ-S", ("Petrol",)),
    ],
    "auto_rickshaw": [("Bajaj", "RE Compact", ("CNG", "LPG")), ("Piaggio", "Ape City", ("CNG", "Diesel")),
                      ("TVS", "King Deluxe", ("LPG",))],
    "truck": [
        ("Ashok Leyland", "Ecomet 1615", ("Diesel",)), ("Tata", "Signa 2823", ("Diesel",)),
        ("Eicher", "Pro 2049", ("Diesel",)), ("BharatBenz", "1617R", ("Diesel",)),
        ("Ashok Leyland", "Dost+", ("Diesel",)), ("Tata", "Ace Gold", ("Diesel", "CNG")),
    ],
    "bus": [("Ashok Leyland", "Viking", ("Diesel",)), ("Ashok Leyland", "Switch EiV 12", ("Electric",)),
            ("Tata", "Starbus", ("Diesel",))],
}
LIGHT_GOODS = {"Dost+", "Ace Gold"}  # allowed in the city by day
COLOURS = {
    "car": ["white", "white", "silver", "grey", "red", "blue", "black", "brown"],
    "motorcycle": ["black", "black", "red", "blue", "grey", "white"],
    "auto_rickshaw": ["yellow", "green"],
    "truck": ["white", "blue", "orange", "yellow"],
    "bus": ["blue", "green"],
}
FLEET = {"car": 34, "motorcycle": 26, "auto_rickshaw": 8, "truck": 9, "bus": 5}
SERIES = "ABCDEFGHJKLMNPRSTUVWXYZ"  # I/O/Q are not issued


@dataclass
class _Vehicle:
    details: VehicleDetails
    home: Junction
    work: Junction


def _plate(rng: random.Random, used: set[str], vtype: str) -> tuple[str, str, str]:
    """Returns (plate, state, registering office)."""
    while True:
        if vtype in ("car", "motorcycle") and rng.random() < 0.12:
            code, state, offices = rng.choice(OUTSTATION)
            rto, office = rng.choice(list(offices.items()))
            prefix, label = f"{code}{rto}", f"{office} ({code}{rto})"
        else:
            if vtype == "bus":
                prefix = "TN01"  # MTC fleet
            elif vtype == "truck":
                prefix = rng.choice(["TN18", "TN12", "TN05", "TN22"])
            else:
                prefix = rng.choice(list(CHENNAI_RTO))
            state, label = "Tamil Nadu", f"{CHENNAI_RTO[prefix]} ({prefix})"
        series = rng.choice(SERIES) + rng.choice(SERIES) if rng.random() < 0.85 else rng.choice(SERIES)
        plate = f"{prefix}{series}{rng.randint(1, 9999):04d}"
        if plate not in used:
            used.add(plate)
            return plate, state, label


def _registry(rng: random.Random) -> list[_Vehicle]:
    used = {v.plate_number for v in REFERENCE_VEHICLES}
    fleet: list[_Vehicle] = []
    for vtype, count in FLEET.items():
        for _ in range(count):
            make, model, fuels = rng.choice(MODELS[vtype])
            plate, state, office = _plate(rng, used, vtype)
            home = rng.choice(JUNCTIONS)
            far = [j for j in JUNCTIONS if 4 <= distance_km(home, j) <= 14] or list(neighbours(home))
            fleet.append(_Vehicle(
                VehicleDetails(
                    plate_number=plate, vehicle_type=vtype, make=make, model=model,
                    colour=rng.choice(COLOURS[vtype]), registered_state=state, registering_office=office,
                    fuel_type=rng.choice(fuels), registration_year=rng.randint(2012, 2026),
                ),
                home=home,
                work=rng.choice(far),
            ))
    return fleet


def _route(rng: random.Random, start: Junction, end: Junction, max_hops: int = 6) -> list[Junction]:
    """Greedy, slightly random walk towards `end` over neighbouring junctions."""
    path, current = [start], start
    while current.id != end.id and len(path) <= max_hops:
        options = [n for n in neighbours(current) if n not in path]
        if not options:
            break
        options.sort(key=lambda n: distance_km(n, end))
        current = options[0] if rng.random() < 0.75 or len(options) == 1 else options[1]
        path.append(current)
    return path


def _speed(rng: random.Random, vtype: str, when: datetime) -> int:
    peak = when.hour in (8, 9, 10, 17, 18, 19, 20)
    base = {"car": 34, "motorcycle": 36, "auto_rickshaw": 26, "truck": 40, "bus": 28}[vtype]
    if peak:
        base *= 0.62
    elif when.hour >= 22 or when.hour < 6:
        base *= 1.35
    return max(6, int(rng.gauss(base, base * 0.18)))


def _confidence(rng: random.Random, vtype: str, when: datetime) -> float:
    mean = {"car": 0.94, "motorcycle": 0.87, "auto_rickshaw": 0.9, "truck": 0.92, "bus": 0.93}[vtype]
    if when.hour >= 19 or when.hour < 6:  # headlight glare and low light
        mean -= 0.04
    return round(min(0.99, max(0.6, rng.gauss(mean, 0.035))), 2)


def _sightings(rng: random.Random, v: VehicleDetails, path: list[Junction], depart: datetime) -> list[dict]:
    out, t = [], depart
    for i, j in enumerate(path):
        if i > 0:
            t += timedelta(minutes=travel_minutes(path[i - 1], j, max(_speed(rng, v.vehicle_type, t), 8)))
            t += timedelta(seconds=rng.randint(20, 150))  # signal wait
        if rng.random() < _MISS_RATE or t >= COVERAGE_END:
            continue
        heading = bearing(j, path[i + 1]) if i + 1 < len(path) else bearing(path[i - 1], j) if i else "N"
        approach = "N NE E SE S SW W NW".split().index(heading) % j.cameras + 1
        out.append({
            "plate_number": v.plate_number,
            "vehicle_type": v.vehicle_type,
            "confidence": _confidence(rng, v.vehicle_type, t),
            "junction_id": j.id,
            "timestamp": t.replace(microsecond=0),
            "direction": heading,
            "camera_id": f"CAM-{j.id[3:]}-{approach:02d}",
            "lane": rng.choice([1, 1, 2] if v.vehicle_type in ("motorcycle", "auto_rickshaw", "bus") else [1, 2, 2, 3]),
            "speed_kmph": _speed(rng, v.vehicle_type, t),
        })
    return out


def _at(day: datetime, rng: random.Random, start_h: float, end_h: float) -> datetime:
    return day + timedelta(minutes=rng.uniform(start_h * 60, end_h * 60))


def _trips(rng: random.Random, fleet: list[_Vehicle]) -> list[dict]:
    rows: list[dict] = []
    day = COVERAGE_START
    while day < COVERAGE_END:
        weekday = day.weekday() < 5 and day.date() not in HOLIDAYS
        for veh in fleet:
            v, kind = veh.details, veh.details.vehicle_type
            if kind in ("car", "motorcycle"):
                if weekday and rng.random() < 0.72:
                    rows += _sightings(rng, v, _route(rng, veh.home, veh.work), _at(day, rng, 7.75, 10))
                    rows += _sightings(rng, v, _route(rng, veh.work, veh.home), _at(day, rng, 17.5, 20.5))
                elif not weekday and rng.random() < 0.35:
                    dest = rng.choice(neighbours(veh.home))
                    out = _at(day, rng, 10.5, 19)
                    rows += _sightings(rng, v, _route(rng, veh.home, dest), out)
                    rows += _sightings(rng, v, _route(rng, dest, veh.home), out + timedelta(hours=rng.uniform(1.5, 4)))
            elif kind == "auto_rickshaw":
                if day.weekday() != 6 or rng.random() < 0.5:
                    here = veh.home
                    for _ in range(rng.randint(2, 5)):
                        dest = rng.choice(neighbours(here)[:5])
                        rows += _sightings(rng, v, [here, dest], _at(day, rng, 7, 22.5))
                        here = dest
            elif kind == "truck":
                if v.model in LIGHT_GOODS:
                    if weekday and rng.random() < 0.8:
                        rows += _sightings(rng, v, _route(rng, veh.home, veh.work), _at(day, rng, 10.5, 16))
                elif rng.random() < 0.45:
                    corridor = [j for j in JUNCTIONS if j.truck_route]
                    a, b = rng.sample(corridor, 2)
                    rows += _sightings(rng, v, _route(rng, a, b), _at(day, rng, 22, 23.9))
            elif kind == "bus":
                route = _route(rng, veh.home, veh.work, max_hops=5)
                for run in range(2):
                    leg = route if run % 2 == 0 else list(reversed(route))
                    rows += _sightings(rng, v, leg, _at(day, rng, 6 + run * 8, 9 + run * 8))
        day += timedelta(days=1)
    return rows


def _misreads(rng: random.Random, used: set[str]) -> list[dict]:
    """Plates read wrongly by the cameras: no registry record, low confidence."""
    rows = []
    for _ in range(7):
        plate, _, _ = _plate(rng, used, "car")
        j = rng.choice(JUNCTIONS)
        t = COVERAGE_START + timedelta(minutes=rng.uniform(0, (COVERAGE_END - COVERAGE_START).total_seconds() / 60))
        rows.append({
            "plate_number": plate, "vehicle_type": rng.choice(["car", "motorcycle"]),
            "confidence": round(rng.uniform(0.55, 0.72), 2), "junction_id": j.id,
            "timestamp": t.replace(microsecond=0), "direction": rng.choice(["N", "E", "S", "W"]),
            "camera_id": f"CAM-{j.id[3:]}-{rng.randint(1, j.cameras):02d}", "lane": rng.randint(1, 3),
            "speed_kmph": rng.randint(15, 45),
        })
    return rows


def build_dataset() -> tuple[list[ANPRRecord], list[VehicleDetails]]:
    rng = random.Random(_SEED)
    fleet = _registry(rng)
    rows = _trips(rng, fleet)
    rows += _misreads(rng, {v.details.plate_number for v in fleet} | {v.plate_number for v in REFERENCE_VEHICLES})
    rows.sort(key=lambda r: r["timestamp"])
    first_id = len(REFERENCE_RECORDS) + 1
    records = [ANPRRecord(detection_id=f"DET-{first_id + i:04d}", **row) for i, row in enumerate(rows)]
    return REFERENCE_RECORDS + records, REFERENCE_VEHICLES + [v.details for v in fleet]


MOCK_RECORDS, MOCK_VEHICLES = build_dataset()
assert all(r.junction_id in BY_ID for r in MOCK_RECORDS)
