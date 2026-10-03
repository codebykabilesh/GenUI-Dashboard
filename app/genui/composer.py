"""Turns MCP tool results into A2UI surfaces.

For every tool result this builds the surface's data model (and the facts and
prebuilt blocks an LLM-designed layout binds to, see designer.py) plus a default
template layout, used when no LLM layout is requested or the LLM's layout is rejected.
Surfaces only display data returned by the tools.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.genui.a2ui import A2UIMessage, Surface, lit, path

logger = logging.getLogger(__name__)

ALL = "all"


def _dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _when(value: Any) -> str:
    dt = _dt(value)
    return f"{dt:%d %b %Y, %H:%M}" if dt else str(value)


def _window(start: Any, end: Any) -> str:
    a, b = _dt(start), _dt(end)
    if not a or not b:
        return ""
    return f"{a:%d %b %Y %H:%M} to {b:%d %b %Y %H:%M} IST"


def _input_dt(value: Any) -> str:
    dt = _dt(value)
    return f"{dt:%Y-%m-%dT%H:%M}" if dt else ""


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _label(value: Any) -> str:
    return str(value or "").replace("_", " ")


class UIComposer:
    def __init__(self, junction_lookup: Callable[[], Any] | None = None) -> None:
        # async callable returning known junction ids (discovered from the analytics server)
        self._junction_lookup = junction_lookup
        self._builders: dict[str, Callable[..., str]] = {
            "search_vehicle": self._sightings,
            "get_vehicle_history": self._sightings,
            "get_vehicle_details": self._vehicle,
            "get_detection_by_id": self._detection,
            "get_detection_evidence": self._evidence,
            "get_vehicle_count": self._vehicle_count,
            "get_junction_statistics": self._junction_stats,
            "get_vehicle_type_distribution": self._type_distribution,
            "get_hourly_traffic": self._hourly,
            "compare_junctions": self._compare,
        }

    def supports(self, tool: str) -> bool:
        return tool in self._builders

    async def compose(
        self, tool: str, args: dict[str, Any], result: Any, surface_id: str | None = None
    ) -> list[A2UIMessage] | None:
        built = await self.build(tool, args, result, surface_id)
        return built[0].messages(built[1]) if built else None

    async def build(
        self, tool: str, args: dict[str, Any], result: Any, surface_id: str | None = None
    ) -> tuple[Surface, str] | None:
        """The default (template) surface and its root id; also the data an LLM layout binds to."""
        builder = self._builders.get(tool)
        if builder is None or not isinstance(result, dict):
            return None
        junctions = await self._junctions() if tool in _ANALYTICS else []
        surface = Surface(tool.replace("_", "-"), surface_id)
        try:
            root = builder(surface, args, result, junctions)
        except Exception:
            logger.exception("Failed to compose UI for %s", tool)
            return None
        return surface, root

    async def _junctions(self) -> list[str]:
        if self._junction_lookup is None:
            return []
        try:
            return list(await self._junction_lookup())
        except Exception:
            logger.warning("Junction lookup failed", exc_info=True)
            return []

    # shared pieces -----------------------------------------------------------
    @staticmethod
    def _header(s: Surface, title: str, subtitle: str = "", plate: str | None = None,
                badge: tuple[str, str] | None = None) -> str:
        s.facts.update(title=title, subtitle=subtitle)
        if plate:
            s.facts["plate"] = plate
        parts = []
        if plate:
            parts.append(s.plate(plate, action="vehicle_details"))
        heading = [s.text(title, "h4")]
        if subtitle:
            heading.append(s.text(subtitle, "caption"))
        parts.append(s.column(heading))
        row = [s.row(parts)]
        if badge:
            row.append(s.badge(*badge))
        return s.row(row, distribution="spaceBetween", id_="header")

    @staticmethod
    def _search_bar(s: Surface, query: str) -> str:
        s.data["query"] = query
        field = s.text_field("Registration number", "/query")
        go = s.button("Search", "search_vehicle", {"registration_number": path("/query")})
        s.blocks["search"] = s.row([field, go], alignment="end")
        return s.blocks["search"]

    @staticmethod
    def _junction_choice(s: Surface, junctions: list[str], selected: list[str], allow_all: bool = True,
                         max_selections: int = 1) -> str:
        s.data["junction"] = selected or ([ALL] if allow_all else [])
        options = ([("All junctions", ALL)] if allow_all else []) + [(j, j) for j in junctions]
        return s.choice("/junction", options, max_selections)

    @staticmethod
    def _range_inputs(s: Surface, result: dict[str, Any]) -> list[str]:
        s.data["start"] = _input_dt(result.get("start_time"))
        s.data["end"] = _input_dt(result.get("end_time"))
        return [s.date_input("/start", with_time=True), s.date_input("/end", with_time=True)]

    @staticmethod
    def _range_context() -> dict[str, dict[str, Any]]:
        return {"start_time": path("/start"), "end_time": path("/end"), "junction_id": path("/junction")}

    def _filters(self, s: Surface, inputs: list[str], action: str, context: dict) -> str:
        s.blocks["filters"] = s.add("Filters", {"children": {"explicitList": [*inputs, s.button("Apply", action, context)]}})
        return s.blocks["filters"]

    # investigation -----------------------------------------------------------
    def _not_found(self, s: Surface, title: str, detail: str, plate: str | None = None, search: bool = True) -> str:
        parts = [self._header(s, title, detail, badge=("No match", "warning"))]
        if search:
            parts.append(self._search_bar(s, plate or ""))
        return s.column(parts)

    def _sightings(self, s: Surface, args: dict, r: dict, _j: list[str]) -> str:
        plate = r.get("query", "")
        records = r.get("records") or []
        if not r.get("found") or not records:
            return self._not_found(s, "No sightings found",
                                   f"{plate} has not been detected by any camera in the searched records.", plate)
        first, last = records[0], records[-1]
        total = int(r.get("total") or len(records))
        junctions = {d.get("junction_id") for d in records}
        best = max(float(d.get("confidence", 0)) for d in records)
        s.data["sightings"] = [
            {
                "detection_id": d["detection_id"],
                "when": _when(d.get("timestamp")),
                "junction": d.get("junction_id", ""),
                "direction": d.get("direction", ""),
                "confidence": float(d.get("confidence", 0)),
                "vehicle_type": _label(d.get("vehicle_type")),
                "capture": ", ".join(p for p in (d.get("camera_id", ""),
                                                 f"{d['speed_kmph']} km/h" if "speed_kmph" in d else "") if p),
            }
            for d in records
        ]
        item = s.row(
            [
                s.column([s.text(path("when"), "body"), s.text(path("capture"), "caption")], id_="when"),
                s.badge(path("junction"), "neutral", id_="junction", mono=True),
                s.add("Direction", {"value": path("direction")}, "direction"),
                s.add("Confidence", {"value": path("confidence")}, "confidence"),
                s.button("Evidence", "open_evidence", {"detection_id": path("detection_id")}),
            ],
            distribution="spaceBetween",
            id_="sighting",
        )
        return s.column([
            self._header(s, _plural(total, "sighting") + (f", latest {len(records)} shown" if total > len(records) else ""),
                         (f"From {_when(first.get('timestamp'))} to {_when(last.get('timestamp'))} IST"
                          if len(records) > 1 else f"Seen {_when(first.get('timestamp'))} IST"),
                         plate, ("Investigation", "neutral")),
            s.row([
                s.stat("Sightings", f"{total:,}", "neutral"),
                s.stat("Junctions", f"{len(junctions)}", "neutral"),
                s.stat("Best match", f"{round(best * 100)}%", "neutral"),
            ], id_="stats"),
            s.add("Timeline", {"columns": ["Time", "Junction", "Direction", "Read", ""],
                                "children": {"template": {"dataBinding": "/sightings", "componentId": item}}}),
            s.row([
                s.button("Vehicle record", "vehicle_details", {"registration_number": lit(plate)}),
                self._search_bar(s, ""),
            ], distribution="spaceBetween", alignment="end"),
        ])

    def _vehicle(self, s: Surface, args: dict, r: dict, _j: list[str]) -> str:
        plate = r.get("query", "")
        v = r.get("vehicle")
        if not r.get("found") or not v:
            return self._not_found(s, "No vehicle record", f"No registration record exists for {plate}.", plate)
        make_model = f"{v.get('make', '')} {v.get('model', '')}".strip()
        s.data["facts"] = [
            {"label": "Vehicle type", "value": _label(v.get("vehicle_type")).capitalize()},
            {"label": "Registering office", "value": v.get("registering_office") or v.get("registered_state", "")},
            {"label": "Fuel", "value": v.get("fuel_type", "")},
            {"label": "Registered", "value": str(v.get("registration_year", ""))},
            {"label": "Colour", "value": str(v.get("colour", "")).capitalize()},
        ]
        fact = s.column([s.text(path("label"), "caption"), s.text(path("value"), "body")], id_="fact")
        return s.column([
            self._header(s, make_model or "Vehicle record", "Registration record", plate, ("Investigation", "neutral")),
            s.add("List", {"direction": "horizontal",
                           "children": {"template": {"dataBinding": "/facts", "componentId": fact}}}),
            s.row([s.button("Sighting history", "vehicle_history", {"registration_number": lit(plate)})]),
        ])

    def _detection(self, s: Surface, args: dict, r: dict, _j: list[str]) -> str:
        d = r.get("record")
        if not r.get("found") or not d:
            return self._not_found(s, "No sighting found",
                                   f"There is no sighting with ID {r.get('detection_id', '')}.", search=False)
        plate = d["plate_number"]
        s.data["d"] = {"junction": d.get("junction_id", ""), "direction": d.get("direction", ""),
                       "confidence": float(d.get("confidence", 0))}
        return s.column([
            self._header(s, f"Sighting {d['detection_id']}", f"{_when(d.get('timestamp'))} IST, {d.get('camera_id', '')}, "
                         f"{_label(d.get('vehicle_type'))}", plate, ("Investigation", "neutral")),
            s.row([
                s.badge(path("/d/junction"), "neutral", mono=True),
                s.add("Direction", {"value": path("/d/direction")}),
                s.add("Confidence", {"value": path("/d/confidence")}),
            ]),
            s.row([
                s.button("Evidence", "open_evidence", {"detection_id": lit(d["detection_id"])}),
                s.button("Sighting history", "vehicle_history", {"registration_number": lit(plate)}),
            ]),
        ])

    def _evidence(self, s: Surface, args: dict, r: dict, _j: list[str]) -> str:
        did = r.get("detection_id", "")
        items = r.get("evidence") or []
        if not r.get("found") or not items:
            return self._not_found(s, "No evidence", f"No evidence is attached to sighting {did}.", search=False)
        labels = {"vehicle_image": "Vehicle image", "plate_crop": "Plate crop", "video_clip": "Video clip"}
        s.data["evidence"] = [
            {"kind": e["kind"], "label": labels.get(e["kind"], _label(e["kind"])),
             "evidence_id": e.get("evidence_id", ""), "content_type": e.get("content_type", ""), "uri": e.get("uri", "")}
            for e in items
        ]
        frame = s.add("EvidenceFrame", {"kind": path("kind"), "label": path("label"), "uri": path("uri"),
                                        "reference": path("evidence_id"), "format": path("content_type"),
                                        "detection": lit(did)}, "frame")
        return s.column([
            self._header(s, f"Evidence for sighting {did}", f"{_plural(len(items), 'item')} captured",
                         badge=("Evidence", "neutral")),
            s.add("List", {"direction": "horizontal",
                           "children": {"template": {"dataBinding": "/evidence", "componentId": frame}}}),
            s.row([s.button("Sighting details", "open_detection", {"detection_id": lit(did)})]),
        ])

    # analytics ---------------------------------------------------------------
    def _vehicle_count(self, s: Surface, args: dict, r: dict, junctions: list[str]) -> str:
        jn = r.get("junction_id")
        if r.get("found") is False:
            return self._not_found(s, "Unknown junction", f"{jn} is not a monitored junction.", search=False)
        children = [
            self._header(s, "Vehicle count", _window(r.get("start_time"), r.get("end_time")), badge=("Analytics", "neutral")),
            s.row([
                s.stat("Vehicles", f"{r.get('total_vehicles', 0):,}", "neutral", size="large"),
                s.stat("Scope", jn or "All junctions", "neutral"),
                s.stat("Junctions", f"{len(r.get('junctions_included') or [])}", "neutral"),
            ]),
            self._filters(s, [*self._range_inputs(s, r), self._junction_choice(s, junctions, [jn] if jn else [])],
                          "vehicle_count", self._range_context()),
        ]
        if jn:
            children.append(s.row([s.button("Junction statistics", "junction_stats", self._range_context())]))
        return s.column(children)

    def _junction_stats(self, s: Surface, args: dict, r: dict, junctions: list[str]) -> str:
        st = r.get("statistics")
        if not r.get("found") or not st:
            return self._not_found(s, "Unknown junction", "That junction is not monitored.", search=False)
        busiest = _dt(st.get("busiest_hour_start"))
        s.data["types"] = [{"label": _label(k), "value": v}
                           for k, v in sorted(st.get("by_vehicle_type", {}).items(), key=lambda kv: -kv[1])]
        return s.column([
            self._header(s, f"{st['junction_id']} {st['junction_name']}", _window(r.get("start_time"), r.get("end_time")),
                         badge=("Analytics", "neutral")),
            s.row([
                s.stat("Detections", f"{st['total_detections']:,}", "neutral", size="large"),
                s.stat("Per hour", f"{st['average_per_hour']:,}", "neutral"),
                s.stat("Busiest hour", f"{busiest:%H:%M}" if busiest else "None",
                       "neutral", caption=f"{st['busiest_hour_count']:,} vehicles, {busiest:%d %b}" if busiest else ""),
            ]),
            s.add("Donut", {"data": path("/types"), "unit": lit("vehicles")}),
            self._filters(s, [*self._range_inputs(s, r),
                              self._junction_choice(s, junctions, [st["junction_id"]], allow_all=False)],
                          "junction_stats", self._range_context()),
        ])

    def _type_distribution(self, s: Surface, args: dict, r: dict, junctions: list[str]) -> str:
        jn = r.get("junction_id")
        if r.get("found") is False:
            return self._not_found(s, "Unknown junction", f"{jn} is not a monitored junction.", search=False)
        s.data["types"] = [{"label": _label(d["vehicle_type"]), "value": d["count"], "note": f"{d['percentage']}%"}
                           for d in r.get("distribution") or []]
        return s.column([
            self._header(s, f"Vehicle mix, {jn or 'all junctions'}", _window(r.get("start_time"), r.get("end_time")),
                         badge=("Analytics", "neutral")),
            s.add("Donut", {"data": path("/types"), "unit": lit("vehicles")}),
            self._filters(s, [*self._range_inputs(s, r), self._junction_choice(s, junctions, [jn] if jn else [])],
                          "type_distribution", self._range_context()),
        ])

    def _hourly(self, s: Surface, args: dict, r: dict, junctions: list[str]) -> str:
        jn = r.get("junction_id")
        if r.get("found") is False:
            return self._not_found(s, "Unknown junction", f"{jn} is not a monitored junction.", search=False)
        hours = r.get("hours") or []
        peak = r.get("peak_hour")
        quiet = min(hours, key=lambda h: h["vehicle_count"]) if hours and r.get("total_vehicles") else None
        s.data["hours"] = [{"label": f"{h['hour']:02d}", "value": h["vehicle_count"], "highlight": h["hour"] == peak}
                           for h in hours]
        s.data["date"] = r.get("date", "")
        day = _dt(r.get("date"))
        return s.column([
            self._header(s, f"Hourly traffic, {jn or 'all junctions'}", f"{day:%A %d %B %Y}, IST" if day else "",
                         badge=("Analytics", "neutral")),
            s.row([
                s.stat("Vehicles", f"{r.get('total_vehicles', 0):,}", "neutral", size="large"),
                s.stat("Peak hour", f"{peak:02d}:00" if peak is not None else "None", "neutral"),
                s.stat("Quietest hour", f"{quiet['hour']:02d}:00" if quiet else "None", "neutral"),
            ]),
            s.add("BarChart", {"data": path("/hours"), "orientation": "vertical", "colorMode": "heat",
                               "unit": lit("vehicles")}),
            self._filters(s, [s.date_input("/date"), self._junction_choice(s, junctions, [jn] if jn else [])],
                          "hourly_traffic", {"date": path("/date"), "junction_id": path("/junction")}),
        ])

    def _compare(self, s: Surface, args: dict, r: dict, junctions: list[str]) -> str:
        rows = r.get("junctions") or []
        if not r.get("found") or not rows:
            return self._not_found(s, "No junctions to compare", "None of the selected junctions are monitored.",
                                   search=False)
        busiest = next((j for j in rows if j["junction_id"] == r.get("busiest_junction")), rows[0])
        s.data["totals"] = [{"label": f"{j['junction_id']} {j['junction_name']}", "key": j["junction_id"],
                             "value": j["total_detections"], "note": f"{j['share_of_total_pct']}%"} for j in rows]
        return s.column([
            self._header(s, f"Comparing {len(rows)} junctions", _window(r.get("start_time"), r.get("end_time")),
                         badge=("Analytics", "neutral")),
            s.row([
                s.stat("Busiest", f"{busiest['junction_id']}", "neutral", caption=busiest["junction_name"]),
                s.stat("Share of total", f"{busiest['share_of_total_pct']}%", "neutral"),
                s.stat("Combined", f"{sum(j['total_detections'] for j in rows):,}", "neutral"),
            ]),
            s.add("ShareBar", {"data": path("/totals")}),
            s.add("BarChart", {"data": path("/totals"), "orientation": "horizontal", "colorMode": "category",
                               "unit": lit("vehicles")}),
            self._filters(s, [*self._range_inputs(s, r),
                              self._junction_choice(s, junctions, [j["junction_id"] for j in rows],
                                                    allow_all=False, max_selections=10)],
                          "compare_junctions",
                          {"start_time": path("/start"), "end_time": path("/end"), "junction_ids": path("/junction")}),
        ])


_ANALYTICS = {
    "get_vehicle_count", "get_junction_statistics", "get_vehicle_type_distribution",
    "get_hourly_traffic", "compare_junctions",
}
