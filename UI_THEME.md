# VISTA / Chennai ANPR — UI Theme & Page Guide

Reference for building new pages in `frontend design/` so they match the existing
screens (Command Centre, Live Feeds, Investigation, Trajectory, Analytics, Node
Insights, Alerts, Blacklist).

**Source of truth:** [src/styles/tokens.css](src/styles/tokens.css) (all tokens, light + dark)
and [src/index.css](src/index.css) (Tailwind bridge, global rules, animations).
Domain rules: [.claude/skills/command-center-ui-design/SKILL.md](.claude/skills/command-center-ui-design/SKILL.md).

---

## 1. Stack

- React 19 + TypeScript, Vite, React Router 7, TanStack Query
- Tailwind CSS v4 (`@import 'tailwindcss'` in `index.css`; no `tailwind.config`)
- Icons: `lucide-react` only (one set, outline style)
- Charts: `recharts` for real charts; hand-rolled SVG for tile sparklines (`MiniBars`)
- Maps: `maplibre-gl` (+ `terra-draw` for geofences)
- Font: **Public Sans** (Google Fonts, weights 400/500/600/700), loaded in `index.html`

**How styles are written:** Tailwind classes handle layout (`flex`, `grid`, `gap`,
`px-4`, `rounded-md`, `truncate`, …). Colours, font sizes and other design values
come from CSS variables, usually through inline `style={{ … 'var(--token)' }}`.
**Never hardcode a hex in a component.** Always use a token so dark mode works.
Tailwind colour utilities also map to the tokens (`bg-surface-panel`,
`text-text-secondary`, `border-border-default`, `bg-critical-tint`, …) via the
`@theme` block in `index.css`.

---

## 2. Design idea

A **warm, near-monochrome control-room theme**. Operators watch these screens all
shift, so **colour means status, never decoration.**

- Most of the screen is cream, white, warm grey and black.
- **Sand (`#f2dfc9`) is the only accent hue.** Use it for the active or selected state.
- **Red, amber, green and blue are reserved for status** (critical, warning,
  success, info). They are never used for decoration or as chart series.
- **Hue only comes back in charts**, through a fixed six-colour palette.
- Restraint everywhere: flat cards, hairline borders, one primary button per
  screen, ALL CAPS only for important state words.

---

## 3. Colour tokens

### Light theme (the default)

| Role | Token | Value | Use |
|---|---|---|---|
| Page ground | `--surface-page` | `#faf6f1` cream | App background |
| Panel | `--surface-panel` | `#ffffff` | Cards, tables, top bars, modals |
| Subtle / inset | `--surface-subtle` | `#f3e8e1` beige | Table headers, inline forms, skeletons, disabled controls |
| Map ground | `--surface-map` | `#f3e8e1` | Map backgrounds |
| Quiet tile | `--surface-quiet` | = subtle | Fact cards |
| Header | `--surface-header` | `#000000` | Masthead (rendered as black glass) |
| Primary ink | `--brand-primary` | `#000000` | Primary button, links, selected-row edge, focus ring |
| Primary hover / active | `--brand-primary-hover` / `-active` | `#2a211a` / `#453830` | |
| On primary | `--brand-on-primary` | `#ffffff` | Text on a primary button |
| **Accent (sand)** | `--brand-primary-tint` | `#f2dfc9` | Selected row, active chip, "brand" badge |
| Text | `--text-primary` | `#171310` | Body text and figures |
| | `--text-secondary` | `#5c534b` | Labels, subtitles, secondary columns |
| | `--text-muted` | `#6f655c` | Meta text, units, placeholders, empty states |
| | `--text-inverse` | `#faf6f1` | |
| Borders | `--border-default` | `#eadfd5` | Every hairline: cards, rows, inputs |
| | `--border-strong` | `#cdbcab` | Secondary button outline, table header underline, hover border |
| | `--border-hairline` | `1px solid var(--border-default)` | Complete border shorthand |
| Overlays | `--hover-overlay` / `--press-overlay` | 5% / 10% ink | Hover and press washes |
| | `--scrim` | 45% ink | Modal backdrop |

### Status colours (hue is used ONLY here)

Each status has three tokens:
- `*-fill`: dots, borders, map markers, icons, the 3px left edge. **Not for text backgrounds.**
- `*-tint`: background of a badge or pill.
- `*-on-tint`: text placed on that tint. Contrast is at least 4.5:1.

