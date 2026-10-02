import { useMemo } from "react";
import "./genui.css";
import Surface from "./Surface";
import { reduceMessages, type A2UIMessage, type UserAction } from "./model";

interface Props {
  messages: A2UIMessage[];
  onAction: (action: UserAction) => Promise<void>;
}

/** Renders every A2UI surface carried by one assistant reply. */
export default function GenUI({ messages, onAction }: Props) {
  const surfaces = useMemo(() => reduceMessages(messages), [messages]);
  if (surfaces.length === 0) return null;
  return (
    <div className="gu">
      {surfaces.map((s) => (
        // version in the key: a server re-render resets the surface's local input state
        <Surface key={`${s.id}:${s.version}`} surface={s} onAction={onAction} />
      ))}
    </div>
  );
}
