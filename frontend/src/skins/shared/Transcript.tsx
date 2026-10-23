import { useEffect, useRef } from "react";
import { MessageRow, TypingLine } from "../../components/MessageRow";
import { useStore } from "../../store";
import { threadPlace } from "./useRoster";

/** One conversation, full height, sticking to the bottom as lines arrive. Fits any container the skin puts it in. */
export function Transcript({ id, eyebrow = true }: { id: number; eyebrow?: boolean }) {
  const msgs = useStore((s) => s.threadMsgs[id]) ?? [];
  const typing = useStore((s) => s.typing[id]) ?? [];
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const close = useStore((s) => s.openThreadPane);
  const thread = useStore((s) => s.threads[id] ?? Object.values(s.feeds).flatMap((f) => f.threads).find((t) => t.id === id));
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [msgs.length, typing.length]);
  const names = thread?.participants.map((p) => people[p]?.short).filter(Boolean).join(", ");
  return (
    <>
      <div className="flex items-start justify-between border-b border-[var(--border)] px-4 py-3">
        <div className="min-w-0">
          {eyebrow && (
            <div className="font-mono text-[10px] tracking-[0.18em] text-[var(--accent)] uppercase">
              {thread && !thread.ended_at ? "● listening" : "ended"} · {thread ? threadPlace(thread, presence) : ""}
            </div>
          )}
          <div className="truncate text-[15px] font-semibold">{thread?.root_text}</div>
          <div className="truncate text-[11px] text-[var(--muted)]">{names}</div>
        </div>
        <button onClick={() => close(null)} className="cursor-pointer rounded px-2 text-xl text-[var(--muted)] hover:bg-white/10">
          ×
        </button>
      </div>
      <div
        ref={ref}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="scroll flex-1 py-2"
      >
        {msgs.map((m, i) => (
          <MessageRow key={m.id} m={m} grouped={i > 0 && msgs[i - 1].kind === "speech" && msgs[i - 1].speaker_id === m.speaker_id} />
        ))}
        <TypingLine ids={typing} />
      </div>
    </>
  );
}
