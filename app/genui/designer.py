"""LLM-designed A2UI layouts.

The LLM sees the user's request, which tool ran, and the surface's data model (built
from the tool result by composer.py), then writes a layout in a compact JSON form of
the component catalog. That layout is checked here and compiled to A2UI messages.

The LLM decides structure only. Every figure on screen comes from the data model
through a data path; literal text is limited to short labels, and any digits in it
must already appear in the data. Buttons can only use whitelisted actions. A layout
that breaks any rule is rejected and the caller falls back to the template.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError
from app.genui.a2ui import A2UIMessage, Surface, lit, path
from app.genui.actions import ACTIONS
from app.llm.gateway import LLMGateway
from app.schemas.common import Message

logger = logging.getLogger(__name__)

MAX_COMPONENTS = 80
MAX_DEPTH = 14
MAX_LITERAL = 90
PREVIEW_ITEMS = 3

ALIGN = ("start", "center", "end", "stretch")
DISTRIBUTION = ("start", "center", "end", "spaceBetween", "spaceAround")
TONES = ("neutral", "success", "warning", "critical", "info")

# prop -> kind. Kinds: value (literal text or {"path"}), text (literal), data (path to a
# list of {label, value}), items (path to a list), item/child (component id), children
# (list of ids), action, context, columns, bool, or a tuple of allowed strings.
SPECS: dict[str, dict[str, Any]] = {
    "Column": {"children": "children", "align": ALIGN},
    "Row": {"children": "children", "align": ALIGN, "distribution": DISTRIBUTION},
    "Card": {"child": "child"},
    "Divider": {},
    "Text": {"text": "value", "hint": ("h3", "h4", "h5", "body", "caption")},
    "Stat": {"label": "value", "value": "value", "caption": "value", "size": ("normal", "large"), "tone": TONES},
    "Badge": {"text": "value", "tone": (*TONES, "brand"), "mono": "bool"},
    "Plate": {"text": "value", "clickable": "bool"},
    "Direction": {"value": "value"},
    "Confidence": {"value": "value"},
    "BarChart": {"data": "data", "orientation": ("vertical", "horizontal"), "colorMode": ("heat", "category"),
                 "unit": "text"},
    "Donut": {"data": "data", "unit": "text"},
    "ShareBar": {"data": "data"},
    "List": {"items": "items", "item": "item", "direction": ("vertical", "horizontal")},
    "Timeline": {"items": "items", "item": "item", "columns": "columns"},
    "EvidenceFrame": {"kind": "value", "label": "value", "uri": "value", "reference": "value", "format": "value",
                      "detection": "value"},
    "Button": {"label": "text", "action": "action", "context": "context", "primary": "bool"},
    "Block": {"name": "text"},
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "Column": ("children",), "Row": ("children",), "Card": ("child",), "Text": ("text",),
    "Stat": ("label", "value"), "Badge": ("text",), "Plate": ("text",), "Direction": ("value",),
    "Confidence": ("value",), "BarChart": ("data",), "Donut": ("data",), "ShareBar": ("data",),
    "List": ("items", "item"), "Timeline": ("items", "item"), "EvidenceFrame": ("uri",),
    "Button": ("label", "action"), "Block": ("name",),
}

ACTION_CONTEXT = {
    "search_vehicle": "registration_number",
    "vehicle_history": "registration_number",
    "vehicle_details": "registration_number",
    "open_evidence": "detection_id",
    "open_detection": "detection_id",
    "vehicle_count": "start_time, end_time, junction_id (optional)",
    "junction_stats": "junction_id, start_time, end_time",
    "type_distribution": "start_time, end_time, junction_id (optional)",
    "hourly_traffic": "date, junction_id (optional)",
    "compare_junctions": "junction_ids, start_time, end_time",
}

DESIGNER_PROMPT = f"""\
You design the interactive panel shown for one ANPR tool result. You receive the user's request, \
the tool that ran, and the panel's data model. Choose the components and layout that best answer \
the request: lead with what was asked, leave out what was not, and pick the chart that suits the data.

