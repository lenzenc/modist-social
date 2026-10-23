import "@fontsource-variable/literata";
import "@fontsource-variable/literata/wght-italic.css";
import "@fontsource-variable/space-grotesk";
import "../shared/skin-base.css";
import "./storyboard.css";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "../../components/Avatar";
import { Controls } from "../../components/Controls";
import { StatsBar } from "../../components/StatsBar";
import { useStore } from "../../store";
import type { Msg, Profile, Thread } from "../../types";
import { fmtDay, fmtDayTime, fmtTime, initials } from "../../util";
import { BudgetBanner } from "../shared/BudgetBanner";
import { Meter } from "../shared/Meter";
import { OpenSign } from "../shared/OpenSign";
import { useAllFeeds } from "../shared/useAllFeeds";
import { threadPlace, TIER_COLOR, useRoster } from "../shared/useRoster";

const ALL = "all";

/** Storyboard: the taproom as a script you read. Panels of dialogue, a cast strip, and a character sheet with a relationship constellation. */
export default function Storyboard() {
  const connect = useStore((s) => s.connect);
  useEffect(() => connect(), [connect]);
  useAllFeeds();
  const [channel, setChannel] = useState<string>(ALL);

  return (
    <div className="flex h-full flex-col">
      <TopBar channel={channel} setChannel={setChannel} />
      <CastStrip />
      <BudgetBanner />
      <div className="flex min-h-0 flex-1">
        <Reader channel={channel} />
        <CharacterSheet />
      </div>
      <StatsBar />
    </div>
  );
}

