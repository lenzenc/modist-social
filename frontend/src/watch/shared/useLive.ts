import { useMemo } from "react";
import { useStore } from "../../store";
import type { Msg, Thread } from "../../types";

export interface Live {
  thread: Thread;
  msgs: Msg[];
  /** Id of the newest line; bigger means more recent. */
  lastId: number;
  typing: string[];
}

const ORDER = { chat: 0, order: 1, staff: 2 } as const;

/** Every conversation going on right now, newest talk first. Orders and staff chatter come after real chats. */
export function useLive(): Live[] {
  const threads = useStore((s) => s.threads);
  const threadMsgs = useStore((s) => s.threadMsgs);
  const typing = useStore((s) => s.typing);
  return useMemo(
    () =>
      Object.values(threads)
        .filter((t) => !t.ended_at)
        .map((t) => {
          const msgs = threadMsgs[t.id] ?? [];
          return { thread: t, msgs, lastId: msgs.length ? msgs[msgs.length - 1].id : t.id, typing: typing[t.id] ?? [] };
        })
        .sort((a, b) => ORDER[a.thread.kind] - ORDER[b.thread.kind] || b.lastId - a.lastId),
    [threads, threadMsgs, typing],
  );
}

/** "Bar", "Table 7" or "Patio 2": where a conversation sits. */
export function placeOf(t: Thread): string {
  if (t.channel === "bar") return "Bar";
  if (t.channel === "ordering") return "Line";
  if (t.channel === "staff") return "Behind the bar";
  const n = t.table != null ? ` ${t.table + 1}` : "";
  return (t.channel === "patio" ? "Patio" : "Table") + n;
}