Reply with ONLY a JSON object, no prose and no code fences:
{{"root": "<id>", "components": [{{"id": "<id>", "type": "<Type>", ...props}}, ...]}}

Values: a prop marked VALUE is either a short literal label string, or {{"path": "/key/sub"}} bound to \
the data model. Paths start with "/" except inside a List/Timeline item, where a path without "/" is \
relative to the current item (e.g. {{"path": "junction"}}). Every number, time, plate, ID or count shown \
MUST come from a path; never type data values yourself. Literal text is for headings and labels only.

Components:
- Column {{children: [ids], align?: start|center|end|stretch}}
- Row {{children: [ids], distribution?: start|center|end|spaceBetween|spaceAround, align?}}
- Card {{child: id}}   Divider {{}}
- Text {{text: VALUE, hint?: h3|h4|h5|body|caption}}
- Stat {{label: VALUE, value: VALUE, caption?: VALUE, size?: normal|large, tone?: neutral|success|warning|critical|info}}
- Badge {{text: VALUE, tone?, mono?: bool}}
- Plate {{text: VALUE, clickable?: bool}}  registration plate; clickable opens the vehicle record
- Direction {{value: VALUE}}  compass heading code (N, NE, ...)
- Confidence {{value: VALUE}}  plate-read confidence 0..1
- BarChart {{data: "/path", orientation?: vertical|horizontal, colorMode?: heat|category, unit?: "text"}}
- Donut {{data: "/path", unit?: "text"}}   ShareBar {{data: "/path"}}
  (chart data paths must point to a list of objects with "label" and "value")
- List {{items: "/path", item: id, direction?: vertical|horizontal}}  repeats component `item` per list entry
- Timeline {{items: "/path", item: id, columns: ["header", ...]}}  table-like list; `item` is usually a Row
- EvidenceFrame {{kind, label, uri, reference, format, detection: VALUE}}  one evidence image/clip
- Button {{label: "text", action: name, context?: {{key: VALUE}}, primary?: bool}}
- Block {{name: "filters"|"search"}}  a prebuilt widget; only names listed in `blocks` exist

Button actions (and the context keys they need):
{chr(10).join(f"- {name}: {keys}" for name, keys in ACTION_CONTEXT.items())}

Guidance: "/summary" holds the computed headline figures (title, subtitle, stats); bind Stat values \
to "/summary/stats/<key>/value". Include the "filters" block when it exists so the user can change the \
time range or junction, unless the request is a single quick fact. Offer useful next steps as buttons. \
Keep it compact (usually 4-15 components). Use only data that exists in the data model.
"""


class LayoutError(ValueError):
    """The LLM's layout broke a catalog or data rule."""


@dataclass(frozen=True)
class Design:
    """A validated LLM layout; it can be re-applied when the same surface gets new data."""

    root: str
    nodes: dict[str, dict[str, Any]]


def data_model(surface: Surface) -> dict[str, Any]:
    return {**surface.data, "summary": surface.facts}


def _get(data: Any, p: str) -> Any:
    node = data
    for key in (k for k in p.split("/") if k):
        if isinstance(node, dict):
            node = node.get(key)
        elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            return None
    return node


def _preview(value: Any, at: str, lengths: dict[str, int]) -> Any:
    """Data model for the prompt: lists cut to a few items, with their real length noted."""
    if isinstance(value, dict):
        return {k: _preview(v, f"{at}/{k}", lengths) for k, v in value.items()}
    if isinstance(value, list):
        lengths[at] = len(value)
        return [_preview(v, f"{at}/{i}", lengths) for i, v in enumerate(value[:PREVIEW_ITEMS])]
    return value


