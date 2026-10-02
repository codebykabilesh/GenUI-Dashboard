import type { Conversation } from "../types";
import { LogoIcon, NewChatIcon, SearchIcon, SidebarIcon } from "./Icons";

interface Props {
  open: boolean;
  conversations: Conversation[];
  activeId: string | null;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
}

export default function Sidebar({ open, conversations, activeId, onToggle, onNew, onSelect }: Props) {
  return (
    <aside className={`sidebar ${open ? "" : "collapsed"}`}>
      <div className="sidebar-inner">
        <div className="sidebar-top">
          <button className="icon-btn" onClick={onToggle} aria-label="Close sidebar"><SidebarIcon /></button>
          <button className="icon-btn" onClick={onNew} aria-label="New chat"><NewChatIcon /></button>
        </div>

        <nav className="sidebar-nav">
          <button className="nav-item" onClick={onNew}><NewChatIcon /> New chat</button>
          <button className="nav-item"><SearchIcon /> Search chats</button>
          <button className="nav-item"><LogoIcon size={20} /> Library</button>
        </nav>

        <div className="sidebar-history">
          <div className="history-label">Chats</div>
          {conversations.map((c) => (
            <button
              key={c.id}
              className={`history-item ${c.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(c.id)}
              title={c.title}
            >
              {c.title}
            </button>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="avatar">U</div>
          <div className="user-meta">
            <div className="user-name">User</div>
            <div className="user-plan">Free</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
