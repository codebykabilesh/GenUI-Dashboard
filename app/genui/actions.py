"""Whitelisted A2UI userAction -> MCP tool mapping.

An action whose tool produced the source surface re-renders that surface (a filter
change); any other action adds a new surface (navigation).

A surface can only trigger the actions listed here, and each action can only call
its one tool. Arguments come from the action context and are still validated against
the tool's discovered schema before the call.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.errors import InvalidToolArgumentsError

ALL = "all"


def _str(ctx: dict[str, Any], key: str, required: bool = True) -> str | None:
    value = ctx.get(key)
    if isinstance(value, list):  # MultipleChoice selections
        value = value[0] if value else None
    value = str(value).strip() if value is not None else ""
    if not value or value == ALL:
        if required:
            raise InvalidToolArgumentsError(f"'{key}' is required")
        return None
    return value


def _list(ctx: dict[str, Any], key: str) -> list[str]:
    value = ctx.get(key)
    items = value if isinstance(value, list) else [value] if value else []
    return [str(v) for v in items if v and v != ALL]


def _range(ctx: dict[str, Any]) -> dict[str, Any]:
    return {"start_time": _str(ctx, "start_time"), "end_time": _str(ctx, "end_time")}


def _optional_junction(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    jn = _str(ctx, "junction_id", required=False)
    return {**args, "junction_id": jn} if jn else args


@dataclass(frozen=True)
class UIAction:
    tool: str
    build_args: Callable[[dict[str, Any]], dict[str, Any]]


ACTIONS: dict[str, UIAction] = {
    "search_vehicle": UIAction("search_vehicle", lambda c: {"registration_number": _str(c, "registration_number")}),
    "vehicle_history": UIAction("get_vehicle_history", lambda c: {"registration_number": _str(c, "registration_number")}),
    "vehicle_details": UIAction("get_vehicle_details", lambda c: {"registration_number": _str(c, "registration_number")}),
    "open_evidence": UIAction("get_detection_evidence", lambda c: {"detection_id": _str(c, "detection_id")}),
    "open_detection": UIAction("get_detection_by_id", lambda c: {"detection_id": _str(c, "detection_id")}),
    "vehicle_count": UIAction("get_vehicle_count", lambda c: _optional_junction(_range(c), c)),
    "junction_stats": UIAction("get_junction_statistics",
                               lambda c: {"junction_id": _str(c, "junction_id"), **_range(c)}),
    "type_distribution": UIAction("get_vehicle_type_distribution", lambda c: _optional_junction(_range(c), c)),
    "hourly_traffic": UIAction("get_hourly_traffic", lambda c: _optional_junction({"date": _str(c, "date")}, c)),
    "compare_junctions": UIAction("compare_junctions",
                                  lambda c: {"junction_ids": _list(c, "junction_ids"), **_range(c)}),
}
