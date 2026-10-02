import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import Composer from "./components/Composer";
import MessageView from "./components/MessageView";
import { ChevronDownIcon, SidebarIcon } from "./components/Icons";
import type { Conversation, Message } from "./types";

const uid = () => Math.random().toString(36).slice(2, 10);

const SEED: Conversation[] = [
  {
    id: "c1",
    title: "Explain React hooks",
    messages: [
      { id: "m1", role: "user", content: "Explain React hooks in simple terms." },
      {
        id: "m2",
        role: "assistant",
        content:
          "Hooks are functions that let you use state and other React features inside function components. useState stores values, useEffect runs side effects, and you can combine them into your own custom hooks.",
      },
    ],
  },
  { id: "c2", title: "Trip ideas for Japan", messages: [] },
  { id: "c3", title: "Write a cover letter", messages: [] },
];

const SUGGESTIONS = ["Summarize a long article", "Help me write an email", "Plan a weekend trip", "Explain a tricky concept"];

// API call to backend
const callBackend = async (q: string) => {
  const response = await fetch('http://localhost:5000/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message: q }),
  });
  
  if (!response.ok) {
    throw new Error('Failed to fetch from backend');
  }
  
  const data = await response.json();
  return data.response;
};

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>(SEED);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const hasMessages = !!active && active.messages.length > 0;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages]);

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
    },
    []
  );

  const patch = (id: string, fn: (m: Message[]) => Message[]) =>
    setConversations((cs) => cs.map((c) => (c.id === id ? { ...c, messages: fn(c.messages) } : c)));

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setBusy(false);
  };

  const send = async (text: string) => {
    const convId = activeId ?? uid();
    const userMsg: Message = { id: uid(), role: "user", content: text };
    if (!activeId) {
      const title = text.length > 32 ? text.slice(0, 32) + "…" : text;
      setConversations((cs) => [{ id: convId, title, messages: [userMsg] }, ...cs]);
      setActiveId(convId);
    } else {
      patch(convId, (m) => [...m, userMsg]);
    }

    const replyId = uid();
    setBusy(true);
    patch(convId, (m) => [...m, { id: replyId, role: "assistant", content: "" }]);

    try {
      const full = await callBackend(text);
      let i = 0;
      timer.current = window.setInterval(() => {
        i += 2;
        patch(convId, (m) => m.map((x) => (x.id === replyId ? { ...x, content: full.slice(0, i) } : x)));
        if (i >= full.length) stop();
      }, 20);
    } catch (error) {
      console.error('Error calling backend:', error);
      patch(convId, (m) =>
        m.map((x) =>
          x.id === replyId
            ? { ...x, content: "Sorry, I encountered an error. Please try again." }
            : x
        )
      );
      stop();
    }
  };

  const newChat = () => {
    stop();
    setActiveId(null);
  };

  const lastId = active?.messages[active.messages.length - 1]?.id;

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        conversations={conversations}
        activeId={activeId}
        onToggle={() => setSidebarOpen((o) => !o)}
        onNew={newChat}
        onSelect={(id) => {
          stop();
          setActiveId(id);
        }}
      />
      <main className="main">
        <header className="topbar">
          {!sidebarOpen && (
            <button className="icon-btn" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
              <SidebarIcon />
            </button>
          )}
          <button className="model-btn">
            ChatGPT <ChevronDownIcon />
          </button>
        </header>

        <div className="scroll">
          {hasMessages ? (
            <div className="thread">
              {active!.messages.map((m) => (
                <MessageView key={m.id} message={m} typing={busy && m.id === lastId && m.role === "assistant"} />
              ))}
              <div ref={bottom} />
            </div>
          ) : (
            <div className="empty">
              <h1>What can I help with?</h1>
            </div>
          )}
        </div>

        {!hasMessages && (
          <div className="chips">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        <Composer busy={busy} onSend={send} onStop={stop} />
      </main>
    </div>
  );
}
