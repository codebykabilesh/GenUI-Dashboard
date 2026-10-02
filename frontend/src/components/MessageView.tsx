import GenUI from "../a2ui/GenUI";
import type { UserAction } from "../a2ui/model";
import type { Message } from "../types";
import { Icon } from "./Icons";

interface Props {
  message: Message;
  typing?: boolean;
  onRetry?: () => void;
  onAction?: (action: UserAction) => Promise<void>;
}

const time = (at?: number) =>
  at
    ? new Date(at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false })
    : "";

export default function MessageView({ message, typing, onRetry, onAction }: Props) {
  if (message.role === "user") {
    return (
      <div className="query">
        <span className="query-text">{message.content}</span>
        {message.at && <time className="query-time font-mono">{time(message.at)} IST</time>}
      </div>
    );
  }

  const hasUI = !!message.ui?.length;
  const waiting = typing && !message.content && !hasUI;
  return (
    <div className="answer">
      {hasUI && onAction && <GenUI messages={message.ui!} onAction={onAction} />}
      {waiting && (
        <div className="card loading" role="status" aria-label="Querying ANPR sources">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton-shimmer" style={{ opacity: 1 - i * 0.18, width: `${92 - i * 14}%` }} />
          ))}
        </div>
      )}
      {(message.content || (typing && !waiting)) && (
        <div className={`brief${message.error ? " is-error" : ""}`}>
          {message.content}
          {typing && <span className="cursor" />}
        </div>
      )}
      {message.error && onRetry && (
        <button className="btn btn-ghost" onClick={onRetry}>
          <Icon name="retry" size={14} /> Try again
        </button>
      )}
      {!typing && !message.error && message.content && (
        <div className="answer-tools">
          <button className="btn btn-ghost" onClick={() => navigator.clipboard?.writeText(message.content)}>
            <Icon name="copy" size={14} /> Copy summary
          </button>
        </div>
      )}
    </div>
  );
}
