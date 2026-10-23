import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/plus-jakarta-sans";
import "../shared/skin-base.css";
import "./control.css";

import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "../../components/Avatar";
import { ProfilePane } from "../../components/RightPane";
import { useStore } from "../../store";
import type { GodAssessment, Thread } from "../../types";
import { fmtDay, fmtTime, kfmt, money } from "../../util";
import { BudgetBanner } from "../shared/BudgetBanner";
import { Meter } from "../shared/Meter";
import { NewsTicker } from "../shared/NewsTicker";
import { Radial } from "../shared/Radial";
import { Sparkline } from "../shared/Sparkline";
import { Transcript } from "../shared/Transcript";
import { useAllFeeds, useLiveThreads, useTail } from "../shared/useAllFeeds";
import { threadPlace, TIER_COLOR, useRoster } from "../shared/useRoster";

/** Control Room: the director's console. A timeline of every conversation, the knobs, the room, and what the model is costing. */
export default function Control() {
  const connect = useStore((s) => s.connect);
  useEffect(() => connect(), [connect]);
  useAllFeeds();
  const openThread = useStore((s) => s.openThread);
  const profileId = useStore((s) => s.profileId);

  return (
    <div className="flex h-full flex-col">
      <TopStrip />
      <BudgetBanner />
      <div className="flex min-h-0 flex-1">
        <Director />
        <div className="flex min-w-0 flex-1 flex-col">
          <Timeline />
          <div className="flex min-h-0 flex-1">
            <Tail />
            {openThread != null && (
              <div className="flex w-[30rem] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--panel)]">
                <Transcript id={openThread} />
              </div>
            )}
          </div>
        </div>
        {profileId ? <ProfilePane /> : <Telemetry />}
      </div>
      <NewsTicker className="border-t border-[var(--border)] bg-[var(--sidebar)] px-4 py-1 font-mono text-[11px] text-[var(--muted)]" empty="No headlines on the wire today." />
    </div>
  );
}

const CROWD_WORD = (n: number) => (n <= 0.6 ? "quiet" : n <= 1 ? "normal" : n <= 1.6 ? "busy" : "packed");

