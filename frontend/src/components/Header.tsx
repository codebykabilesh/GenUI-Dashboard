import { useEffect, useState } from "react";
import { getStatus, type RuntimeStatus } from "../api";
import type { Theme } from "../hooks/useTheme";
import { Icon } from "./Icons";

const SOURCE_NAMES: Record<string, string> = { investigation: "Investigation", analytics: "Analytics" };

function useClock(): string {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

function useSources() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () =>
      getStatus()
        .then((s) => {
          if (alive) {
            setStatus(s);
            setOffline(false);
          }
        })
        .catch(() => alive && setOffline(true));
    load();
    const t = window.setInterval(load, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return { status, offline };
}

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
  onToggleCases: () => void;
}

/** Floating black-glass masthead. Its colours stay fixed in both themes. */
export default function Header({ theme, onToggleTheme, onToggleCases }: Props) {
  const clock = useClock();
  const { status, offline } = useSources();
  return (
    <header className="masthead">
      <button className="masthead-icon cases-toggle" onClick={onToggleCases} aria-label="Show investigations">
        <Icon name="panel-left" size={18} />
      </button>
      <div className="masthead-brand">
        <span className="masthead-mark"><Icon name="shield" size={18} /></span>
        <span className="masthead-name">
          <strong>Chennai City ANPR</strong>
          <span>Intelligence Platform</span>
        </span>
      </div>

      <div className="masthead-sources" aria-label="Data sources">
        {offline ? (
          <span className="source is-down"><i />Runtime unreachable</span>
        ) : (
          status?.servers.map((s) => (
            <span
              key={s.name}
              className={`source${s.status === "connected" ? "" : " is-down"}`}
              title={s.status === "connected" ? `${s.tool_count} tools available` : s.error ?? s.status}
            >
              <i />
              {SOURCE_NAMES[s.name] ?? s.name}
            </span>
          ))
        )}
      </div>

      <time className="masthead-clock" aria-label="Indian Standard Time">
        {clock} <span>IST</span>
      </time>
      <button
        className="masthead-icon"
        onClick={onToggleTheme}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        title={theme === "dark" ? "Light theme" : "Dark theme"}
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
      </button>
    </header>
  );
}