| Status | fill | tint | on-tint |
|---|---|---|---|
| critical | `#c1272d` | `#fbe3e1` | `#7d1418` |
| warning | `#b9690a` | `#fbedd8` | `#75400a` |
| success | `#2f7d4f` | `#e2f1e7` | `#1c5233` |
| info | `#2f6fb5` | `#e3edf8` | `#1d4876` |
| neutral | `#8b8076` | `#f6f1eb` | `#453d35` |

**Severity mapping used across every screen:**

```ts
CRITICAL → critical-*   HIGH → warning-*   MEDIUM → info-*
LOW      → bg: --surface-subtle, text: --text-secondary, border: --border-default
```

Confidence or score bands: ≥ 0.90 is success, ≥ 0.75 is warning, anything lower is critical.

### Chart palette (categorical; fixed order, never cycled)

`--chart-1` blue `#347dbb`, `--chart-2` brass `#915b02`, `--chart-3` teal `#0b9d9d`,
`--chart-4` orange `#e45a01`, `--chart-5` magenta `#ab4399`, `--chart-6` olive `#628202`.
Any seventh category goes into "Other". The order was chosen with a colour-blindness
validator (`npm run check:palette`), so don't reorder it. Also use
`--chart-surface` (the background behind charts) and `--chart-grid` (gridlines,
10% ink). A single-series chart uses `--chart-1`.

### Dark theme

Dark mode is turned on with `data-theme="dark"` on `<html>`. Every token above is
redefined for dark mode, with warm darks: page `#1a1613`, panel `#241f1b`,
subtle `#2e2722`, text `#f5ede6`, primary becomes light beige `#f3e8e1` with dark
text on it, and status and chart colours are re-stepped for dark backgrounds.
**If you only use tokens, dark mode works automatically.** Exceptions that stay
fixed: the header is always black glass with white text, and danger buttons use
`#fff` text on `--critical-fill`.

---

## 4. Typography

One font family across the whole product. `body` sets
`font-variant-numeric: tabular-nums`, so numbers line up in columns.
`--font-mono` and `--font-data` also resolve to Public Sans. Tailwind's
`font-mono` class is still used **as a semantic marker** for plates, IDs, camera
IDs, timestamps and coordinates.

| Token | Size | Use |
|---|---|---|
| `--text-platform-title` | 24px | (rare) platform title |
| `--text-panel-title` | 20px | Page title in the top bar (`text-[20px] font-medium`) |
| `--text-kpi-lg` / `--text-kpi` | 40 / 32px | KPI figures (weight 600, `letter-spacing: -0.02em`) |
| `--text-body` | 16px | Long-form text |
| `--text-data` | 14px | **Default body size** (set on page root); card titles |
| `--text-meta` | 12px | Labels, meta lines, buttons, table body |
| `--text-micro` | 11px | Badges, subtitles, table headers, timestamps |

Weights: 400 regular, 500 medium (titles, labels), 600 bold (KPIs, plates, page
emphasis). **Never use 700** for figures.
Line heights: `--leading-tight` 1.25, `--leading-snug` 1.5, `--leading-normal` 1.65.

**Casing:** use sentence case by default. Use ALL CAPS only for severity words
(CRITICAL, HIGH), match bands (EXACT, STRONG, REVIEW) and table headers
(`text-[11px] font-semibold uppercase tracking-[0.06em]`).

---

## 5. Spacing, shape, elevation, motion

- **Spacing scale:** `--space-1…12` = 4, 8, 12, 16, 20, 24, 32, 40, 48px.
  `--card-padding` 18px. `--panel-gap` 12px between panels (`--panel-gap-lg` 16px).
- **Radius:** `--radius-card` 12px (cards, tiles), `--radius-control` 8px
  (inputs, buttons; Tailwind `rounded-md` is also used), `--radius-pill` 999px
  (badges, nav items).
- **Control heights:** `--control-height` 40px. Buttons in practice are 32px
  (`Button`) or 36px (`h-9`).
