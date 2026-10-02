import { useEffect, useRef, useState } from "react";
import Header from "./components/Header";
import CaseList from "./components/CaseList";
import Composer from "./components/Composer";
import MessageView from "./components/MessageView";
import EmptyState from "./components/EmptyState";
import { useTheme } from "./hooks/useTheme";
import { ApiError, sendUIAction, streamChat } from "./api";
import type { A2UIMessage, UserAction } from "./a2ui/model";
import type { Conversation, Message } from "./types";

const uid = () => Math.random().toString(36).slice(2, 10);

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(false); // drawer state on narrow screens
  const [busy, setBusy] = useState(false);
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
      abort.current?.abort();
    },
    []
  );

  const patch = (id: string, fn: (m: Message[]) => Message[]) =>
    setConversations((cs) => cs.map((c) => (c.id === id ? { ...c, messages: fn(c.messages) } : c)));

  const patchMsg = (convId: string, msgId: string, changes: Partial<Message>) =>
    patch(convId, (m) => m.map((x) => (x.id === msgId ? { ...x, ...changes } : x)));

  const appendUI = (convId: string, msgId: string, msgs: A2UIMessage[]) =>
    patch(convId, (m) => m.map((x) => (x.id === msgId ? { ...x, ui: [...(x.ui ?? []), ...msgs] } : x)));

  // A2UI userAction from a surface: the runtime runs the mapped tool and returns surface updates.
  const handleAction = (convId: string, msgId: string) => async (action: UserAction) => {
    const sessionId = conversationsRef.current.find((c) => c.id === convId)?.sessionId ?? null;
    appendUI(convId, msgId, await sendUIAction(sessionId, action));
  };

  const stop = () => {
    abort.current?.abort();
    abort.current = null;
    inflight.current = false;
    setBusy(false);
  };

  // Ask the backend for a reply and show it in the assistant message `replyId`.
  const request = async (convId: string, replyId: string, text: string) => {
    if (inflight.current) return; // one request at a time
    inflight.current = true;
    setBusy(true);
    patchMsg(convId, replyId, { content: "", error: false, ui: [] });

    const controller = new AbortController();
    abort.current = controller;
    const sessionId = conversationsRef.current.find((c) => c.id === convId)?.sessionId ?? null;

    // Text streams in as it is generated. Text that precedes a tool call is narration, so drop it.
    let shown = "";
    const handlers = {
      onDelta: (t: string) => {
        shown += t;
        patchMsg(convId, replyId, { content: shown });
      },
      onToolCall: () => {
        shown = "";
        patchMsg(convId, replyId, { content: "" });
      },
      onA2UI: (msgs: A2UIMessage[]) => appendUI(convId, replyId, msgs),
    };

    try {
      let data;
      try {
        data = await streamChat(text, sessionId, handlers, controller.signal);
      } catch (e) {
        // Backend restarted and lost the session: start a fresh one and resend.
        if (e instanceof ApiError && e.code === "session_not_found") {
          shown = "";
          data = await streamChat(text, null, handlers, controller.signal);
        } else {
          throw e;
        }
      }
      setConversations((cs) => cs.map((c) => (c.id === convId ? { ...c, sessionId: data.session_id } : c)));
      patchMsg(convId, replyId, {
        content: data.reply || (data.ui?.length ? "" : "(The assistant returned an empty response.)"),
        ui: data.ui ?? [],
      });
      stop();
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
    const userMsg: Message = { id: uid(), role: "user", content: text, at: Date.now() };
    const replyId = uid();
    const placeholder: Message = { id: replyId, role: "assistant", content: "" };
    if (!activeId) {
      const title = text.length > 40 ? text.slice(0, 40) + "…" : text;
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
      <Header theme={theme} onToggleTheme={toggleTheme} onToggleCases={() => setRailOpen(true)} />
      <div className="app-body">
        <CaseList
          open={railOpen}
          conversations={conversations}
          activeId={activeId}
          onClose={() => setRailOpen(false)}
          onNew={() => {
            newChat();
            setRailOpen(false);
          }}
          onSelect={(id) => {
            stop();
            setActiveId(id);
            setRailOpen(false);
          }}
        />
        <main className="main">
          <div className="topbar">
            <h1 className="topbar-title">{active?.title ?? "New investigation"}</h1>
          </div>
          <div className="scroll">
            {hasMessages ? (
              <div className="thread">
                {active!.messages.map((m) => (
                  <MessageView
                    key={m.id}
                    message={m}
                    typing={busy && m.id === lastId && m.role === "assistant"}
                    onRetry={m.error ? () => retry(m.id) : undefined}
                    onAction={handleAction(active!.id, m.id)}
                  />
                ))}
                <div ref={bottom} />
              </div>
            ) : (
              <EmptyState disabled={busy} onRun={send} />
            )}
          </div>
          <Composer busy={busy} onSend={send} onStop={stop} />
        </main>
      </div>
    </div>
  );
}
