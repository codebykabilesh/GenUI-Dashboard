import { useEffect, useRef, useState } from "react";
import { MicIcon, PlusIcon, SendIcon, StopIcon } from "./Icons";

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
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
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
        <button className="icon-btn" aria-label="Attach"><PlusIcon /></button>
        <textarea
          ref={ref}
          rows={1}
          value={value}
          placeholder="Ask anything"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="icon-btn" aria-label="Voice"><MicIcon /></button>
        {busy ? (
          <button className="send-btn" onClick={onStop} aria-label="Stop"><StopIcon /></button>
        ) : (
          <button className="send-btn" onClick={submit} disabled={!value.trim()} aria-label="Send"><SendIcon /></button>
        )}
      </div>
      <p className="disclaimer">ChatGPT can make mistakes. Check important info.</p>
    </div>
  );
}