function TopBar({ channel, setChannel }: { channel: string; setChannel: (c: string) => void }) {
  const channels = useStore((s) => s.channels);
  const clock = useStore((s) => s.clock);
  const threads = useStore((s) => s.threads);
  const liveIn = (c: string) => Object.values(threads).filter((t) => c === ALL || t.channel === c).length;
  const tabs = [{ id: ALL, desc: "Everything, in order" }, ...channels];
  return (
    <header className="flex items-center gap-4 border-b border-[var(--border)] px-5 py-2">
      <div className="mr-2">
        <div className="text-[17px] font-semibold tracking-tight">Modist Social</div>
        <div className="text-[10px] tracking-[0.2em] text-[var(--muted)] uppercase">
          {clock ? `${fmtDay(clock.sim_now)} ${fmtTime(clock.sim_now)}` : ""}
          {clock?.paused ? " · paused" : ""}
        </div>
      </div>
      <OpenSign className="text-[14px]" />
      <nav className="flex items-center gap-1">
        {tabs.map((t) => {
          const n = liveIn(t.id);
          const on = channel === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setChannel(t.id)}
              title={t.desc}
              className={`cursor-pointer rounded-full px-3 py-1 text-[13px] ${on ? "bg-[var(--accent)] font-semibold text-black" : "text-[var(--muted)] hover:bg-white/5 hover:text-[var(--ink)]"}`}
            >
              {t.id === ALL ? "All" : t.id.replace("-", " ")}
              {n > 0 && <span className={`ml-1.5 text-[10px] ${on ? "text-black/60" : "text-[var(--ok)]"}`}>●{n}</span>}
            </button>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <Controls />
      </div>
    </header>
  );
}

function CastStrip() {
  const { bartenders, patrons } = useRoster();
  const presence = useStore((s) => s.presence);
  const openProfile = useStore((s) => s.openProfile);
  const profileId = useStore((s) => s.profileId);
  const cast = [...bartenders, ...patrons];
  return (
    <div className="cast flex shrink-0 items-start gap-1 overflow-x-auto border-b border-[var(--border)] bg-[var(--sidebar)] px-4 py-2">
      <div className="mr-2 self-center text-[10px] tracking-[0.2em] text-[var(--muted)] uppercase">
        Cast
        <br />
        <span className="text-[var(--ink)]">{cast.length}</span>
      </div>
      {cast.map((p) => {
        const pr = presence[p.id];
        const ring = TIER_COLOR[pr?.tier ?? ""];
        return (
          <div
            key={p.id}
            role="button"
            tabIndex={0}
            onClick={() => openProfile(p.id)}
            onKeyDown={(e) => e.key === "Enter" && openProfile(p.id)}
            title={`${p.display}${pr?.drink ? ` · ${pr.drink}` : ""}`}
            className={`flex w-16 shrink-0 cursor-pointer flex-col items-center rounded-lg px-1 py-1 hover:bg-white/5 ${profileId === p.id ? "bg-white/8" : ""}`}
          >
            <span
              className="rounded-full"
              style={{ boxShadow: ring ? `0 0 0 2.5px ${ring}` : p.role === "bartender" ? "0 0 0 2.5px var(--accent)" : "0 0 0 1px var(--border)" }}
            >
              <Avatar id={p.id} size={40} round />
            </span>
            <span className="mt-1 w-full truncate text-center text-[11px]">{p.short}</span>
            <span className="w-full truncate text-center text-[9px] text-[var(--muted)]">{p.role === "bartender" ? "bartender" : pr?.drink ?? "—"}</span>
          </div>
        );
      })}
      {!cast.length && <div className="self-center text-[12px] text-[var(--muted)]">Nobody in yet.</div>}
    </div>
  );
}

type Item = { key: string; ts: number; thread?: Thread; msg?: Msg };

function Reader({ channel }: { channel: string }) {
  const feeds = useStore((s) => s.feeds);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const items = useMemo<Item[]>(() => {
    const picked = Object.entries(feeds).filter(([c]) => channel === ALL || c === channel);
    const out: Item[] = [];
    for (const [, f] of picked) {
      for (const t of f.threads) out.push({ key: `t${t.id}`, ts: +new Date(t.started_at), thread: t });
      for (const m of f.messages) out.push({ key: `m${m.id}`, ts: +new Date(m.sim_ts), msg: m });
    }
    return out.sort((a, b) => a.ts - b.ts || a.key.localeCompare(b.key)).slice(-80);
  }, [feeds, channel]);

  const lastKey = items.at(-1)?.key;
  const total = useStore((s) => items.reduce((n, it) => n + (it.thread ? (s.threadMsgs[it.thread.id]?.length ?? 0) : 0), 0));
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lastKey, total, channel]);

  return (
    <div
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
      className="scroll min-w-0 flex-1"
    >
      <div className="mx-auto max-w-[48rem] px-5 py-6">
        {!items.length && <div className="py-16 text-center text-[var(--muted)]">The script is blank so far. The taproom opens at 3pm.</div>}
        {items.map((it) => (it.thread ? <Panel key={it.key} t={it.thread} /> : <Direction key={it.key} m={it.msg!} />))}
      </div>
    </div>
  );
}

const Direction = memo(function Direction({ m }: { m: Msg }) {
  return (
    <div className={`bubble-in direction my-2 text-center text-[13px] ${m.kind === "system" ? "text-[var(--muted)]/70" : "text-[var(--muted)]"}`}>
      <span className="mr-2 text-[10px] tracking-normal opacity-60" style={{ fontVariantCaps: "normal" }}>{fmtTime(m.sim_ts)}</span>
      {m.text}
    </div>
  );
});

const PREVIEW = 6;

