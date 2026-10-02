import { useState } from "react";
import { Icon } from "./Icons";

const QUICK_STARTS = [
  { icon: "clock", title: "Hourly traffic", prompt: "Show hourly traffic across all junctions on 30 September 2026" },
  { icon: "compare", title: "Compare junctions", prompt: "Compare JN-001, JN-003, JN-007 and JN-014 on 30 September 2026" },
  { icon: "chart-pie", title: "Vehicle mix", prompt: "What was the vehicle type mix at JN-014 on 1 October 2026?" },
  { icon: "camera", title: "Sighting lookup", prompt: "Show sighting DET-0004 and its evidence" },
];

interface Props {
  disabled: boolean;
  onRun: (prompt: string) => void;
}

export default function EmptyState({ disabled, onRun }: Props) {
  const [plate, setPlate] = useState("");
  const clean = plate.replace(/[^a-z0-9]/gi, "").toUpperCase();
  const search = () => {
    if (clean.length >= 4 && !disabled) onRun(`Show the sighting history for ${clean}`);
  };

  return (
    <div className="start">
      <section className="card start-card">
        <div className="card-head">
          <div>
            <h2 className="card-title">Trace a vehicle</h2>
            <p className="card-subtitle">Search every camera sighting for a registration number.</p>
          </div>
        </div>
        <form
          className="trace"
          onSubmit={(e) => {
            e.preventDefault();
            search();
          }}
        >
          <label className="field">
            <span className="field-label">Registration number</span>
            <input
              className="input input-plate font-mono"
              value={plate}
              onChange={(e) => setPlate(e.target.value.toUpperCase())}
              placeholder="KA 01 AB 1234"
              maxLength={14}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <button className="btn btn-secondary btn-tall" type="submit" disabled={clean.length < 4 || disabled}>
            <Icon name="scan" size={14} /> Trace vehicle
          </button>
        </form>
      </section>

      <section className="start-quick" aria-label="Quick starts">
        {QUICK_STARTS.map((q) => (
          <button key={q.title} className="tile row-hover" onClick={() => onRun(q.prompt)} disabled={disabled}>
            <span className="tile-icon"><Icon name={q.icon} size={16} /></span>
            <span className="tile-title">{q.title}</span>
            <span className="tile-text">{q.prompt}</span>
          </button>
        ))}
      </section>
    </div>
  );
}
