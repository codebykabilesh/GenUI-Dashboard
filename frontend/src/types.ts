export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
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
