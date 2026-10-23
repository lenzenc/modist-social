import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { familiarityLabel, fmtDayTime } from "../util";
import { Avatar } from "./Avatar";
import { MessageRow, TypingLine } from "./MessageRow";

export function RightPane() {
  const openThread = useStore((s) => s.openThread);
  const profileId = useStore((s) => s.profileId);
  if (openThread != null) return <ThreadPane id={openThread} />;
  if (profileId) return <ProfilePane />;
  return null;
}

function Header({ title, sub, onClose }: { title: string; sub?: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
      <div className="min-w-0">
        <div className="truncate font-bold">{title}</div>
        {sub && <div className="truncate text-xs text-[var(--muted)]">{sub}</div>}
      </div>
      <button onClick={onClose} className="cursor-pointer rounded px-2 text-xl text-[var(--muted)] hover:bg-black/10">
        ×
      </button>
    </div>
  );
}

function ThreadPane({ id }: { id: number }) {
  const msgs = useStore((s) => s.threadMsgs[id]) ?? [];
  const typing = useStore((s) => s.typing[id]) ?? [];
  const close = useStore((s) => s.openThreadPane);
  const thread = useStore((s) => s.threads[id] ?? Object.values(s.feeds).flatMap((f) => f.threads).find((t) => t.id === id));
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [msgs.length, typing.length]);

  return (
    <aside className="flex w-[26rem] shrink-0 flex-col border-l border-[var(--border)]">
      <Header title="Thread" sub={thread?.root_text} onClose={() => close(null)} />
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
    </aside>
  );
}

const REASON: Record<string, string> = {
  unwind: "unwind after the day",
  catch_up: "catch up with friends",
  solo: "have some time alone",
  game: "watch the game",
  date: "have a date",
  work: "work",
};
const moodWord = (m: number) => (m >= 0.4 ? "good" : m >= 0.1 ? "fine" : m > -0.25 ? "so-so" : m > -0.5 ? "irritable" : "down");
const BOND_ICON: Record<string, string> = {
  friends: "🤝", close_friends: "💛", rivals: "⚔️", crush: "💘", couple: "❤️", falling_out: "💔", ex: "🥀", mentor: "🎓",
};
const bar = (n: number) => `${Math.round(n * 100)}%`;

