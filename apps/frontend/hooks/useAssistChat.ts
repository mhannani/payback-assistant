"use client";

import { useCallback, useState } from "react";
import type { AssistResponse, Msg } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

let _id = 0;
const nextId = () => `m${++_id}`;

/** Chat state over the PAYBACK /assist API.
 *
 * A plain request/response transport (no streaming/sessions). The agent's clarify flow is multi-turn:
 * a `clarify` response carries a `thread_id`; the next user message is sent to `/assist/resume` with
 * that id (the agent resumes the paused graph), and the thread is cleared once it resolves. This is
 * why we hold `threadId` — it replaces a session token. */
export function useAssistChat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const push = useCallback((msg: Msg) => setMessages((prev) => [...prev, msg]), []);

  const send = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || pending) return;

      push({ id: nextId(), role: "user", text: query });
      setPending(true);

      // Resume the paused clarify thread if one is open; otherwise start a fresh assist turn.
      const url = threadId ? `${API_BASE}/assist/resume` : `${API_BASE}/assist`;
      const body = threadId ? { thread_id: threadId, answer: query } : { query };

      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        // A resume against an expired/unknown thread → recover gracefully and drop the thread.
        if (res.status === 404 && threadId) {
          setThreadId(null);
          push({
            id: nextId(),
            role: "assistant",
            kind: "text",
            text: "Das Gespräch ist abgelaufen — bitte stellen Sie Ihre Frage erneut.",
          });
          return;
        }
        if (!res.ok) throw new Error(`assist ${res.status}`);

        const data = (await res.json()) as AssistResponse;
        if (data.type === "products") {
          setThreadId(null);
          push({ id: nextId(), role: "assistant", kind: "products", items: data.items });
          if (data.items.length === 0) {
            push({
              id: nextId(),
              role: "assistant",
              kind: "text",
              text: "Ich konnte nichts Passendes finden — bitte anders beschreiben.",
            });
          }
        } else if (data.type === "clarify") {
          setThreadId(data.thread_id);
          push({ id: nextId(), role: "assistant", kind: "clarify", question: data.question });
        } else {
          setThreadId(null);
          push({
            id: nextId(),
            role: "assistant",
            kind: "route",
            message: data.message,
            deeplink: data.deeplink,
            partnerName: data.partner_name,
          });
        }
      } catch {
        push({
          id: nextId(),
          role: "assistant",
          kind: "text",
          text: "Es gab ein Problem beim Erreichen des Assistenten. Bitte erneut versuchen.",
        });
      } finally {
        setPending(false);
      }
    },
    [pending, threadId, push],
  );

  return { messages, pending, send };
}
