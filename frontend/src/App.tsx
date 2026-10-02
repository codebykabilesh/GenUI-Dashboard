import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import Composer from "./components/Composer";
import MessageView from "./components/MessageView";
import { ChevronDownIcon, SidebarIcon } from "./components/Icons";
import { ApiError, sendChat } from "./api";
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

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>(SEED);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const inflight = useRef(false);
  const conversationsRef = useRef(conversations);
  conversationsRef.current = conversations;
  const bottom = useRef<HTMLDivElement>(null);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const hasMessages = !!active && active.messages.length > 0;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages]);

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      abort.current?.abort();
    },
    []
  );

  const patch = (id: string, fn: (m: Message[]) => Message[]) =>
    setConversations((cs) => cs.map((c) => (c.id === id ? { ...c, messages: fn(c.messages) } : c)));

  const patchMsg = (convId: string, msgId: string, changes: Partial<Message>) =>
    patch(convId, (m) => m.map((x) => (x.id === msgId ? { ...x, ...changes } : x)));

  const stop = () => {
    abort.current?.abort();
    abort.current = null;
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    inflight.current = false;
    setBusy(false);
  };

  // Ask the backend for a reply and show it in the assistant message `replyId`.
  const request = async (convId: string, replyId: string, text: string) => {
    if (inflight.current) return; // one request at a time
    inflight.current = true;
    setBusy(true);
    patchMsg(convId, replyId, { content: "", error: false });

    const controller = new AbortController();
    abort.current = controller;
    const sessionId = conversationsRef.current.find((c) => c.id === convId)?.sessionId ?? null;

    try {
      let data;
      try {
        data = await sendChat(text, sessionId, controller.signal);
      } catch (e) {
        // Backend restarted and lost the session: start a fresh one and resend.
        if (e instanceof ApiError && e.code === "session_not_found") {
          data = await sendChat(text, null, controller.signal);
        } else {
          throw e;
        }
      }
      setConversations((cs) => cs.map((c) => (c.id === convId ? { ...c, sessionId: data.session_id } : c)));

      const full = data.reply || "(The assistant returned an empty response.)";
      let i = 0;
      timer.current = window.setInterval(() => {
        i += 2;
        patchMsg(convId, replyId, { content: full.slice(0, i) });
        if (i >= full.length) stop();
      }, 20);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // Stopped by the user: drop the placeholder if nothing was received.
        patch(convId, (m) => m.filter((x) => !(x.id === replyId && x.content === "")));
        return;
      }
      console.error("Error calling backend:", error);
      const message = error instanceof Error ? error.message : "Unknown error";
      patchMsg(convId, replyId, { content: message, error: true });
      stop();
    }
  };

  const send = async (text: string) => {
    if (inflight.current) return;
    const convId = activeId ?? uid();
    const userMsg: Message = { id: uid(), role: "user", content: text };
    const replyId = uid();
    const placeholder: Message = { id: replyId, role: "assistant", content: "" };
    if (!activeId) {
      const title = text.length > 32 ? text.slice(0, 32) + "…" : text;
      setConversations((cs) => [{ id: convId, title, messages: [userMsg, placeholder] }, ...cs]);
      setActiveId(convId);
    } else {
      patch(convId, (m) => [...m, userMsg, placeholder]);
    }
    await request(convId, replyId, text);
  };

  const retry = (replyId: string) => {
    if (!active || inflight.current) return;
    const idx = active.messages.findIndex((m) => m.id === replyId);
    const prompt = active.messages[idx - 1];
    if (idx < 1 || prompt.role !== "user") return;
    void request(active.id, replyId, prompt.content);
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
                <MessageView
                  key={m.id}
                  message={m}
                  typing={busy && m.id === lastId && m.role === "assistant"}
                  onRetry={m.error ? () => retry(m.id) : undefined}
                />
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
