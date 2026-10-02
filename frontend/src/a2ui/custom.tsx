// "genui-anpr/v1" custom catalog components (names match CUSTOM_COMPONENTS in app/genui/a2ui.py).
// Styled per UI_THEME.md: tokens only, hue only for status and charts.

import { useState, type ComponentType, type CSSProperties } from "react";
import type { CatalogProps } from "./catalog";
import { Children, useBound, useSurface } from "./Surface";

/** Fixed categorical order (colour-blind checked). Never cycled: a 7th category becomes "Other". */
const CHART = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];
const chartColor = (i: number) => CHART[i] ?? "var(--chart-other)";

const STATUS = new Set(["success", "warning", "critical", "info", "neutral", "brand"]);

/** "KA01AB1234" -> "KA 01 AB 1234" (Indian registration format), otherwise unchanged. */
export function formatPlate(raw: string): string {
  const m = raw.replace(/[\s-]/g, "").toUpperCase().match(/^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/);
  return m ? [m[1], m[2], m[3], m[4]].filter(Boolean).join(" ") : raw.toUpperCase();
}

function Plate({ id, props, scope }: CatalogProps) {
  const { act, pending } = useSurface();
  const value = formatPlate(String(useBound(props.text, scope) ?? ""));
  if (!props.action) return <span className="gu-plate font-mono">{value}</span>;
  return (
    <button
      type="button"
      className="gu-plate font-mono row-hover"
      disabled={pending}
      onClick={() => act(id, props.action, scope)}
      title="Open vehicle record"
    >
      {value}
    </button>
  );
}

function Badge({ props, scope }: CatalogProps) {
  const text = String(useBound(props.text, scope) ?? "");
  const variant = STATUS.has(props.tone) ? props.tone : "neutral";
  return (
    <span className={`gu-badge gu-badge-${variant}${props.mono ? " font-mono" : ""}${props.caps ? " is-caps" : ""}`}>
      {props.dot ? <i aria-hidden="true" /> : null}
      {text}
    </span>
  );
}

/** MetricCard: label, 32px figure, optional meta line. A non-neutral tone paints a 3px left edge. */
function Stat({ props, scope }: CatalogProps) {
  const label = useBound(props.label, scope);
  const value = useBound(props.value, scope);
  const caption = useBound(props.caption, scope);
  const tone = ["success", "warning", "critical", "info"].includes(props.tone) ? props.tone : null;
  return (
    <div
      className="gu-metric"
      style={tone ? ({ "--edge": `var(--${tone}-fill)` } as CSSProperties) : undefined}
      data-tone={tone ?? undefined}
    >
      <span className="gu-metric-label">{label}</span>
      <span className="gu-metric-value">{value}</span>
      {caption ? <span className="gu-metric-meta">{caption}</span> : null}
    </div>
  );
}

const BEARING: Record<string, number> = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 };
const HEADING: Record<string, string> = {
  N: "Northbound", NE: "Northeast", E: "Eastbound", SE: "Southeast",
  S: "Southbound", SW: "Southwest", W: "Westbound", NW: "Northwest",
};

function Direction({ props, scope }: CatalogProps) {
  const code = String(useBound(props.value, scope) ?? "").toUpperCase();
  const deg = BEARING[code];
  return (
    <span className="gu-direction" title={HEADING[code] ?? code}>
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <circle cx="12" cy="12" r="10.5" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" />
        {deg !== undefined && (
          <path d="M12 4.5 L15.5 14 L12 12.2 L8.5 14 Z" fill="var(--text-primary)" transform={`rotate(${deg} 12 12)`} />
        )}
      </svg>
      <span>{HEADING[code] ?? code}</span>
    </span>
  );
}

/** Read confidence band: >= 0.90 success, >= 0.75 warning, lower critical. */
function Confidence({ props, scope }: CatalogProps) {
  const v = Math.max(0, Math.min(1, Number(useBound(props.value, scope) ?? 0)));
  const band = v >= 0.9 ? "success" : v >= 0.75 ? "warning" : "critical";
  const label = v >= 0.9 ? "STRONG" : v >= 0.75 ? "REVIEW" : "WEAK";
  return (
    <span className="gu-confidence" title="Plate read confidence">
      <span className="gu-confidence-value">{Math.round(v * 100)}%</span>
      <span className={`gu-badge gu-badge-${band} is-caps`}>{label}</span>
    </span>
  );
}

