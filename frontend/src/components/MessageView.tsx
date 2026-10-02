import type { Message } from "../types";
import { CopyIcon, LogoIcon, RefreshIcon, ThumbDownIcon, ThumbUpIcon } from "./Icons";

interface Props {
  message: Message;
  typing?: boolean;
  onRetry?: () => void;
}

export default function MessageView({ message, typing, onRetry }: Props) {
  if (message.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble">{message.content}</div>
      </div>
    );
  }
  return (
    <div className="msg assistant">
      <div className="assistant-avatar"><LogoIcon /></div>
      <div className="assistant-body">
        <div className={`assistant-text${message.error ? " error" : ""}`}>
          {message.content}
          {typing && <span className="cursor" />}
        </div>
        {message.error && onRetry && (
          <button className="retry-btn" onClick={onRetry}><RefreshIcon /> Retry</button>
        )}
        {!typing && !message.error && (
          <div className="actions">
            <button className="icon-btn sm" aria-label="Copy" onClick={() => navigator.clipboard?.writeText(message.content)}><CopyIcon /></button>
            <button className="icon-btn sm" aria-label="Good response"><ThumbUpIcon /></button>
            <button className="icon-btn sm" aria-label="Bad response"><ThumbDownIcon /></button>
            <button className="icon-btn sm" aria-label="Regenerate"><RefreshIcon /></button>
          </div>
        )}
      </div>
    </div>
  );
}
