import type { UIResource } from "./api";

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** MCP App views (e.g. Prefab generative UI) to render under the text. */
  uiResources?: UIResource[];
  /** Assistant message that failed; `content` holds the error text and Retry resends the previous user message. */
  error?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  /** Backend session ID, assigned by the first reply. */
  sessionId?: string;
}
