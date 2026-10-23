import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../store";
import type { Msg, Thread } from "../types";
import { fmtTime } from "../util";
import { Avatar } from "./Avatar";
import { MessageRow, TypingLine } from "./MessageRow";

type Item = { key: string; ts: number; thread?: Thread; msg?: Msg };

const PREVIEW = 3;

export function Feed() {
  const channel = useStore((s) => s.channel);
  const feed = useStore((s) => s.feeds[s.channel]);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const items = useMemo<Item[]>(() => {
    if (!feed) return [];
    const out: Item[] = [
      ...feed.threads.map((t) => ({ key: `t${t.id}`, ts: +new Date(t.started_at), thread: t })),
      ...feed.messages.map((m) => ({ key: `m${m.id}`, ts: +new Date(m.sim_ts), msg: m })),
    ];
    return out.sort((a, b) => a.ts - b.ts || a.key.localeCompare(b.key));
  }, [feed]);

  const lastKey = items.at(-1)?.key;
  const total = useStore((s) => (feed ? feed.threads.reduce((n, t) => n + (s.threadMsgs[t.id]?.length ?? 0), 0) : 0));

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lastKey, total, channel]);

  return (
    <div
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}
      className="scroll flex-1 py-3"
    >
      {!items.length && (
        <div className="px-5 py-10 text-center text-[var(--muted)]">
          Nothing in #{channel} yet. Give it a moment: the taproom opens at 3pm.
        </div>
      )}
      {items.map((it) =>
        it.thread ? <ThreadCard key={it.key} t={it.thread} /> : <MessageRow key={it.key} m={it.msg!} />,
      )}
    </div>
  );
}

export function ThreadCard({ t }: { t: Thread }) {
  const openThreadPane = useStore((s) => s.openThreadPane);
  const open = useStore((s) => s.openThread === t.id);
  const msgs = useStore((s) => s.threadMsgs[t.id]);
  const typing = useStore((s) => s.typing[t.id]);
  const people = useStore((s) => s.people);
  const live = !t.ended_at;
  const speech = (msgs ?? []).filter((m) => m.kind === "speech");
  const shown = speech.slice(-PREVIEW);
  const hidden = Math.max(0, t.count - shown.length);

  return (
    <div className={`mx-3 my-2 rounded-lg border ${open ? "border-[var(--accent)]" : "border-[var(--border)]"} bg-[var(--panel)]`}>
      <button
        onClick={() => openThreadPane(t.id)}
        className="flex w-full cursor-pointer items-center gap-3 rounded-t-lg px-4 py-2 text-left hover:bg-black/[0.04]"
      >
        <div className="flex -space-x-2">
          {t.participants.slice(0, 4).map((id) => (
            <Avatar key={id} id={id} size={26} ring />
          ))}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{t.root_text}</div>
          <div className="text-xs text-[var(--muted)]">
            {fmtTime(t.started_at)} · {t.count} {t.count === 1 ? "reply" : "replies"}
            {t.kind === "order" && " · ordering"}
          </div>
        </div>
        {live ? (
          <span className="flex items-center gap-1 rounded-full bg-[var(--ok)]/15 px-2 py-0.5 text-xs font-semibold text-[var(--ok)]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--ok)]" /> live
          </span>
        ) : (
          <span className="text-xs text-[var(--muted)]">ended {t.ended_at && fmtTime(t.ended_at)}</span>
        )}
      </button>

      {shown.length > 0 && (
        <div className="border-t border-[var(--border)] py-1">
          {hidden > 0 && (
            <button
              onClick={() => openThreadPane(t.id)}
              className="cursor-pointer px-5 py-0.5 text-xs font-semibold text-[var(--accent)] hover:underline"
            >
              View {hidden} earlier {hidden === 1 ? "reply" : "replies"}
            </button>
          )}
          {shown.map((m, i) => (
            <MessageRow key={m.id} m={m} compact grouped={i > 0 && shown[i - 1].speaker_id === m.speaker_id} />
          ))}
          {live && <TypingLine ids={(typing ?? []).filter((i) => people[i])} />}
        </div>
      )}
      {shown.length === 0 && live && (typing?.length ?? 0) > 0 && (
        <div className="border-t border-[var(--border)]">
          <TypingLine ids={typing ?? []} />
        </div>
      )}
    </div>
  );
}