- **Icons:** 20px default, 16px small, 14px inside tiles and buttons.
- **Elevation: only three levels.**
  1. *Flush*: hairline border, no shadow. This is **every ordinary card**.
  2. `--shadow-raised`: floating chrome over a map or chart (legends, toolbars). Use `RaisedPanel`.
  3. `--shadow-overlay`: popovers, dropdown menus, tooltips.
  - `--elevation-critical` is the strongest shadow and is reserved for a card
    showing an active alert (`Card tone="alert"`).
- **Motion:** 150–250ms, decelerating curve `--easing-standard`, no bounce.
  Use `var(--transition-state)` for colour, background, border and shadow
  changes. `prefers-reduced-motion` is respected globally.
  **Cards never grow or move on hover.** Only clickable items (rows, tiles,
  buttons) react to hover.

---

## 6. Page shell (copy this for every new page)

```tsx
import { Header } from '../../components/Header'
import { useTheme } from '../../hooks/useTheme'

export function MyPage() {
  const { theme, toggleTheme } = useTheme()   // the ONLY theme source; never keep local theme state
  return (
    <div
      className="flex h-screen w-screen flex-col overflow-hidden"
      style={{ background: 'var(--surface-page)', fontFamily: 'var(--font-sans)',
               color: 'var(--text-primary)', fontSize: 'var(--text-data)' }}
    >
      <Header theme={theme} onToggleTheme={toggleTheme} />

      {/* Optional top bar: white strip, hairline underneath */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-3"
           style={{ background: 'var(--surface-panel)', borderBottom: '1px solid var(--border-default)' }}>
        <div className="flex items-center gap-3">
          <SomeLucideIcon size={20} />
          <div className="text-[20px] font-medium">Page title</div>
        </div>
        {/* the one primary action */}
      </div>

      {/* Optional KPI strip */}
      <div className="grid px-4 pt-4"
           style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--panel-gap)' }}>
        <MetricCard label="…" value="…" meta="…" metaValue="…" />
      </div>

      {/* Body: main area scrolls; optional right-hand detail panel */}
      <div className="flex min-h-0 flex-1 items-stretch">
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto p-4">…</main>
        {selected ? <DetailPanel /> : null}
      </div>
    </div>
  )
}
```

Then:
1. Add a `<Route>` in [src/App.tsx](src/App.tsx).
2. Add an entry to `NAV_ITEMS` in [src/components/Header.tsx](src/components/Header.tsx).

