import type { A2UIMessage } from "./a2ui/model";

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** When the message was sent (epoch ms). */
  at?: number;
  /** Assistant message that failed; `content` holds the error text and Retry resends the previous user message. */
  error?: boolean;
  /** A2UI messages for the generated interface shown with this reply. */
  ui?: A2UIMessage[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  /** Backend session ID, assigned by the first reply. */
  sessionId?: string;
}
