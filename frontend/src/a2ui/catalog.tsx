// Component catalog: A2UI v0.8 standard components used by the runtime, plus the
// "genui-anpr/v1" custom components from ./custom (see CUSTOM_COMPONENTS in app/genui/a2ui.py).

import { useId, useState, type ComponentType } from "react";
import { boundPath, Children, Node, useBound, useSurface } from "./Surface";
import { custom } from "./custom";

export interface CatalogProps {
  id: string;
  props: Record<string, any>;
  scope: string;
}

/* ---------- standard catalog ---------- */

function Text({ props, scope }: CatalogProps) {
  const value = useBound(props.text, scope);
  const hint: string = props.usageHint ?? "body";
  const text = value == null ? "" : String(value);
  if (/^h[1-5]$/.test(hint)) {
    const Tag = `h${Math.min(Number(hint[1]) + 1, 6)}` as "h2"; // surfaces sit under the page heading
    return <Tag className={`gu-text gu-${hint}`}>{text}</Tag>;
  }
  return <p className={`gu-text gu-${hint}`}>{text}</p>;
}

const layout = (p: Record<string, any>) => `gu-dist-${p.distribution ?? "start"} gu-align-${p.alignment ?? "stretch"}`;

function Row({ props, scope }: CatalogProps) {
  return (
    <div className={`gu-row ${layout(props)}`}>
      <Children spec={props.children} scope={scope} />
    </div>
  );
}

function Column({ props, scope }: CatalogProps) {
  return (
    <div className={`gu-column ${layout(props)}`}>
      <Children spec={props.children} scope={scope} />
    </div>
  );
}

function List({ props, scope }: CatalogProps) {
  return (
    <div className={`gu-list gu-list-${props.direction ?? "vertical"}`}>
      <Children spec={props.children} scope={scope} />
    </div>
  );
}

function Card({ props, scope }: CatalogProps) {
  return (
    <div className="gu-card">
      <Node id={props.child} scope={scope} />
    </div>
  );
}

function Divider({ props }: CatalogProps) {
  return <hr className={`gu-divider gu-divider-${props.axis ?? "horizontal"}`} />;
}

function Button({ id, props, scope }: CatalogProps) {
  const { act, pending } = useSurface();
  return (
    <button
      type="button"
      className={`gu-button${props.primary ? " is-primary" : ""}`}
      disabled={pending}
      onClick={() => act(id, props.action, scope)}
    >
      <Node id={props.child} scope={scope} />
    </button>
  );
}

function TextField({ props, scope }: CatalogProps) {
  const { setValue, act, surface } = useSurface();
  const label = useBound(props.label, scope);
  const value = useBound(props.text, scope) ?? "";
  const path = boundPath(props.text, scope);
  const inputId = useId();
  // Enter submits through the primary button of the same row, if there is one.
  const submit = () => {
    const primary = Object.values(surface.components).find(
      (c) => c.type === "Button" && c.props.primary && JSON.stringify(c.props.action?.context ?? []).includes(props.text?.path ?? "\u0000"),
    );
    if (primary) act(primary.id, primary.props.action, scope);
  };
  return (
    <label className="gu-field" htmlFor={inputId}>
      <span className="gu-field-label">{label}</span>
      <input
        id={inputId}
        type={props.textFieldType === "number" ? "number" : props.textFieldType === "obscured" ? "password" : "text"}
        value={value}
        onChange={(e) => path && setValue(path, e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        autoComplete="off"
        spellCheck={false}
      />
    </label>
  );
}

function DateTimeInput({ props, scope }: CatalogProps) {
  const { setValue } = useSurface();
  const value = useBound(props.value, scope) ?? "";
  const path = boundPath(props.value, scope);
  const withTime = props.enableTime && props.enableDate !== false;
  const type = withTime ? "datetime-local" : props.enableTime ? "time" : "date";
  const inputId = useId();
  return (
    <label className="gu-field" htmlFor={inputId}>
      <span className="gu-field-label">{withTime ? (path?.endsWith("end") ? "To" : "From") : "Date"}</span>
      <input id={inputId} type={type} value={value} onChange={(e) => path && setValue(path, e.target.value)} />
    </label>
  );
}

function MultipleChoice({ props, scope }: CatalogProps) {
  const { setValue } = useSurface();
  const raw = useBound(props.selections, scope);
  const selected: string[] = Array.isArray(raw) ? raw : raw ? [String(raw)] : [];
  const path = boundPath(props.selections, scope);
  const max: number = props.maxAllowedSelections ?? Infinity;
  const toggle = (value: string) => {
    if (!path) return;
    if (max === 1) return setValue(path, [value]);
    const next = selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value];
    setValue(path, next.slice(-max));
  };
  return (
    <div className="gu-chips" role="group" aria-label="Junction">
      {(props.options ?? []).map((o: any) => {
        const label = o.label?.literalString ?? o.value;
        const on = selected.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            className={`gu-chip${on ? " is-on" : ""}`}
            aria-pressed={on}
            onClick={() => toggle(o.value)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function CheckBox({ props, scope }: CatalogProps) {
  const { setValue } = useSurface();
  const label = useBound(props.label, scope);
  const value = !!useBound(props.value, scope);
  const path = boundPath(props.value, scope);
  return (
    <label className="gu-check">
      <input type="checkbox" checked={value} onChange={(e) => path && setValue(path, e.target.checked)} />
      {label}
    </label>
  );
}

function Tabs({ props, scope }: CatalogProps) {
  const [active, setActive] = useState(0);
  const items: any[] = props.tabItems ?? [];
  return (
    <div className="gu-tabs">
      <div role="tablist" className="gu-tablist">
        {items.map((t, i) => (
          <button key={i} role="tab" aria-selected={i === active} className="gu-tab" onClick={() => setActive(i)}>
            {t.title?.literalString}
          </button>
        ))}
      </div>
      {items[active] && <Node id={items[active].child} scope={scope} />}
    </div>
  );
}

function Image({ props, scope }: CatalogProps) {
  const url = useBound(props.url, scope);
  const alt = useBound(props.altText, scope) ?? "";
  return <img className={`gu-image gu-image-${props.usageHint ?? "mediumFeature"}`} src={url} alt={alt} style={{ objectFit: props.fit ?? "cover" }} />;
}

export const catalog: Record<string, ComponentType<CatalogProps>> = {
  Text, Row, Column, List, Card, Divider, Button, TextField, DateTimeInput, MultipleChoice, CheckBox, Tabs, Image,
  ...custom,
};
