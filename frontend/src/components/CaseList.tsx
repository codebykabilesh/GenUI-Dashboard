import type { Conversation } from "../types";
import { Icon } from "./Icons";

interface Props {
  open: boolean;
  conversations: Conversation[];
  activeId: string | null;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
}

export default function CaseList({ open, conversations, activeId, onClose, onNew, onSelect }: Props) {
  return (
    <>
      <aside className={`cases${open ? " is-open" : ""}`} aria-label="Investigations">
        <div className="cases-head">
          <span className="cases-title">Investigations</span>
          <button className="btn btn-secondary" onClick={onNew}>
            <Icon name="plus" size={14} /> New
          </button>
        </div>
        <nav className="cases-list">
          {conversations.length === 0 ? (
            <div className="empty-note">
              <p className="empty-note-title">No investigations yet</p>
              <p className="empty-note-hint">Trace a plate or ask a question to start one.</p>
            </div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                className={`case row-hover${c.id === activeId ? " is-selected" : ""}`}
                onClick={() => onSelect(c.id)}
                title={c.title}
                aria-current={c.id === activeId ? "page" : undefined}
              >
                <Icon name="folder-open" size={14} />
                <span>{c.title}</span>
              </button>
            ))
          )}
        </nav>
      </aside>
      {open && <div className="cases-scrim" onClick={onClose} aria-hidden="true" />}
    </>
  );
}
