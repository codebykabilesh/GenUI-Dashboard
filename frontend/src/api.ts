// Client for the GenUI FastAPI runtime. Schemas mirror app/schemas/api.py.

import type { A2UIMessage, UserAction } from "./a2ui/model";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export interface ChatResponse {
  session_id: string;
  reply: string;
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[];
  tool_results: { call_id: string; name: string; is_error: boolean; content: unknown }[];
  llm_provider: string;
  /** A2UI v0.8 messages describing the interface for this reply. */
  ui: A2UIMessage[];
}

export class ApiError extends Error {
  constructor(message: string, public code?: string, public status?: number) {
    super(message);
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    // runtime errors: {error: {code, message}}; FastAPI validation: {detail: ...}
    if (body?.error) return new ApiError(body.error.message, body.error.code, res.status);
    if (body?.detail) {
      return new ApiError(typeof body.detail === "string" ? body.detail : "Invalid request", undefined, res.status);
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(`Request failed (HTTP ${res.status})`, undefined, res.status);
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  /** The model is calling a tool; any text streamed so far was narration, not the answer. */
  onToolCall?: (name: string) => void;
  /** A tool result was rendered as an A2UI surface. */
  onA2UI?: (messages: A2UIMessage[]) => void;
}

/** POST /api/v1/chat/stream (Server-Sent Events). Resolves with the final response. */
export async function streamChat(
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(`Cannot reach the server at ${API_BASE_URL}. Is the backend running?`);
  }
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new ApiError("The server returned an empty stream.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: ChatResponse | null = null;

  const handle = (block: string) => {
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    const payload = JSON.parse(data);
    if (event === "delta") handlers.onDelta(payload.text);
    else if (event === "tool_call") handlers.onToolCall?.(payload.name);
    else if (event === "a2ui") handlers.onA2UI?.(payload.messages);
    else if (event === "done") done = payload as ChatResponse;
    else if (event === "error") throw new ApiError(payload.message, payload.code);
  };

  for (;;) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      handle(buffer.slice(0, sep));
      buffer = buffer.slice(sep + 2);
    }
  }
  if (!done) throw new ApiError("The connection closed before the reply finished.");
  return done;
}

/** Send an A2UI userAction; resolves with the A2UI messages that update the interface. */
export async function sendUIAction(sessionId: string | null, userAction: UserAction): Promise<A2UIMessage[]> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/ui/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, userAction }),
    });
  } catch {
    throw new ApiError(`Cannot reach the server at ${API_BASE_URL}. Is the backend running?`);
  }
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()).messages;
}

export interface RuntimeStatus {
  servers: { name: string; status: string; error: string | null; tool_count: number }[];
}

/** Connection state of the MCP data sources. */
export async function getStatus(): Promise<RuntimeStatus> {
  const res = await fetch(`${API_BASE_URL}/api/v1/servers`);
  if (!res.ok) throw await errorFrom(res);
  return res.json();
}
