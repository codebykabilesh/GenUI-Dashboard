// Icons: lucide-react only (UI_THEME.md). Kebab-case names map to lucide components.
import {
  ArrowRight, Camera, ChartColumn, ChartPie, Clock, Copy, FolderOpen, GitCompareArrows, Moon,
  PanelLeft, Plus, RotateCcw, ScanLine, ShieldCheck, Square, Sun, type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  "arrow-right": ArrowRight,
  camera: Camera,
  "chart-column": ChartColumn,
  "chart-pie": ChartPie,
  clock: Clock,
  copy: Copy,
  "folder-open": FolderOpen,
  compare: GitCompareArrows,
  moon: Moon,
  "panel-left": PanelLeft,
  plus: Plus,
  retry: RotateCcw,
  scan: ScanLine,
  shield: ShieldCheck,
  stop: Square,
  sun: Sun,
};

export function Icon({ name, size = 20 }: { name: keyof typeof ICONS | string; size?: number }) {
  const Component = ICONS[name];
  return Component ? <Component size={size} strokeWidth={1.75} aria-hidden="true" /> : null;
}