function TopStrip() {
  const clock = useStore((s) => s.clock);
  const connected = useStore((s) => s.connected);
  const llmMode = useStore((s) => s.llmMode);
  const city = useStore((s) => s.city);
  const live = useLiveThreads();
  const god = clock?.god;
  const room = clock?.room;
  return (
    <div className="flex items-stretch border-b border-[var(--border)] bg-[var(--sidebar)]">
      <Cell label="Modist Social">
        <span className="text-[13px] font-semibold">{city || "Taproom"}</span>
      </Cell>
      <Cell label="Sim clock">
        <span className="num text-[22px] leading-none">{clock ? fmtTime(clock.sim_now) : "--:--"}</span>
        <span className="ml-2 font-mono text-[11px] text-[var(--muted)]">{clock ? fmtDay(clock.sim_now) : ""}</span>
      </Cell>
      <Cell label="State">
        <span className={`num text-[13px] ${clock?.paused ? "text-[var(--warn)]" : clock?.open ? "text-[var(--ok)]" : "text-[var(--muted)]"}`}>
          {clock?.paused ? "PAUSED" : clock?.open ? "OPEN" : "CLOSED"}
        </span>
      </Cell>
      <Cell label="Speed">
        <span className="num text-[13px]">{clock?.speed ?? 0}×</span>
        {clock && clock.effective_speed < clock.speed - 0.5 && <span className="ml-2 font-mono text-[11px] text-[var(--warn)]">held {Math.round(clock.effective_speed)}×</span>}
      </Cell>
      <Cell label="Crowd">
        <span className="num text-[13px]">{clock?.crowd ?? 0}</span>
        <span className="ml-2 font-mono text-[11px] text-[var(--muted)]">{clock ? CROWD_WORD(clock.crowd_level) : ""}</span>
      </Cell>
      <Cell label="Conversations">
        <span className="num text-[13px] text-[var(--accent)]">{live.length}</span>
        <span className="ml-2 font-mono text-[11px] text-[var(--muted)]">live</span>
      </Cell>
      {room && (
        <Cell label="Room">
          <span className="font-mono text-[11px]">
            {room.weather} · {room.noise}
            {room.trivia && <span className="text-[var(--accent)]"> · trivia</span>}
            {room.game && (
              <span className={room.game.live ? "text-[var(--accent)]" : "text-[var(--muted)]"}>
                {" · "}
                {room.game.team} {room.game.live ? `${room.game.score[0]}–${room.game.score[1]}` : "vs"} {room.game.opp}
              </span>
            )}
          </span>
        </Cell>
      )}
      <Cell label="God mode" grow>
        {god ? (
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-[11px] text-[var(--warn)]" title={god.text}>{god.text}</span>
            <Meter value={god.heat} color="var(--warn)" className="w-20" title={`heat ${Math.round(god.heat * 100)}%`} />
          </div>
        ) : (
          <span className="font-mono text-[11px] text-[var(--muted)]">off</span>
        )}
      </Cell>
      <Cell label="Dialogue">
        <span className="font-mono text-[11px]">{llmMode === "mock" ? "mock" : "claude haiku"}</span>
      </Cell>
      <Cell label="Link" last>
        <span className={`font-mono text-[11px] ${connected ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>{connected ? "● live" : "○ reconnecting"}</span>
      </Cell>
    </div>
  );
}

function Cell({ label, children, grow = false, last = false }: { label: string; children: React.ReactNode; grow?: boolean; last?: boolean }) {
  return (
    <div className={`${last ? "" : "cell"} ${grow ? "min-w-0 flex-1" : "shrink-0"} px-4 py-2`}>
      <div className="lbl mb-1">{label}</div>
      <div className="flex min-h-[22px] items-center">{children}</div>
    </div>
  );
}

const SPEEDS = [5, 15, 30, 60, 120, 240];
const CROWDS: [number, string][] = [[0.6, "Quiet"], [1, "Normal"], [1.6, "Busy"], [2.5, "Packed"]];
const REACH = ["Only fans care", "A few care", "Plenty care", "Most care", "Everyone's talking"];
const SPLIT = ["Everyone agrees", "Friendly rivalry", "Some disagree", "Sides form", "Picks sides, gets ugly"];

function Director() {
  const clock = useStore((s) => s.clock);
  const control = useStore((s) => s.control);
  return (
    <aside className="scroll flex w-72 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--sidebar)]">
      <Section title="Director">
        {clock && (
          <div className="space-y-2">
            <button
              onClick={() => control({ action: clock.paused ? "resume" : "pause" })}
              className={`w-full cursor-pointer rounded border px-3 py-1.5 font-mono text-[12px] ${clock.paused ? "border-[var(--ok)] text-[var(--ok)]" : "border-[var(--border)] hover:bg-white/5"}`}
            >
              {clock.paused ? "▶ RESUME" : "⏸ PAUSE"}
            </button>
            <label className="flex items-center justify-between gap-2">
              <span className="lbl">Speed</span>
              <select value={SPEEDS.includes(clock.speed) ? clock.speed : "custom"} onChange={(e) => control({ action: "speed", speed: Number(e.target.value) })} className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-[var(--ink)]">
                {!SPEEDS.includes(clock.speed) && <option value="custom">{clock.speed}×</option>}
                {SPEEDS.map((s) => (
                  <option key={s} value={s} className="text-black">{s}×</option>
                ))}
              </select>
            </label>
            <label className="flex items-center justify-between gap-2">
              <span className="lbl">Crowd</span>
              <select value={clock.crowd_level} onChange={(e) => control({ action: "crowd", crowd: Number(e.target.value) })} className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-[var(--ink)]">
                {CROWDS.map(([v, l]) => (
                  <option key={v} value={v} className="text-black">{l}</option>
                ))}
              </select>
            </label>
          </div>
        )}
      </Section>
      <GodConsole />
      <Section title="On shift">
        <OnShift />
      </Section>
    </aside>
  );
}

function OnShift() {
  const { bartenders } = useRoster();
  return (
    <div className="flex flex-wrap gap-2">
      {bartenders.map((b) => (
        <span key={b.id} className="flex items-center gap-1.5 font-mono text-[11px]">
          <Avatar id={b.id} size={18} /> {b.short}
        </span>
      ))}
      {!bartenders.length && <span className="font-mono text-[11px] text-[var(--muted)]">nobody</span>}
    </div>
  );
}

function GodConsole() {
  const god = useStore((s) => s.clock?.god ?? null);
  const { setGod, clearGod, assessGod } = useStore();
  const [text, setText] = useState("");
  const [read, setRead] = useState<(GodAssessment & { text: string }) | null>(null);
  const [reach, setReach] = useState(3);
  const [split, setSplit] = useState(2);
  const [busy, setBusy] = useState(false);
  const current = read && read.text === text.trim() ? read : null;

  const readRoom = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      const a = await assessGod(t);
      setRead({ ...a, text: t });
      setReach(a.reach);
      setSplit(a.divisiveness);
    } finally {
      setBusy(false);
    }
  };
  const submit = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      await (current ? setGod(t, reach, split) : setGod(t));
      setText("");
      setRead(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="God mode">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={280}
        rows={2}
        placeholder="What just happened in town?"
        className="w-full rounded border border-[var(--border)] bg-transparent p-2 font-mono text-[12px]"
      />
      {current && (
        <div className="mt-2 space-y-2">
          <Gauge label="Reach" hints={REACH} value={reach} onChange={setReach} />
          <Gauge label="Divisiveness" hints={SPLIT} value={split} onChange={setSplit} />
          <div className="font-mono text-[11px] text-[var(--muted)]">
            {current.sides[0]} <span className="text-[var(--ink)]">vs</span> {current.sides[1]}
            {current.reason && <div className="mt-1">{current.reason}</div>}
          </div>
        </div>
      )}
      <div className="mt-2 flex gap-2">
        <button onClick={readRoom} disabled={busy || !text.trim()} className="cursor-pointer rounded border border-[var(--border)] px-2 py-1 font-mono text-[11px] disabled:opacity-40">
          {busy && !current ? "READING…" : "READ ROOM"}
        </button>
        <button onClick={submit} disabled={busy || !text.trim()} className="cursor-pointer rounded bg-[var(--warn)] px-2 py-1 font-mono text-[11px] text-black disabled:opacity-40">
          SET
        </button>
        {god && (
          <button onClick={() => clearGod()} className="ml-auto cursor-pointer rounded border border-[var(--border)] px-2 py-1 font-mono text-[11px]">
            OFF
          </button>
        )}
      </div>
      {god && (
        <div className="mt-3 space-y-1.5 border-t border-[var(--border)] pt-3">
          <div className="text-[12px] text-[var(--warn)]">{god.text}</div>
          <Row label="Reach" v={god.reach} max={5} color="var(--warn)" />
          <Row label="Divisive" v={god.divisiveness} max={5} color="var(--warn)" />
          <Row label="Heat" v={god.heat} max={1} color="var(--bad)" />
          <Row label="Fade" v={god.fade} max={1} color="var(--muted)" />
          <div className="font-mono text-[11px] text-[var(--muted)]">
            {god.sides[0]} <span className="text-[var(--ink)]">vs</span> {god.sides[1]}
          </div>
        </div>
      )}
    </Section>
  );
}

function Gauge({ label, hints, value, onChange }: { label: string; hints: string[]; value: number; onChange: (n: number) => void }) {
  return (
    <label className="block">
      <div className="flex justify-between font-mono text-[11px]">
        <span className="text-[var(--muted)]">{label}</span>
        <span>{hints[value - 1]}</span>
      </div>
      <input type="range" min={1} max={5} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--warn)]" />
    </label>
  );
}

function Row({ label, v, max, color }: { label: string; v: number; max: number; color: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px]">
      <span className="w-14 text-[var(--muted)]">{label}</span>
      <Meter value={v} max={max} color={color} />
      <span className="w-8 text-right">{max === 1 ? `${Math.round(v * 100)}%` : `${v}/${max}`}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-[var(--border)] px-4 py-3">
      <h3 className="lbl mb-2">{title}</h3>
      {children}
    </section>
  );
}

const WINDOW_MIN = 90;
const ROW_H = 16;
const MAX_ROWS = 4;
const KIND_COLOR: Record<string, string> = { chat: "var(--accent)", order: "var(--warn)", staff: "var(--violet)" };

function Timeline() {
  const channels = useStore((s) => s.channels);
  const feeds = useStore((s) => s.feeds);
  const clock = useStore((s) => s.clock);
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const openThread = useStore((s) => s.openThread);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const now = clock ? +new Date(clock.sim_now) : Date.now();
  const start = now - WINDOW_MIN * 60_000;
  const LEFT = 92;
  const span = Math.max(1, w - LEFT - 12);
  const x = (ms: number) => LEFT + ((ms - start) / (now - start)) * span;

  // Each channel is a lane; conversations that overlap in time stack into sub-rows so every bar stays legible.
  const { bars, lanes, H } = useMemo(() => {
    const bars: { t: Thread; y: number; x0: number; x1: number; live: boolean }[] = [];
    const lanes: { id: string; y: number; rows: number }[] = [];
    let y = 22;
    for (const c of channels) {
      const list = (feeds[c.id]?.threads ?? [])
        .map((t) => ({ t, s: +new Date(t.started_at), e: t.ended_at ? +new Date(t.ended_at) : now }))
        .filter((b) => b.e >= start)
        .sort((a, b) => a.s - b.s);
      const rowEnd: number[] = [];
      for (const b of list) {
        let row = rowEnd.findIndex((end) => end <= b.s);
        if (row < 0) row = rowEnd.length < MAX_ROWS ? rowEnd.length : rowEnd.indexOf(Math.min(...rowEnd));
        rowEnd[row] = b.e;
        bars.push({ t: b.t, y: y + row * ROW_H + 2, x0: Math.max(LEFT, x(b.s)), x1: Math.min(LEFT + span, x(b.e)), live: !b.t.ended_at });
      }
      const rows = Math.max(1, rowEnd.length);
      lanes.push({ id: c.id, y, rows });
      y += rows * ROW_H + 6;
    }
    return { bars, lanes, H: y + 4 };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channels, feeds, now, w]);

  const ticks = Array.from({ length: WINDOW_MIN / 15 + 1 }, (_, i) => start + i * 15 * 60_000);

  return (
    <div ref={ref} className="shrink-0 border-b border-[var(--border)] bg-[var(--panel)]">
      <div className="flex items-baseline justify-between px-4 pt-2">
        <span className="lbl">Timeline · last {WINDOW_MIN} sim minutes</span>
        <span className="font-mono text-[10px] text-[var(--muted)]">
          <i className="mr-1 inline-block h-2 w-2 bg-[var(--accent)]" />chat <i className="mx-1 inline-block h-2 w-2 bg-[var(--warn)]" />order <i className="mx-1 inline-block h-2 w-2 bg-[var(--violet)]" />staff
        </span>
      </div>
      <svg width="100%" height={H} className="block">
        {ticks.map((ms) => (
          <g key={ms}>
            <line x1={x(ms)} x2={x(ms)} y1={14} y2={H - 4} stroke="var(--border)" strokeWidth={1} />
            <text x={x(ms)} y={10} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--muted)">{new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</text>
          </g>
        ))}
        {lanes.map((l) => (
          <g key={l.id}>
            <text x={8} y={l.y + (l.rows * ROW_H) / 2 + 4} fontSize={10} fontFamily="var(--font-mono)" fill="var(--muted)">#{l.id}</text>
            <line x1={LEFT} x2={LEFT + span} y1={l.y + l.rows * ROW_H + 3} y2={l.y + l.rows * ROW_H + 3} stroke="var(--border)" strokeWidth={1} />
          </g>
        ))}
        {bars.map(({ t, y, x0, x1, live }) => {
          const wd = Math.max(3, x1 - x0);
          const on = openThread === t.id;
          const label = `${threadPlace(t, presence)} · ${t.participants.map((p) => people[p]?.short).filter(Boolean).slice(0, 3).join(", ")}`;
          return (
            <g key={t.id} className={`cursor-pointer ${live ? "tl-live" : ""}`} onClick={() => openThreadPane(on ? null : t.id)}>
              <title>{`${label} · ${t.count} lines`}</title>
              <rect x={x0} y={y} width={wd} height={ROW_H - 4} rx={3} fill={KIND_COLOR[t.kind] ?? "var(--accent)"} fillOpacity={live ? 0.85 : 0.4} stroke={on ? "#fff" : "none"} strokeWidth={1.5} />
              {live && <circle cx={x1} cy={y + (ROW_H - 4) / 2} r={3} fill={KIND_COLOR[t.kind]} />}
              {wd > 60 && (
                <text x={x0 + 4} y={y + (ROW_H - 4) / 2 + 3} fontSize={9} fontFamily="var(--font-mono)" fill={live ? "#000" : "var(--ink)"}>
                  {label.length > (wd - 8) / 5.6 ? label.slice(0, Math.max(0, Math.floor((wd - 8) / 5.6) - 1)) + "…" : label}
                </text>
              )}
            </g>
          );
        })}
        <line x1={LEFT + span} x2={LEFT + span} y1={14} y2={H - 4} stroke="var(--accent)" strokeWidth={1} />
      </svg>
    </div>
  );
}

function Tail() {
  const tail = useTail(80);
  const people = useStore((s) => s.people);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [tail.length, tail.at(-1)?.id]);
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="lbl border-b border-[var(--border)] px-4 py-1.5">Tail · every channel</div>
      <div
        ref={ref}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
        className="scroll flex-1 px-4 py-2 font-mono text-[11.5px] leading-[1.55]"
      >
        {tail.map((m) => {
          const p = m.speaker_id ? people[m.speaker_id] : undefined;
          return (
            <div key={m.id} className="bubble-in flex gap-2 whitespace-pre-wrap">
              <span className="shrink-0 text-[var(--muted)]">{fmtTime(m.sim_ts)}</span>
              <span className="w-28 shrink-0 truncate text-[var(--muted)]">#{m.channel}</span>
              {p && <span className="shrink-0 font-semibold" style={{ color: p.color }}>{p.short}</span>}
              <span className={m.kind === "speech" ? "" : "text-[var(--muted)] italic"}>{m.text}</span>
            </div>
          );
        })}
        {!tail.length && <div className="text-[var(--muted)]">Nothing on the wire yet.</div>}
      </div>
    </div>
  );
}

/** Messages and model calls per minute, sampled client-side every few seconds. */
function useRates() {
  const feeds = useStore((s) => s.feeds);
  const threadMsgs = useStore((s) => s.threadMsgs);
  const calls = useStore((s) => s.stats?.calls ?? 0);
  const total = useMemo(
    () => Object.values(feeds).reduce((n, f) => n + f.messages.length, 0) + Object.values(threadMsgs).reduce((n, m) => n + m.length, 0),
    [feeds, threadMsgs],
  );
  const latest = useRef({ total, calls });
  latest.current = { total, calls };
  const [series, setSeries] = useState<{ msgs: number[]; calls: number[] }>({ msgs: [], calls: [] });
  useEffect(() => {
    // The first tick only takes a baseline, so the initial feed load doesn't read as a burst.
    let prev: { total: number; calls: number } | null = null;
    const id = setInterval(() => {
      const cur = { ...latest.current };
      if (prev) {
        const dm = Math.max(0, cur.total - prev.total) * 12;
        const dc = Math.max(0, cur.calls - prev.calls) * 12;
        setSeries((s) => ({ msgs: [...s.msgs, dm].slice(-40), calls: [...s.calls, dc].slice(-40) }));
      }
      prev = cur;
    }, 5000);
    return () => clearInterval(id);
  }, []);
  return series;
}

function Telemetry() {
  const stats = useStore((s) => s.stats);
  const rates = useRates();
  const { patrons, byLocation, bartenders } = useRoster();
  const presence = useStore((s) => s.presence);
  const pct = stats ? Math.min(1, stats.spent_today / stats.budget) : 0;
  const zones: [string, string][] = [["bar", "bar"], ["inside-tables", "inside"], ["patio", "patio"], ["ordering", "counter"], ["door", "door"]];
  return (
    <aside className="scroll flex w-80 shrink-0 flex-col border-l border-[var(--border)] bg-[var(--sidebar)]">
      <Section title="Model">
        {stats ? (
          <div className="space-y-3">
            <div className="flex items-center gap-4">
              <Radial value={stats.cache_hit_pct / 100} size={64} color="var(--accent)">
                <span className="num text-[12px]">{stats.cache_hit_pct}%</span>
              </Radial>
              <div className="grid flex-1 grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px]">
                <Stat label="calls" v={kfmt(stats.calls)} />
                <Stat label="errors" v={String(stats.errors)} bad={stats.errors > 0} />
                <Stat label="tokens in" v={kfmt(stats.input_tokens + stats.cache_read_tokens + stats.cache_write_tokens)} />
                <Stat label="tokens out" v={kfmt(stats.output_tokens)} />
                <Stat label="cached" v={kfmt(stats.cache_read_tokens)} />
                <Stat label="searches" v={String(stats.web_searches)} />
              </div>
            </div>
            <div>
              <div className="flex justify-between font-mono text-[11px]">
                <span className="text-[var(--muted)]">spend today</span>
                <span className={pct > 0.85 ? "text-[var(--bad)]" : ""}>{money(stats.spent_today)} / ${stats.budget.toFixed(2)}</span>
              </div>
              <Meter value={pct} color={pct > 0.85 ? "var(--bad)" : "var(--ok)"} className="mt-1" />
            </div>
          </div>
        ) : (
          <span className="font-mono text-[11px] text-[var(--muted)]">waiting for stats</span>
        )}
      </Section>
      <Section title="Rates · per minute">
        <div className="flex gap-4">
          <div>
            <div className="font-mono text-[10px] text-[var(--muted)]">lines</div>
            <Sparkline values={rates.msgs} width={128} height={34} color="var(--accent)" />
            <div className="num text-[12px]">{rates.msgs.at(-1) ?? 0}</div>
          </div>
          <div>
            <div className="font-mono text-[10px] text-[var(--muted)]">model calls</div>
            <Sparkline values={rates.calls} width={128} height={34} color="var(--warn)" />
            <div className="num text-[12px]">{rates.calls.at(-1) ?? 0}</div>
          </div>
        </div>
      </Section>
      <Section title={`Who's here · ${patrons.length} guests, ${bartenders.length} staff`}>
        <div className="space-y-2">
          {zones.map(([id, label]) => {
            const here = (byLocation[id] ?? []).filter((p) => p.role === "patron");
            return (
              <div key={id} className="flex items-start gap-2">
                <span className="w-14 shrink-0 pt-0.5 font-mono text-[10px] text-[var(--muted)]">{label} {here.length}</span>
                <div className="flex flex-wrap gap-1">
                  {here.map((p) => {
                    const ring = TIER_COLOR[presence[p.id]?.tier ?? ""];
                    return (
                      <span key={p.id} className="rounded-md" style={{ boxShadow: ring ? `0 0 0 2px ${ring}` : undefined }} title={`${p.display}${presence[p.id]?.drink ? ` · ${presence[p.id]!.drink}` : ""}`}>
                        <Avatar id={p.id} size={20} />
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Section>
    </aside>
  );
}

function Stat({ label, v, bad = false }: { label: string; v: string; bad?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-[var(--muted)]">{label}</span>
      <span className={`num ${bad ? "text-[var(--bad)]" : ""}`}>{v}</span>
    </div>
  );
}
