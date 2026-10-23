import { useStore } from "../store";
import { Controls } from "./Controls";

export function Header() {
  const { channel, channels, clock } = useStore();
  const desc = channels.find((c) => c.id === channel)?.desc;
  const live = useStore((s) => (s.feeds[s.channel]?.threads ?? []).filter((t) => !t.ended_at).length);

  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-2.5">
      <div className="min-w-0">
        <div className="text-lg font-bold">
          <span className="mr-1 opacity-50">#</span>
          {channel}
        </div>
        <div className="truncate text-xs text-[var(--muted)]">
          {desc}
          {live > 0 && ` · ${live} live conversation${live > 1 ? "s" : ""}`}
        </div>
      </div>
      {clock && (
        <div className="flex items-center gap-3">
          {clock.occasion && (
            <span className="rounded-full bg-black/[0.06] px-3 py-1 text-xs font-semibold" title="What's special tonight">
              {clock.occasion}
            </span>
          )}
          <a
            href="/sales"
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]"
          >
            Sales ↗
          </a>
          <a
            href="/realism"
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]"
          >
            Realism ↗
          </a>
          <a
            href="/taproom"
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-[var(--border)] px-3 py-1 text-sm font-semibold hover:bg-black/[0.05]"
          >
            Floor ↗
          </a>
          <Controls />
        </div>
      )}
    </div>
  );
}