const Panel = memo(function Panel({ t }: { t: Thread }) {
  const msgs = useStore((s) => s.threadMsgs[t.id]) ?? [];
  const typing = useStore((s) => s.typing[t.id]) ?? [];
  const people = useStore((s) => s.people);
  const presence = useStore((s) => s.presence);
  const [all, setAll] = useState(false);
  const live = !t.ended_at;
  const shown = all || live ? msgs : msgs.slice(-PREVIEW);
  const hidden = msgs.length - shown.length;
  const names = t.participants.map((id) => people[id]?.short).filter(Boolean).join(", ");

  return (
    <section className={`panel bubble-in my-4 rounded-2xl ${live ? "live breathe" : ""}`}>
      <header className="flex items-baseline gap-3 border-b border-[var(--border)] px-5 py-2.5">
        <span className="text-[10px] tracking-[0.2em] text-[var(--accent)] uppercase">{live ? "● Live" : "Scene"}</span>
        <span className="text-[14px] font-semibold">{threadPlace(t, presence)}</span>
        <span className="text-[12px] text-[var(--muted)]">{fmtTime(t.started_at)}{t.ended_at ? ` – ${fmtTime(t.ended_at)}` : ""}</span>
        <span className="ml-auto truncate text-[12px] text-[var(--muted)]">{names}</span>
      </header>
      <div className="px-5 py-3">
        {hidden > 0 && (
          <button onClick={() => setAll(true)} className="direction mb-2 cursor-pointer text-[12px] text-[var(--accent)] hover:underline">
            {hidden} earlier line{hidden === 1 ? "" : "s"}
          </button>
        )}
        {!msgs.length && <div className="font-serif text-[15px] text-[var(--muted)] italic">{t.root_text}</div>}
        {shown.map((m, i) => (
          <Line key={m.id} m={m} grouped={i > 0 && shown[i - 1].kind === "speech" && shown[i - 1].speaker_id === m.speaker_id} />
        ))}
        {typing.filter((id) => people[id]).map((id) => (
          <Bubble key={`typing-${id}`} id={id} grouped={false}>
            <span className="dots text-[18px] leading-none">
              <span>•</span>
              <span>•</span>
              <span>•</span>
            </span>
          </Bubble>
        ))}
      </div>
    </section>
  );
});

const Line = memo(function Line({ m, grouped }: { m: Msg; grouped: boolean }) {
  if (m.kind !== "speech" || !m.speaker_id) {
    return (
      <div className={`direction my-1.5 text-center text-[12.5px] text-[var(--muted)] ${m.kind === "action" ? "" : "opacity-70"}`}>
        {m.text}
      </div>
    );
  }
  return (
    <Bubble id={m.speaker_id} grouped={grouped} time={fmtTime(m.sim_ts)}>
      <span className="font-serif text-[15.5px] leading-relaxed">{m.text}</span>
    </Bubble>
  );
});