def parse_layout(text: str) -> Design:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise LayoutError("reply contains no JSON object")
    try:
        obj = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise LayoutError(f"invalid JSON: {exc}") from exc
    comps = obj.get("components") if isinstance(obj, dict) else None
    if not isinstance(comps, list) or not comps:
        raise LayoutError("'components' must be a non-empty list")
    if len(comps) > MAX_COMPONENTS:
        raise LayoutError(f"too many components (max {MAX_COMPONENTS})")
    nodes: dict[str, dict[str, Any]] = {}
    for c in comps:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"]:
            raise LayoutError("every component needs a string 'id'")
        if c["id"] in nodes:
            raise LayoutError(f"duplicate id '{c['id']}'")
        nodes[c["id"]] = c
    root = obj.get("root")
    if root not in nodes:
        raise LayoutError("'root' must be the id of a component")
    return Design(root=root, nodes=nodes)


class _Compiler:
    """Checks one Design against one surface's data and emits A2UI components."""

    def __init__(self, design: Design, surface: Surface) -> None:
        self.design = design
        self.surface = surface
        self.data = data_model(surface)
        self.corpus = json.dumps(self.data, default=str, ensure_ascii=False)
        self.out = Surface("llm", surface.id)
        self.out.data = self.data
        self.done: dict[str, tuple[str, str]] = {}  # node id -> (data scope, emitted id)
        self.blocks: dict[str, str] = {}

    def run(self) -> list[A2UIMessage]:
        root = self.node(self.design.root, scope="", stack=())
        return self.out.messages(root)

    # values ------------------------------------------------------------------
    def literal(self, value: str, where: str) -> str:
        if len(value) > MAX_LITERAL:
            raise LayoutError(f"{where}: literal text longer than {MAX_LITERAL} characters")
        for digits in re.findall(r"\d+", value):
            if digits not in self.corpus:
                raise LayoutError(f"{where}: literal '{value}' contains a number not in the data; bind it with a path")
        return value

    def resolve(self, p: Any, scope: str, where: str) -> Any:
        if not isinstance(p, str) or not p:
            raise LayoutError(f"{where}: path must be a non-empty string")
        if not p.startswith("/") and not scope:
            raise LayoutError(f"{where}: relative path '{p}' outside a List/Timeline item")
        full = p if p.startswith("/") else f"{scope}/{p}"
        value = _get(self.data, full)
        if value is None:
            raise LayoutError(f"{where}: path '{p}' does not exist in the data model")
        return value

    def value(self, v: Any, scope: str, where: str) -> dict[str, Any]:
        if isinstance(v, dict) and set(v) == {"path"}:
            if isinstance(self.resolve(v["path"], scope, where), (dict, list)):
                raise LayoutError(f"{where}: path '{v['path']}' is not a single value")
            return path(v["path"])
        if isinstance(v, str):
            return lit(self.literal(v, where))
        raise LayoutError(f"{where}: expected a label string or {{\"path\": ...}}")

    def chart_data(self, p: Any, scope: str, where: str) -> dict[str, str]:
        rows = self.resolve(p, scope, where)
        if not isinstance(rows, list) or not all(
            isinstance(r, dict) and "label" in r and isinstance(r.get("value"), (int, float)) for r in rows
        ):
            raise LayoutError(f"{where}: '{p}' is not a list of {{label, value}} objects")
        return path(p)

    # components --------------------------------------------------------------
    def node(self, nid: Any, scope: str, stack: tuple[str, ...]) -> str:
        if not isinstance(nid, str) or nid not in self.design.nodes:
            raise LayoutError(f"reference to unknown component '{nid}'")
        if nid in stack:
            raise LayoutError(f"component '{nid}' contains itself")
        if len(stack) >= MAX_DEPTH:
            raise LayoutError("layout nested too deeply")
        if nid in self.done:
            seen_scope, out_id = self.done[nid]
            if seen_scope != scope:
                raise LayoutError(f"component '{nid}' is used both inside and outside a list item")
            return out_id
        n = self.design.nodes[nid]
        ctype = n.get("type")
        spec = SPECS.get(ctype)  # type: ignore[arg-type]
        where = f"{ctype} '{nid}'"
        if spec is None:
            raise LayoutError(f"component '{nid}': unknown type '{ctype}'")
        props = {k: v for k, v in n.items() if k not in ("id", "type")}
        if extra := set(props) - set(spec):
            raise LayoutError(f"{where}: unknown props {sorted(extra)}")
        if missing := [k for k in REQUIRED.get(ctype, ()) if k not in props]:
            raise LayoutError(f"{where}: missing {missing}")
        for k, v in props.items():
            if isinstance(spec[k], tuple) and v not in spec[k]:
                raise LayoutError(f"{where}: {k} must be one of {list(spec[k])}")
            if spec[k] == "bool" and not isinstance(v, bool):
                raise LayoutError(f"{where}: {k} must be true or false")

        if ctype == "Block":
            root = self.block(props["name"])
            self.done[nid] = (scope, root)
            return root
        out_id = f"u-{nid}"
        self.done[nid] = (scope, out_id)  # a node reached twice is emitted once
        self.out.add(ctype, self.build(ctype, props, scope, (*stack, nid), where), out_id)
        return out_id

    def children(self, ids: Any, scope: str, stack: tuple[str, ...], where: str) -> dict[str, list[str]]:
        if not isinstance(ids, list) or not ids:
            raise LayoutError(f"{where}: children must be a non-empty list of ids")
        return {"explicitList": [self.node(i, scope, stack) for i in ids]}

    def template(self, props: dict, scope: str, stack: tuple[str, ...], where: str) -> dict[str, Any]:
        items = props["items"]
        rows = self.resolve(items, scope, where)
        if not isinstance(rows, list) or not rows:
            raise LayoutError(f"{where}: items '{items}' is not a non-empty list")
        base = items if items.startswith("/") else f"{scope}/{items}"
        item = self.node(props["item"], f"{base}/0", stack)  # checked against the first entry
        return {"template": {"dataBinding": items, "componentId": item}}

    def block(self, name: Any) -> str:
        root = self.surface.blocks.get(name) if isinstance(name, str) else None
        if root is None:
            raise LayoutError(f"block '{name}' is not available for this panel")
        if name not in self.blocks:
            for comp in self.surface.subtree(root):
                self.out.add(*next(iter(comp["component"].items())), comp["id"])
            self.blocks[name] = root
        return root

    def build(self, ctype: str, p: dict, scope: str, stack: tuple[str, ...], where: str) -> dict[str, Any]:
        v = lambda k: self.value(p[k], scope, f"{where}.{k}")  # noqa: E731
        if ctype in ("Column", "Row"):
            out = {"children": self.children(p["children"], scope, stack, where),
                   "alignment": p.get("align", "stretch" if ctype == "Column" else "center")}
            if ctype == "Row":
                out["distribution"] = p.get("distribution", "start")
            return out
        if ctype == "Card":
            return {"child": self.node(p["child"], scope, stack)}
        if ctype == "Divider":
            return {}
        if ctype == "Text":
            return {"text": v("text"), "usageHint": p.get("hint", "body")}
        if ctype == "Stat":
            out = {"label": v("label"), "value": v("value"), "tone": p.get("tone", "neutral"),
                   "size": p.get("size", "normal")}
            if "caption" in p:
                out["caption"] = v("caption")
            return out
        if ctype == "Badge":
            return {"text": v("text"), "tone": p.get("tone", "neutral"), **({"mono": True} if p.get("mono") else {})}
        if ctype == "Plate":
            text = v("text")
            out = {"text": text}
            if p.get("clickable"):
                out["action"] = {"name": "vehicle_details", "context": [{"key": "registration_number", "value": text}]}
            return out
        if ctype in ("Direction", "Confidence"):
            return {"value": v("value")}
        if ctype in ("BarChart", "Donut", "ShareBar"):
            out = {"data": self.chart_data(p["data"], scope, f"{where}.data")}
            if ctype == "BarChart":
                out["orientation"] = p.get("orientation", "horizontal")
                out["colorMode"] = p.get("colorMode", "category")
            if ctype != "ShareBar":
                out["unit"] = lit(self.literal(str(p.get("unit", "")), f"{where}.unit"))
            return out
        if ctype == "List":
            return {"direction": p.get("direction", "vertical"), "children": self.template(p, scope, stack, where)}
        if ctype == "Timeline":
            cols = p.get("columns", [])
            if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
                raise LayoutError(f"{where}: columns must be a list of strings")
            return {"columns": [self.literal(c, f"{where}.columns") for c in cols],
                    "children": self.template(p, scope, stack, where)}
        if ctype == "EvidenceFrame":
            return {k: v(k) for k in SPECS["EvidenceFrame"] if k in p}
        if ctype == "Button":
            name = p["action"]
            if name not in ACTIONS:
                raise LayoutError(f"{where}: unknown action '{name}'")
            ctx = p.get("context") or {}
            if not isinstance(ctx, dict):
                raise LayoutError(f"{where}: context must be an object")
            entries = []
            for k, val in ctx.items():
                if isinstance(val, dict) and set(val) == {"path"}:
                    self.resolve(val["path"], scope, f"{where}.context.{k}")  # lists allowed (multi-select)
                    bound = path(val["path"])
                else:
                    bound = self.value(val, scope, f"{where}.context.{k}")
                entries.append({"key": str(k), "value": bound})
            label = self.out.text(self.literal(str(p["label"]), f"{where}.label"), id_=f"l-{stack[-1]}")
            return {"child": label, "primary": bool(p.get("primary")), "action": {"name": name, "context": entries}}
        raise LayoutError(f"{where}: unsupported type")