interface Datum {
  label: string;
  key?: string;
  value: number;
  note?: string;
  highlight?: boolean;
}

function useData(bound: unknown, scope: string): Datum[] {
  const raw = useBound(bound as any, scope);
  return Array.isArray(raw) ? raw : Object.values(raw ?? {});
}

/** Keep the first five categories and fold the rest into "Other" once there are more than six. */
function capCategories(data: Datum[]): Datum[] {
  if (data.length <= 6) return data;
  const rest = data.slice(5);
  return [...data.slice(0, 5), { label: "Other", key: "Other", value: rest.reduce((a, d) => a + d.value, 0) }];
}

const nextHour = (label: string) => String((Number(label) + 1) % 24).padStart(2, "0");

function BarChart({ props, scope }: CatalogProps) {
  const bars = useData(props.data, scope);
  const unit = String(useBound(props.unit, scope) ?? "");
  const max = Math.max(1, ...bars.map((b) => Number(b.value) || 0));
  const [focus, setFocus] = useState<number | null>(null);

  if (bars.length === 0) return <p className="gu-empty">No values for this selection.</p>;

  if (props.orientation === "vertical") {
    const shown = focus ?? bars.findIndex((b) => b.highlight);
    const current = bars[shown] ?? null;
    return (
      <figure className="gu-vchart">
        <figcaption className="gu-vchart-readout" aria-live="polite">
          {current ? (
            <>
              <strong>{current.value.toLocaleString()}</strong> {unit}, {current.label}:00 to {nextHour(current.label)}:00
              {current.highlight ? <span className="gu-badge gu-badge-neutral">Peak hour</span> : null}
            </>
          ) : (
            " "
          )}
        </figcaption>
        <div className="gu-vchart-plot">
          <span className="gu-vchart-max">{max.toLocaleString()}</span>
          <div className="gu-vchart-bars" onMouseLeave={() => setFocus(null)}>
            {bars.map((b, i) => (
              <button
                type="button"
                key={i}
                className={`gu-vbar${b.highlight ? " is-peak" : ""}${focus === i ? " is-focus" : ""}`}
                onMouseEnter={() => setFocus(i)}
                onFocus={() => setFocus(i)}
                onBlur={() => setFocus(null)}
                aria-label={`${b.label}:00, ${b.value.toLocaleString()} ${unit}`}
              >
                <span className="gu-vbar-fill" style={{ height: `${(b.value / max) * 100}%` }} />
                <span className="gu-vbar-label" aria-hidden="true">{Number(b.label) % 3 === 0 ? b.label : ""}</span>
              </button>
            ))}
          </div>
        </div>
      </figure>
    );
  }

  const category = props.colorMode === "category";
  return (
    <div className="gu-hchart" role="list">
      {bars.map((b, i) => (
        <div key={i} className="gu-hbar" role="listitem">
          <span className="gu-hbar-label">
            {category ? <i style={{ background: chartColor(i) }} aria-hidden="true" /> : null}
            {b.label}
          </span>
          <span className="gu-hbar-track" aria-hidden="true">
            <span
              className="gu-hbar-fill"
              style={{ width: `${(b.value / max) * 100}%`, background: category ? chartColor(i) : CHART[0] }}
            />
          </span>
          <span className="gu-hbar-value">
            {b.value.toLocaleString()}
            {b.note ? <span className="gu-hbar-note"> {b.note}</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}

function Donut({ props, scope }: CatalogProps) {
  const data = capCategories(useData(props.data, scope).filter((d) => d.value > 0));
  const unit = String(useBound(props.unit, scope) ?? "");
  const [hover, setHover] = useState<number | null>(null);
  const total = data.reduce((a, d) => a + d.value, 0);
  if (!total) return <p className="gu-empty">No vehicles in this selection.</p>;
  const r = 58;
  const c = 2 * Math.PI * r;
  const active = hover !== null ? data[hover] : null;
  const starts = data.map((_, i) => data.slice(0, i).reduce((a, d) => a + (d.value / total) * c, 0));
  return (
    <div className="gu-donut">
      <svg viewBox="0 0 160 160" width="160" height="160" role="img" aria-label={`Vehicle mix, ${total.toLocaleString()} ${unit}`}>
        {data.map((d, i) => (
          <circle
            key={i}
            cx="80" cy="80" r={r} fill="none"
            stroke={chartColor(i)}
            strokeWidth={hover === i ? 22 : 18}
            strokeDasharray={`${Math.max((d.value / total) * c - 2, 0)} ${c}`}
            strokeDashoffset={-starts[i]}
            transform="rotate(-90 80 80)"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        <text x="80" y="80" textAnchor="middle" className="gu-donut-total">
          {(active?.value ?? total).toLocaleString()}
        </text>
        <text x="80" y="98" textAnchor="middle" className="gu-donut-unit">
          {active ? active.label : unit}
        </text>
      </svg>
      <table className="gu-legend">
        <thead>
          <tr>
            <th>Type</th>
            <th className="num">Vehicles</th>
            <th className="num">Share</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d, i) => (
            <tr key={i} className={hover === i ? "is-on" : ""} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <td>
                <i style={{ background: chartColor(i) }} aria-hidden="true" />
                {d.label}
              </td>
              <td className="num">{d.value.toLocaleString()}</td>
              <td className="num muted">{d.note ?? `${((d.value / total) * 100).toFixed(1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShareBar({ props, scope }: CatalogProps) {
  const data = capCategories(useData(props.data, scope));
  const total = data.reduce((a, d) => a + d.value, 0);
  if (!total) return null;
  return (
    <div className="gu-share-wrap">
      <div className="gu-share" role="img" aria-label="Share of combined traffic">
        {data.map((d, i) => (
          <span
            key={i}
            className="gu-share-seg"
            style={{ flexGrow: d.value, background: chartColor(i) }}
            title={`${d.label}: ${d.note ?? ""}`}
          />
        ))}
      </div>
      <div className="gu-share-key">
        {data.map((d, i) => (
          <span key={i}>
            <i style={{ background: chartColor(i) }} aria-hidden="true" />
            <span className="font-mono">{d.key ?? d.label}</span>
            <span className="muted">{d.note ?? ""}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Filters({ props, scope }: CatalogProps) {
  return (
    <div className="gu-filters">
      <span className="gu-filters-label">Refine</span>
      <div className="gu-row gu-align-end">
        <Children spec={props.children} scope={scope} />
      </div>
    </div>
  );
}

function EvidenceFrame({ props, scope }: CatalogProps) {
  const kind = String(useBound(props.kind, scope) ?? "");
  const label = String(useBound(props.label, scope) ?? kind);
  const reference = String(useBound(props.reference, scope) ?? "");
  const format = String(useBound(props.format, scope) ?? "");
  const detection = String(useBound(props.detection, scope) ?? "");
  return (
    <figure className="gu-frame">
      <div className="gu-frame-view" aria-hidden="true">
        <span className="gu-frame-hud gu-frame-hud-tl font-mono">{detection}</span>
        <span className="gu-frame-hud gu-frame-hud-br font-mono">{format}</span>
        <span className="gu-frame-kind">{label}</span>
      </div>
      <figcaption className="gu-fact">
        <span className="gu-fact-label">Reference</span>
        <span className="gu-fact-value font-mono">{reference}</span>
      </figcaption>
    </figure>
  );
}

/** Sightings table: optional column headers, one templated row per sighting. */
function Timeline({ props, scope }: CatalogProps) {
  const columns: string[] = props.columns ?? [];
  return (
    <div className="gu-table" role="table">
      {columns.length > 0 && (
        <div className="gu-table-head" role="row">
          {columns.map((c, i) => (
            <span key={i} role="columnheader">{c}</span>
          ))}
        </div>
      )}
      <ol className="gu-table-body">
        <Children spec={props.children} scope={scope} item="li" />
      </ol>
    </div>
  );
}

export const custom: Record<string, ComponentType<CatalogProps>> = {
  Plate, Badge, Stat, Timeline, Direction, Confidence, BarChart, Donut, ShareBar, EvidenceFrame, Filters,
};
