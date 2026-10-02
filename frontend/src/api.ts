// Client for the GenUI FastAPI runtime. Schemas mirror app/schemas/api.py.

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export interface ChatResponse {
  session_id: string;
  reply: string;
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[];
  tool_results: { call_id: string; name: string; is_error: boolean; content: unknown }[];
  llm_provider: string;
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

export async function sendChat(message: string, sessionId: string | null, signal?: AbortSignal): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(`Cannot reach the server at ${API_BASE_URL}. Is the backend running?`);
  }
  if (!res.ok) throw await errorFrom(res);
  return res.json();
}