**Header** (shared, don't rebuild it): a floating black-glass bar
(`rgba(0,0,0,.92)` + blur, 20px radius, 12px margin) containing the GCTP mark,
"Chennai City ANPR / Intelligence Platform", pill-shaped nav links (the active
link is `bg-white/12` with semibold white text), a live IST clock, and an
operator menu that holds the theme toggle.

---

## 7. Shared components ([src/components/ui/](src/components/ui/))

| Component | Use |
|---|---|
| `Card` | Standard panel. Props: `title`, `subtitle`, `actions`, `flush` (header with a divider and no body padding, for tables), `tone`: `default` (white, flat), `ambient` (beige, for supporting info), `alert` (amber border + critical elevation; only for an active alert). |
| `RaisedPanel` | Floating chrome over a map or chart. |
| `MetricCard` | KPI tile: small label + 32px figure + optional `unit`, MiniBars `trend`, and a `meta` / `metaValue` key–value footer. `tone` other than `neutral` paints a **3px left edge**; use it only when the metric needs attention. For a compact version pass `style={{ padding: '10px 14px', gap: 4, '--text-kpi': '24px' }}`. |
| `Badge` / `StatusPill` | Pill with variants `success \| warning \| critical \| info \| neutral \| brand`, optional `dot`, `live` (pulsing dot), `caps`. |
| `Button` | `primary` (ink fill), `secondary` (strong outline), `ghost` (hairline, secondary text). Height 32px, 12px text, optional `icon`. |
| `Icon` | Kebab-case names mapped to lucide (`<Icon name="shield-alert" />`). Add new names to the map in that file. |
| `MiniBars` | Sparkline bars inside tiles: the latest bar is full opacity, earlier bars are at 45%. |
| `DonutProgress`, `Sparkline` | Older components; prefer `MiniBars` for new tiles. |

Page-local components worth reusing: `SegmentedControl`, `Input`
(`pages/command-centre/components`), `Select` (`pages/analytics/components/ui`),
`FactRow` (`pages/node-insights/components`), `TabButton` (`pages/alerts/components`).

---

## 8. Common patterns

**Buttons**
- One primary action per screen: `background: var(--brand-primary)`, `color: var(--brand-on-primary)`, `h-9 rounded-md px-4 text-[12.5px] font-semibold`.
- Routine or reversible actions use `secondary` or `ghost`.
- Destructive actions use `--critical-fill` with `#fff` text **and require a confirmation modal**.
- Disabled: `--surface-subtle` background, `--text-muted` text, `--border-default` border.

**Inputs and selects:** height 36px, `rounded-md px-2.5 text-[13px]`, background
`--surface-panel`, border `1px solid var(--border-default)`. The label sits above
the field: `text-[11px] font-medium` in `--text-secondary`. Plate inputs use `font-mono`.

**Tables**
- Header row: `--surface-subtle` background, `--text-secondary` text, and `boxShadow: inset 0 -1px 0 var(--border-strong)`. Make it sticky.
- Body: 12px text, `px-3 py-1.5` cells, `border-bottom: var(--border-hairline)`.
- Hover: add class `row-hover`. **Don't** set an inline background on unselected rows, because it overrides the hover style.
- Selected row: `background: var(--brand-primary-tint)` + `boxShadow: inset 2px 0 0 var(--brand-primary)`.
- Plates: `font-mono font-semibold tracking-wide`. Times, IDs and camera IDs: `font-mono tabular-nums` in `--text-secondary`.
- Missing value: `—` in `--text-muted`.

**Severity / status pill:** `rounded-full px-2 py-0.5 text-[10px] font-semibold`,
tint background + on-tint text (+ optional 1px fill border).

**Key–value facts:** label on the left (`--text-muted`), value right-aligned
(`font-mono`, `--text-secondary`) using `flex items-baseline justify-between`.
**Don't join facts with middle dots** ("A · B").

**Modal:** fixed overlay with `rgba(0,0,0,.5)` + `blur(2px)` (or `--scrim`).
The dialog is `max-w-[400px] rounded-xl p-5`, `--surface-panel` background,
hairline border. Close it on backdrop click and on Escape.

**Popover / menu:** `--surface-panel`, hairline border, `--shadow-overlay`, `rounded-lg`.

**States**
- *Loading:* skeleton rows `<div className="skeleton-shimmer h-7 rounded" />` (8 rows, each fading slightly).
- *Empty:* centred text: a 13px medium line followed by an 11.5px `--text-secondary` hint saying what to do next.
- *Error:* 12px text in `--critical-fill`.

**Liveness (makes the screen feel live):** `live-dot` class (pulsing dot,
e.g. `<Badge dot live variant="success">LIVE</Badge>`), "updated Ns ago"
counters that tick, the `row-enter` class for newly arrived rows, and
`current-marker` for the current map position.

**Charts (recharts):**
- `CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 3"`.
- Axis line `--border-default`, tick text `--text-muted` at 11px.
- Series in `--chart-1…6`, stroke width 2. Area fill is a gradient of the series colour from 0.42 to 0.02 opacity.
- Dots use `stroke: var(--surface-panel)` so they stand off the line.
- Reference or baseline lines are `--text-muted`, dashed `4 4`.
- Custom tooltip box styled like a popover.

**Focus and hover:** handled globally. Every button, input and `[tabindex]`
gets a 2px `--focus-ring` outline on `:focus-visible`. Use `--hover-overlay`
for hover washes (`.nav-item`, `.incident-card` and `.row-hover` already exist
in `index.css`).

---

## 9. Checklist for a new page

- [ ] Page shell from §6; `useTheme()` + `<Header>`; route and nav entry added
- [ ] No raw hex or rgb in the component; tokens only (check by toggling dark mode)
- [ ] Ordinary cards are flat (hairline border, no shadow); only active alerts are elevated
- [ ] Status hues only for status; sand tint only for selected/active; chart hues only in charts
- [ ] One primary button; destructive actions confirmed
- [ ] Sentence case; caps only for severity/state words and table headers
- [ ] Plates, IDs and timestamps use `font-mono tabular-nums`; facts laid out as key–value, not dot-joined
- [ ] Loading skeleton, empty state with a hint, error text
- [ ] Hover on clickable rows/tiles only; transitions 150–250ms; nothing moves on hover
