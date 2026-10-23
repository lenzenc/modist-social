import { useStore } from "../store";
import type { Msg } from "../types";
import { fmtTime } from "../util";
import { Avatar, Name } from "./Avatar";

export function MessageRow({ m, compact = false, grouped = false }: { m: Msg; compact?: boolean; grouped?: boolean }) {
  if (m.kind === "system") {
    return (
      <div className="bubble-in whitespace-pre-line px-5 py-1 text-[13px] text-[var(--muted)]">
        <span className="mr-2 text-[11px] opacity-70">{fmtTime(m.sim_ts)}</span>
        {m.text}
      </div>
    );
  }
  if (m.kind === "action") {
    return (
      <div className={`bubble-in px-5 py-1 text-[13px] italic ${m.speaker_id ? "" : "text-center text-[var(--muted)]"}`}>
        <span className="mr-2 text-[11px] not-italic opacity-70 text-[var(--muted)]">{fmtTime(m.sim_ts)}</span>
        {m.speaker_id ? <span className="text-[var(--muted)]">{m.text}</span> : m.text}
      </div>
    );
  }
  const size = compact ? 28 : 36;
  return (
    <div className={`bubble-in group flex gap-2.5 px-5 hover:bg-black/[0.03] ${grouped ? "py-0.5" : "pt-1.5 pb-0.5"}`}>
      <div style={{ width: size }} className="shrink-0">
        {!grouped && m.speaker_id && <Avatar id={m.speaker_id} size={size} />}
        {grouped && (
          <span className="hidden pt-1 text-[10px] text-[var(--muted)] group-hover:block">{fmtTime(m.sim_ts)}</span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        {!grouped && (
          <div className="flex items-baseline gap-2">
            <Name id={m.speaker_id} />
            <span className="text-xs text-[var(--muted)]">{fmtTime(m.sim_ts)}</span>
          </div>
        )}
        <div className={`${compact ? "text-[14px]" : ""} leading-snug break-words`}>{m.text}</div>
      </div>
    </div>
  );
}

export function TypingLine({ ids }: { ids: string[] }) {
  const people = useStore((s) => s.people);
  if (!ids.length) return null;
  const names = ids.map((i) => people[i]?.short).filter(Boolean);
  return (
    <div className="px-5 py-1 text-xs text-[var(--muted)]">
      {names.join(", ")} {names.length > 1 ? "are" : "is"} typing
      <span className="dots ml-1">
        <span>.</span>
        <span>.</span>
        <span>.</span>
      </span>
    </div>
  );
}