function Bubble({ id, grouped, time, children }: { id: string; grouped: boolean; time?: string; children: React.ReactNode }) {
  const p = useStore((s) => s.people[id]);
  if (!p) return null;
  const bt = p.role === "bartender";
  return (
    <div className={`bubble-in flex gap-3 ${grouped ? "mt-1" : "mt-3"}`}>
      <div className="w-8 shrink-0">{!grouped && <Avatar id={id} size={32} round />}</div>
      <div className="min-w-0 max-w-[85%]">
        {!grouped && (
          <div className="mb-0.5 flex items-baseline gap-2 text-[12px]">
            <span className="font-semibold" style={{ color: p.color }}>{p.short}</span>
            {bt && <span className="text-[9px] tracking-[0.18em] text-[var(--accent)] uppercase">bartender</span>}
            {time && <span className="text-[var(--muted)]">{time}</span>}
          </div>
        )}
        <div
          className="inline-block rounded-2xl rounded-tl-md px-3.5 py-2"
          style={{ background: `${p.color}22`, borderLeft: `3px solid ${bt ? "var(--accent)" : p.color}` }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

const REASON: Record<string, string> = { unwind: "to unwind", catch_up: "to catch up with friends", solo: "for some time alone", game: "to watch the game", date: "for a date", work: "to work" };
const moodWord = (m: number) => (m >= 0.4 ? "good" : m >= 0.1 ? "fine" : m > -0.25 ? "so-so" : m > -0.5 ? "irritable" : "down");
const BIG5: [keyof NonNullable<Profile["persona"]["big5"]>, string][] = [["o", "Open"], ["c", "Conscientious"], ["e", "Extravert"], ["a", "Agreeable"], ["n", "Neurotic"]];
const BOND_ICON: Record<string, string> = { friends: "🤝", close_friends: "💛", rivals: "⚔️", crush: "💘", couple: "❤️", falling_out: "💔", ex: "🥀", mentor: "🎓" };

function CharacterSheet() {
  const profileId = useStore((s) => s.profileId);
  const p = useStore((s) => s.profile);
  const close = useStore((s) => s.openProfile);
  if (!profileId) return null;
  if (!p || p.id !== profileId) {
    return <aside className="w-[28rem] shrink-0 border-l border-[var(--border)] p-5 text-[var(--muted)]">Pulling the file…</aside>;
  }
  const d = p.persona;
  return (
    <aside className="flex w-[28rem] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--sidebar)]">
      <div className="flex items-center justify-between px-5 pt-4">
        <span className="text-[10px] tracking-[0.2em] text-[var(--muted)] uppercase">Character</span>
        <button onClick={() => close(null)} className="cursor-pointer rounded px-2 text-xl text-[var(--muted)] hover:bg-white/10">×</button>
      </div>
      <div className="scroll flex-1 px-5 pb-6">
        <div className="mt-2 flex items-center gap-4">
          <Avatar id={p.id} size={72} round />
          <div className="min-w-0">
            <div className="text-[22px] leading-tight font-semibold">{p.display}</div>
            <div className="text-[13px] text-[var(--muted)]">{p.pronouns} · {d.age} · {d.job}</div>
            <div className="mt-1 text-[12px]">
              {p.present ? <span className="text-[var(--ok)]">● in the taproom{p.drink ? `, drinking ${p.drink}` : ""}</span> : <span className="text-[var(--muted)]">○ not here tonight</span>}
            </div>
          </div>
        </div>

        {p.state && (
          <Block title="Right now">
            <p className="font-serif text-[14.5px] leading-relaxed">
              Here {REASON[p.state.reason] ?? p.state.reason}. Feeling {moodWord(p.state.mood)}
              {p.state.drinks ? `, ${p.state.drinks} drink${p.state.drinks > 1 ? "s" : ""} in and ${p.state.tier}` : ", stone sober"}
              {p.state.cut_off ? " and cut off" : p.state.on_water ? " and on water" : ""}.
              {p.state.need && ` Needs to ${p.state.need}.`}
            </p>
            {p.state.thought && <p className="mt-2 font-serif text-[14px] text-[var(--muted)] italic">“{p.state.thought}”</p>}
            <div className="mt-3 flex items-center gap-3 text-[11px] text-[var(--muted)]">
              <span className="w-20">Social energy</span>
              <Meter value={p.state.battery} color="var(--accent)" />
              <span className="w-8 text-right">{Math.round(p.state.battery * 100)}%</span>
            </div>
          </Block>
        )}

        <Block title="Who they are">
          <div className="flex flex-wrap gap-1.5">
            {d.traits.map((t) => (
              <span key={t} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[12px]">{t}</span>
            ))}
          </div>
          <p className="mt-3 font-serif text-[14px] leading-relaxed text-[var(--ink)]/90">
            {d.politics}. Into {d.interests.join(", ")}. {d.quirk}
            {d.life ? ` ${d.life}` : ""}
          </p>
          {d.takes && d.takes.length > 0 && <p className="mt-2 font-serif text-[13.5px] text-[var(--muted)] italic">Believes {d.takes.join("; ")}.</p>}
          {d.big5 && (
            <div className="mt-3 space-y-1.5">
              {BIG5.map(([k, label]) => (
                <div key={k} className="flex items-center gap-3 text-[11px] text-[var(--muted)]">
                  <span className="w-24">{label}</span>
                  <Meter value={d.big5![k]} max={5} height={5} color={p.color} />
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block title={`Constellation · ${p.relationships.length}`}>
          {p.relationships.length ? <Constellation p={p} /> : <div className="text-[13px] text-[var(--muted)]">Hasn't met anyone yet.</div>}
        </Block>

        {p.bond_changes?.length > 0 && (
          <Block title="Lately">
            {p.bond_changes.slice(0, 5).map((c, i) => (
              <div key={i} className="font-serif text-[13.5px] leading-relaxed">
                <span className="font-semibold">{c.with}</span>: {c.from.replace("_", " ")} → {c.to.replace("_", " ")}
                {c.why && <span className="text-[var(--muted)]"> ({c.why})</span>}
              </div>
            ))}
          </Block>
        )}

        <Block title="Remembers">
          {p.memories.slice(0, 10).map((m, i) => (
            <div key={i} className="mb-2.5">
              <div className="font-serif text-[13.5px] leading-relaxed">{m.text}</div>
              <div className="text-[11px] text-[var(--muted)]">
                {m.kind === "reflection" && "💭 "}
                {m.source && <span title={`${m.accuracy}% accurate after ${m.hops} retelling${m.hops === 1 ? "" : "s"}`}>🗣 heard from {m.source} · </span>}
                {fmtDayTime(m.sim_ts)}
              </div>
            </div>
          ))}
          {!p.memories.length && <div className="text-[13px] text-[var(--muted)]">Nothing yet.</div>}
        </Block>
      </div>
    </aside>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-[10px] tracking-[0.2em] text-[var(--muted)] uppercase">{title}</h3>
      {children}
    </section>
  );
}

/** The person at the centre; everyone they know on a ring, nearer the closer they are, the line warm or cold by how they feel. */
function Constellation({ p }: { p: Profile }) {
  const open = useStore((s) => s.openProfile);
  const S = 400;
  const c = S / 2;
  const rels = [...p.relationships].sort((a, b) => b.familiarity - a.familiarity).slice(0, 24);
  const n = rels.length;
  const nodes = rels.map((r, i) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
    const rad = 58 + (1 - r.familiarity / 100) * 112;
    return { r, x: c + Math.cos(a) * rad, y: c + Math.sin(a) * rad };
  });
  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="w-full">
      {[58, 114, 170].map((rad) => (
        <circle key={rad} cx={c} cy={c} r={rad} fill="none" stroke="var(--border)" strokeWidth={1} strokeDasharray="2 4" />
      ))}
      {nodes.map(({ r, x, y }) => (
        <line key={r.id} x1={c} y1={c} x2={x} y2={y} stroke={r.affinity >= 0 ? "var(--ok)" : "#e5484d"} strokeWidth={1 + Math.abs(r.affinity) / 40} strokeOpacity={0.35 + Math.abs(r.affinity) / 200} />
      ))}
      {nodes.map(({ r, x, y }) => (
        <g key={r.id} className="cursor-pointer" onClick={() => open(r.id)}>
          <title>{`${r.name} · ${r.bond !== "stranger" && BOND_ICON[r.bond] ? r.bond.replace("_", " ") : r.kind} · familiarity ${Math.round(r.familiarity)} · affinity ${Math.round(r.affinity)}${r.notes ? `\n${r.notes}` : ""}`}</title>
          <circle cx={x} cy={y} r={15} fill={r.color} stroke="var(--canvas)" strokeWidth={2} />
          <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill="#fff">{initials(r.name)}</text>
          {BOND_ICON[r.bond] && <text x={x + 12} y={y - 10} fontSize={12}>{BOND_ICON[r.bond]}</text>}
          <text x={x} y={y + 27} textAnchor="middle" fontSize={10} fill="var(--muted)">{r.name.split(" ")[0]}</text>
        </g>
      ))}
      <circle cx={c} cy={c} r={26} fill={p.color} stroke="var(--accent)" strokeWidth={2.5} />
      <text x={c} y={c} textAnchor="middle" dominantBaseline="central" fontSize={15} fontWeight={700} fill="#fff">{initials(p.display)}</text>
    </svg>
  );
}
