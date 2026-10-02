"""Minimal A2UI v0.8 message builder (server -> client).

Produces `surfaceUpdate`, `dataModelUpdate` and `beginRendering` messages using the
standard catalog plus the custom components listed in CUSTOM_COMPONENTS. See https://a2ui.org/specification/v0.8-a2ui/
"""

import uuid
from typing import Any

CATALOG_ID = "genui-anpr/v1"  # standard v0.8 catalog + CUSTOM_COMPONENTS
CUSTOM_COMPONENTS = (
    "Plate", "Badge", "Stat", "Timeline", "Direction", "Confidence",
    "BarChart", "Donut", "ShareBar", "EvidenceFrame", "Filters",
)

A2UIMessage = dict[str, Any]


def lit(value: str | int | float | bool) -> dict[str, Any]:
    """Literal BoundValue."""
    if isinstance(value, bool):
        return {"literalBoolean": value}
    if isinstance(value, (int, float)):
        return {"literalNumber": value}
    return {"literalString": str(value)}


def path(p: str) -> dict[str, str]:
    """Data-bound BoundValue. Paths without a leading '/' are relative to a template item."""
    return {"path": p}


def to_contents(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Python data -> A2UI dataModelUpdate adjacency list. Lists become index-keyed maps."""
    out: list[dict[str, Any]] = []
    for key, value in data.items():
        entry: dict[str, Any] = {"key": str(key)}
        if value is None:
            continue
        if isinstance(value, bool):
            entry["valueBoolean"] = value
        elif isinstance(value, (int, float)):
            entry["valueNumber"] = value
        elif isinstance(value, dict):
            entry["valueMap"] = to_contents(value)
        elif isinstance(value, (list, tuple)):
            entry["valueMap"] = to_contents({str(i): v for i, v in enumerate(value)})
        else:
            entry["valueString"] = str(value)
        out.append(entry)
    return out


class Surface:
    """Collects components and data for one surface, then emits A2UI messages."""

    def __init__(self, kind: str, surface_id: str | None = None) -> None:
        self.id = surface_id or f"{kind}-{uuid.uuid4().hex[:8]}"
        self._components: list[dict[str, Any]] = []
        self._ids: set[str] = set()
        self.data: dict[str, Any] = {}
        self._n = 0

    def add(self, type_: str, props: dict[str, Any], id_: str | None = None) -> str:
        if id_ is None:
            self._n += 1
            id_ = f"c{self._n}"
        if id_ in self._ids:
            raise ValueError(f"duplicate component id {id_}")
        self._ids.add(id_)
        self._components.append({"id": id_, "component": {type_: props}})
        return id_

    # standard catalog helpers -------------------------------------------------
    def text(self, value: str | dict[str, Any], hint: str = "body", id_: str | None = None) -> str:
        return self.add("Text", {"text": value if isinstance(value, dict) else lit(value), "usageHint": hint}, id_)

    def row(self, children: list[str], distribution: str = "start", alignment: str = "center", id_: str | None = None) -> str:
        return self.add("Row", {"children": {"explicitList": children}, "distribution": distribution, "alignment": alignment}, id_)

    def column(self, children: list[str], alignment: str = "stretch", id_: str | None = None) -> str:
        return self.add("Column", {"children": {"explicitList": children}, "alignment": alignment}, id_)

    def list_template(self, data_path: str, item_id: str, id_: str | None = None) -> str:
        return self.add(
            "List", {"direction": "vertical", "children": {"template": {"dataBinding": data_path, "componentId": item_id}}}, id_
        )

    def button(self, label: str, action: str, context: dict[str, dict[str, Any]] | None = None,
               primary: bool = False, id_: str | None = None) -> str:
        label_id = self.text(label)
        return self.add(
            "Button",
            {
                "child": label_id,
                "primary": primary,
                "action": {"name": action, "context": [{"key": k, "value": v} for k, v in (context or {}).items()]},
            },
            id_,
        )

    def text_field(self, label: str, data_path: str, id_: str | None = None) -> str:
        return self.add("TextField", {"label": lit(label), "text": path(data_path), "textFieldType": "shortText"}, id_)

    def date_input(self, data_path: str, with_time: bool = False, id_: str | None = None) -> str:
        return self.add("DateTimeInput", {"value": path(data_path), "enableDate": True, "enableTime": with_time}, id_)

    def choice(self, data_path: str, options: list[tuple[str, str]], max_selections: int = 1, id_: str | None = None) -> str:
        return self.add(
            "MultipleChoice",
            {
                "selections": path(data_path),
                "options": [{"label": lit(label), "value": value} for label, value in options],
                "maxAllowedSelections": max_selections,
                "variant": "chips",
            },
            id_,
        )

    # custom catalog -----------------------------------------------------------
    def plate(self, value: str | dict[str, Any], action: str | None = None, id_: str | None = None) -> str:
        props: dict[str, Any] = {"text": value if isinstance(value, dict) else lit(value)}
        if action:
            props["action"] = {"name": action, "context": [{"key": "registration_number", "value": props["text"]}]}
        return self.add("Plate", props, id_)

    def badge(self, value: str | dict[str, Any], tone: str = "neutral", id_: str | None = None,
              mono: bool = False) -> str:
        """Pill. tone is a status variant: success | warning | critical | info | neutral | brand."""
        props: dict[str, Any] = {"text": value if isinstance(value, dict) else lit(value), "tone": tone}
        if mono:
            props["mono"] = True
        return self.add("Badge", props, id_)

    def stat(self, label: str, value: str, tone: str = "neutral", caption: str = "", size: str = "normal",
             id_: str | None = None) -> str:
        props: dict[str, Any] = {"label": lit(label), "value": lit(value), "tone": tone, "size": size}
        if caption:
            props["caption"] = lit(caption)
        return self.add("Stat", props, id_)

    # output -------------------------------------------------------------------
    def messages(self, root: str) -> list[A2UIMessage]:
        msgs: list[A2UIMessage] = [{"surfaceUpdate": {"surfaceId": self.id, "components": self._components}}]
        if self.data:
            msgs.append({"dataModelUpdate": {"surfaceId": self.id, "contents": to_contents(self.data)}})
        msgs.append({"beginRendering": {"surfaceId": self.id, "catalogId": CATALOG_ID, "root": root}})
        return msgs
