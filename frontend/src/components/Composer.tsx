import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icons";

interface Props {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export default function Composer({ busy, onSend, onStop }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text);
    setValue("");
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          placeholder="Ask about a plate, a sighting, a junction or traffic patterns"
          aria-label="Query"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {busy ? (
          <button className="btn btn-secondary btn-tall" onClick={onStop}>
            <Icon name="stop" size={14} /> Stop
          </button>
        ) : (
          <button className="btn btn-primary btn-tall" onClick={submit} disabled={!value.trim()}>
            Run query <Icon name="arrow-right" size={14} />
          </button>
        )}
      </div>
      <p className="composer-note">Answers are generated from the connected ANPR sources. Verify before acting on them.</p>
    </div>
  );
}