function ProfilePane() {
  const p = useStore((s) => s.profile);
  const close = useStore((s) => s.openProfile);
  const open = useStore((s) => s.openProfile);
  if (!p)
    return (
      <aside className="w-[26rem] shrink-0 border-l border-[var(--border)]">
        <Header title="Loading…" onClose={() => close(null)} />
      </aside>
    );
  const d = p.persona;
  return (
    <aside className="flex w-[26rem] shrink-0 flex-col border-l border-[var(--border)]">
      <Header title="Profile" onClose={() => close(null)} />
      <div className="scroll flex-1 px-4 py-4">
        <div className="flex items-center gap-3">
          <Avatar id={p.id} size={64} />
          <div>
            <div className="text-xl font-bold">{p.display}</div>
            <div className="text-sm text-[var(--muted)]">
              {p.pronouns} · {d.age} · {d.job}
            </div>
            <div className="mt-1 text-xs">
              {p.present ? (
                <span className="text-[var(--ok)]">● at the {p.location}</span>
              ) : (
                <span className="text-[var(--muted)]">○ not in the taproom</span>
              )}
            </div>
          </div>
        </div>

        {p.shift && (
          <Section title="This shift">
            <dl className="space-y-1 text-sm">
              <Row k="Mood" v={moodWord(p.shift.mood)} />
              <Row k="Energy" v={p.shift.energy} />
              {p.shift.rough && <Row k="Rough night" v={p.shift.rough} />}
              <Row k="Poured" v={`${p.shift.served} drinks${p.shift.wrong ? `, ${p.shift.wrong} wrong` : ""}${p.shift.spills ? `, ${p.shift.spills} spilled` : ""}`} />
              {p.shift.peeve && <Row k="Pet peeve" v={p.shift.peeve} />}
              {p.shift.gripe && <Row k="Sore at" v={p.shift.gripe} />}
            </dl>
          </Section>
        )}

        {p.state && (
          <Section title="Right now">
            <dl className="space-y-1 text-sm">
              <Row k="Here to" v={REASON[p.state.reason] ?? p.state.reason} />
              <Row k="Mood" v={moodWord(p.state.mood)} />
              <Row k="Buzz" v={p.state.drinks ? `${p.state.drinks} drink${p.state.drinks > 1 ? "s" : ""}, ${p.state.tier}${p.state.cut_off ? ", cut off" : p.state.on_water ? ", on water" : ""}` : "sober"} />
              {p.state.slops.length > 0 && <Row k="Tonight" v={p.state.slops.join(", ")} />}
              {p.state.cap > 0 && <Row k="Wallet" v={`$${(p.state.spent / 100).toFixed(0)} of about $${(p.state.cap / 100).toFixed(0)} tonight`} />}
              <Row k="Social energy" v={bar(p.state.battery)} />
              {p.state.need && <Row k="Needs to" v={p.state.need} />}
            </dl>
            {p.state.thought && <div className="mt-2 text-sm italic text-[var(--muted)]">Thinking: “{p.state.thought}”</div>}
          </Section>
        )}

        <Section title="About">
          <dl className="space-y-1 text-sm">
            <Row k="Personality" v={d.traits.join(", ")} />
            <Row k="Politics" v={d.politics} />
            <Row k="Usually" v={d.drink} />
            {p.taste && p.taste.favorites.length > 0 && <Row k="Favorites" v={p.taste.favorites.join(", ")} />}
            {p.taste && p.taste.tired_of.length > 0 && <Row k="Tired of" v={p.taste.tired_of.join(", ")} />}
            {p.taste && <Row k="Spends" v={{ tight: "carefully", ok: "evenly", flush: "freely" }[p.taste.budget]} />}
            {p.taste && Object.keys(p.taste.owes).length > 0 && (
              <Row k="Rounds" v={Object.entries(p.taste.owes).map(([who, n]) => (n > 0 ? `owes ${who}` : `${who} owes`)).join(", ")} />
            )}
            {p.present && p.drink && <Row k="Drinking now" v={p.drink} />}
            <Row k="Into" v={d.interests.join(", ")} />
            <Row k="Quirk" v={d.quirk} />
            {d.life && <Row k="Life" v={d.life} />}
            {p.lately && <Row k="Lately" v={p.lately} />}
            {p.life?.length > 0 && (
              <div className="flex gap-2">
                <dt className="w-24 shrink-0 text-[var(--muted)]">Off-screen</dt>
                <dd className="space-y-0.5">
                  {p.life.map((e, i) => (
                    <div key={i} className={e.active ? "" : "text-[var(--muted)]"}>
                      {e.text}
                      <span className="text-[var(--muted)]"> · {fmtDayTime(e.started_at)}</span>
                    </div>
                  ))}
                </dd>
              </div>
            )}
            {d.takes && d.takes.length > 0 && <Row k="Believes" v={d.takes.join("; ")} />}
            {p.visits > 0 && <Row k="Visits" v={String(p.visits)} />}
            {d.joined && <Row k="First seen" v={fmtDayTime(d.joined)} />}
          </dl>
        </Section>

        {p.bond_changes?.length > 0 && (
          <Section title="Recent changes">
            {p.bond_changes.map((c, i) => (
              <div key={i} className="mb-1 text-sm">
                <span className="font-semibold">{c.with}</span>: {c.from.replace("_", " ")} → {c.to.replace("_", " ")}
                {c.why ? <span className="text-[var(--muted)]"> ({c.why})</span> : null}
              </div>
            ))}
          </Section>
        )}

        <Section title={`Relationships (${p.relationships.length})`}>
          {p.relationships.length === 0 && <div className="text-sm text-[var(--muted)]">Hasn't met anyone yet.</div>}
          {p.relationships.map((r) => (
            <button
              key={r.id}
              onClick={() => open(r.id)}
              className="mb-1.5 block w-full cursor-pointer rounded-md px-2 py-1.5 text-left hover:bg-black/[0.05]"
            >
              <div className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: r.color }} />
                <span className="font-semibold">{r.name}</span>
                <span className="text-xs text-[var(--muted)]">
                  {BOND_ICON[r.bond] ? `${BOND_ICON[r.bond]} ` : ""}
                  {BOND_ICON[r.bond] ? r.bond.replace("_", " ") : r.kind !== "stranger" ? r.kind : familiarityLabel(r.familiarity)}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Bar value={r.familiarity} max={100} color="var(--accent)" label="familiarity" />
                <Bar value={r.affinity + 100} max={200} color={r.affinity >= 0 ? "var(--ok)" : "#cd2553"} label="affinity" />
              </div>
              {r.notes && <div className="mt-1 text-xs text-[var(--muted)]">{r.notes}</div>}
            </button>
          ))}
        </Section>

        <Section title="Remembers">
          {p.memories.length === 0 && <div className="text-sm text-[var(--muted)]">No memories yet.</div>}
          {p.memories.map((m, i) => (
            <div key={i} className="mb-2 text-sm">
              <div>{m.text}</div>
              <div className="text-xs text-[var(--muted)]">
                {m.kind === "reflection" && "💭 reflection · "}
                {m.kind === "followup" && "↪ to ask next time · "}
                {m.source && (
                  <span title={`${m.accuracy}% accurate after ${m.hops} retelling${m.hops === 1 ? "" : "s"}`}>
                    🗣 from {m.source}, {m.confidence! >= 80 ? "pretty sure" : m.confidence! >= 50 ? "fairly sure" : "not sure"} ·{" "}
                  </span>
                )}
                {fmtDayTime(m.sim_ts)}
                {m.about.length > 0 && ` · about ${m.about.join(", ")}`}
              </div>
            </div>
          ))}
        </Section>
      </div>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-2 text-xs font-bold tracking-wide text-[var(--muted)] uppercase">{title}</h3>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-[var(--muted)]">{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}

function Bar({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  return (
    <div className="flex-1" title={`${label}: ${Math.round(value)}`}>
      <div className="h-1.5 rounded-full bg-black/10">
        <div className="h-1.5 rounded-full" style={{ width: `${(value / max) * 100}%`, background: color }} />
      </div>
    </div>
  );
}