def compile_layout(design: Design, surface: Surface) -> list[A2UIMessage]:
    """A2UI messages for `design` over `surface`'s data. Raises LayoutError."""
    try:
        return _Compiler(design, surface).run()
    except LayoutError:
        raise
    except (ValueError, TypeError, AttributeError) as exc:  # e.g. a malformed prop shape
        raise LayoutError(f"malformed layout: {exc}") from exc


class LayoutDesigner:
    """Asks the LLM for a layout, validates it, and retries once with the error."""

    def __init__(self, llm: LLMGateway, timeout: float = 25.0, repairs: int = 1) -> None:
        self._llm = llm
        self._timeout = timeout
        self._repairs = repairs

    def request(self, intent: str, tool: str, args: dict[str, Any], surface: Surface) -> str:
        lengths: dict[str, int] = {}
        preview = _preview(data_model(surface), "", lengths)
        return json.dumps({
            "request": intent,
            "tool": tool,
            "arguments": args,
            "blocks": sorted(surface.blocks),
            "list_lengths": lengths,
            "data_model": preview,
        }, default=str, ensure_ascii=False)

    async def design(
        self, intent: str, tool: str, args: dict[str, Any], surface: Surface
    ) -> tuple[Design, list[A2UIMessage]] | None:
        try:
            return await asyncio.wait_for(self._design(intent, tool, args, surface), self._timeout)
        except asyncio.TimeoutError:
            logger.warning("LLM layout for %s timed out after %gs", tool, self._timeout)
        except AppError as exc:
            logger.warning("LLM layout for %s failed: %s", tool, exc.message)
        return None

    async def _design(
        self, intent: str, tool: str, args: dict[str, Any], surface: Surface
    ) -> tuple[Design, list[A2UIMessage]] | None:
        history = [Message(role="user", content=self.request(intent, tool, args, surface))]
        for attempt in range(self._repairs + 1):
            reply = (await self._llm.complete(history, [], DESIGNER_PROMPT)).content
            try:
                design = parse_layout(reply)
                return design, compile_layout(design, surface)
            except LayoutError as exc:
                logger.info("LLM layout for %s rejected (attempt %d): %s", tool, attempt + 1, exc)
                history += [
                    Message(role="assistant", content=reply),
                    Message(role="user", content=f"That layout was rejected: {exc}. Reply with the corrected JSON only."),
                ]
        return None
