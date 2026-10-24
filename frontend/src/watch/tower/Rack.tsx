import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../../store";
import { actionText } from "../shared/text";
import { placeOf, type Live } from "../shared/useLive";
import { stripOf, TOPIC_COLOR, TOPIC_WORD } from "./topics";

const names = (ids: string[], people: ReturnType<typeof useStore.getState>["people"]) =>
  ids.map((id) => people[id]?.short ?? "?").join(", ");

const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

function Strip({ l, on, onToggle }: { l: Live; on: boolean; onToggle: () => void }) {
  const people = useStore((s) => s.people);
  const t = l.thread;
  const kind = stripOf(t);
  const last = [...l.msgs].reverse().find((m) => m.kind === "speech");
  return (
    <li className={`strip strip-${kind}${on ? " is-on" : ""}`}>
      <button onClick={onToggle} aria-pressed={on} aria-label={`${on ? "Stop listening to" : "Listen to"} ${names(t.participants, people)}`}>
        <span className="strip-where">{placeOf(t)}</span>
        <span className="strip-body">
          <span className="strip-who">{names(t.participants.filter((id) => people[id]?.role !== "bartender" || t.kind !== "chat" || t.participants.length < 3), people)}</span>
          <span className="strip-last">{last ? clip(last.text, 74) : t.root_text}</span>
        </span>
        <span className="strip-meta">
          <span className="strip-topic" style={{ color: TOPIC_COLOR[t.topic ?? ""] ?? "#44566a" }}>{TOPIC_WORD[t.topic ?? "other"] ?? t.topic}</span>
          <span>{t.kind === "chat" ? t.vibe : ""}</span>
          <b>{l.typing.length ? "…" : t.count}</b>
        </span>
      </button>
    </li>
  );
}

function Lines({ l }: { l: Live }) {
  const people = useStore((s) => s.people);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [l.msgs.length, l.typing.length]);
  return (
    <div
      className="dock-lines"
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }}
    >
      {l.msgs.map((m) =>
        m.kind === "system" ? (
          <p key={m.id} className="dock-sys">{m.text}</p>
        ) : m.kind === "action" ? (
          <p key={m.id} className="dock-act">{actionText(m.text, people[m.speaker_id ?? ""]?.short)}</p>
        ) : (
          <p key={m.id}><b style={{ color: people[m.speaker_id ?? ""]?.color }}>{people[m.speaker_id ?? ""]?.short ?? "Modist"}</b> {m.text}</p>
        ),
      )}
      {l.typing.length > 0 && <p className="dock-typing">{names(l.typing, people)} typing…</p>}
      {!l.msgs.length && <p className="dock-sys">Nothing said yet.</p>}
    </div>
  );
}

export function Rack({ live, followed, ended, onToggle }: {
  live: Live[];
  followed: number[];
  ended: Set<number>;
  onToggle: (id: number) => void;
}) {
  const people = useStore((s) => s.people);
  const threadMsgs = useStore((s) => s.threadMsgs);
  const chats = live.filter((l) => l.thread.kind === "chat").length;
  const heated = live.filter((l) => stripOf(l.thread) === "heated").length;

  const panels = useMemo(
    () => followed.map((id) => live.find((l) => l.thread.id === id) ?? null),
    [followed, live],
  );

  return (
    <aside className="tw-right">
      <section className="tw-rack" aria-label="Live conversations">
        <h2>
          Live conversations <span>{chats} chatting{heated ? `, ${heated} heated` : ""}</span>
        </h2>
        <ul>
          {live.map((l) => <Strip key={l.thread.id} l={l} on={followed.includes(l.thread.id)} onToggle={() => onToggle(l.thread.id)} />)}
        </ul>
        {!live.length && <p className="tw-empty">No one is talking yet.</p>}
      </section>
      <section className="tw-dock" aria-label="Listening in">
        <h2>Listening in <span>{followed.length} of 3</span></h2>
        {!followed.length && <p className="tw-empty">Pick a strip to follow a conversation. Up to three at once.</p>}
        <div className="dock-panels">
          {followed.map((id, i) => {
            const l = panels[i];
            const msgs = threadMsgs[id] ?? [];
            const view: Live = l ?? { thread: { id, channel: "", kind: "chat", started_at: "", ended_at: "x", participants: [], root_text: "", count: msgs.length, last: null }, msgs, lastId: 0, typing: [] };
            const parts = l?.thread.participants ?? [...new Set(msgs.map((m) => m.speaker_id).filter(Boolean) as string[])];
            return (
              <article key={id} className={`dock-panel strip-${l ? stripOf(l.thread) : "staff"}`}>
                <header>
                  <span>{l ? placeOf(l.thread) : "Ended"}</span>
                  <b>{names(parts, people)}</b>
                  {ended.has(id) || !l ? <em>ended</em> : null}
                  <button onClick={() => onToggle(id)} aria-label="Stop listening">×</button>
                </header>
                <Lines l={view} />
              </article>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
