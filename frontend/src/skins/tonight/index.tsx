import "@fontsource-variable/fraunces";
import "@fontsource-variable/fraunces/wght-italic.css";
import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/caveat";
import "../shared/skin-base.css";
import "./tonight.css";

import { useEffect, useMemo, useState } from "react";
import { Avatar } from "../../components/Avatar";
import { Controls } from "../../components/Controls";
import { MessageRow, TypingLine } from "../../components/MessageRow";
import { RightPane } from "../../components/RightPane";
import { StatsBar } from "../../components/StatsBar";
import { useStore } from "../../store";
import { STOOLS } from "../../taproom/layout";
import type { MenuItem, Msg, Thread } from "../../types";
import { fmtDay, fmtTime } from "../../util";
import { BudgetBanner } from "../shared/BudgetBanner";
import { NewsTicker } from "../shared/NewsTicker";
import { OpenSign } from "../shared/OpenSign";
import { useAllFeeds, useLiveThreads } from "../shared/useAllFeeds";
import { threadPlace, TIER_COLOR, useRoster } from "../shared/useRoster";

/** Taproom Tonight: the simulation as a place. Every live conversation in the room at once, under a neon sign. */
export default function Tonight() {
  const connect = useStore((s) => s.connect);
  useEffect(() => connect(), [connect]);
  useAllFeeds();
  const [zone, setZone] = useState<string | null>(null);

  return (
    <>
      <div className="flex h-full flex-col">
        <Marquee />
        <NewsTicker className="border-b border-[var(--border)] bg-black/20 px-4 py-1 text-[12px] text-[var(--muted)]" />
        <BudgetBanner />
        <div className="flex min-h-0 flex-1">
          <RoomRail zone={zone} setZone={setZone} />
          <Board zone={zone} />
          <RightPane />
        </div>
        <div className="flex items-center border-t border-[var(--border)] bg-[var(--sidebar)]">
          <div className="flex shrink-0 items-center gap-2 px-4 py-1.5">
            <Controls />
          </div>
          <div className="min-w-0 flex-1 border-l border-[var(--border)]">
            <StatsBar />
          </div>
        </div>
      </div>
    </>
  );
}

function Marquee() {
  const clock = useStore((s) => s.clock);
  const city = useStore((s) => s.city);
  const room = clock?.room;
  const chips: { icon: string; text: string; hot?: boolean }[] = [];
  if (room) {
    chips.push({ icon: "☁", text: room.weather });
    if (room.game) {
      const [us, them] = room.game.score;
      chips.push({
        icon: "📺",
        text: room.game.live
          ? `${room.game.team} ${us}–${them} ${room.game.opp}`
          : `${room.game.team} vs ${room.game.opp} at ${fmtTime(room.game.start)}`,
        hot: room.game.live,
      });
    }
    if (room.trivia)
      chips.push({ icon: "❓", text: "Trivia night", hot: true });
    if (room.song)
      chips.push({ icon: "♪", text: `${room.song[0]} · ${room.song[1]}` });
    chips.push({ icon: "◉", text: room.noise });
  }
  return (
    <header className="flex items-center gap-6 border-b border-[var(--border)] px-5 py-3">
      <div className="min-w-0">
        <div className="font-display text-[22px] leading-tight font-semibold tracking-tight italic">
          Modist Social
        </div>
        <div className="text-[11px] tracking-[0.18em] text-[var(--muted)] uppercase">
          {city || "Taproom"}
        </div>
      </div>
      <OpenSign className="font-display text-[26px]" />
      {clock && (
        <div className="font-display text-[26px] leading-none font-medium">
          <span className="mr-2 text-[var(--muted)]">
            {fmtDay(clock.sim_now)}
          </span>
          {fmtTime(clock.sim_now)}
          {clock.paused && (
            <span className="ml-2 text-[12px] font-normal tracking-[0.18em] text-[var(--muted)] uppercase">
              paused
            </span>
          )}
        </div>
      )}
      <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
        {chips.map((c, i) => (
          <span
            key={i}
            className={`rounded-full border px-2.5 py-0.5 text-[12px] ${c.hot ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)]"}`}
          >
            <span className="mr-1.5 opacity-70">{c.icon}</span>
            {c.text}
          </span>
        ))}
      </div>
    </header>
  );
}

const ZONES = [
  { id: "bar", title: "The bar" },
  { id: "inside-tables", title: "Inside" },
  { id: "patio", title: "Patio" },
  { id: "ordering", title: "The counter" },
  { id: "staff", title: "Behind the bar" },
  { id: "door", title: "The door" },
];

function RoomRail({
  zone,
  setZone,
}: {
  zone: string | null;
  setZone: (z: string | null) => void;
}) {
  const { bartenders, byLocation, patrons } = useRoster();
  const live = useLiveThreads();
  const presence = useStore((s) => s.presence);
  const openProfile = useStore((s) => s.openProfile);

  const peopleIn = (id: string) =>
    id === "staff"
      ? bartenders
      : (byLocation[id] ?? []).filter((p) => p.role === "patron");

  return (
    <aside className="scroll flex w-72 shrink-0 flex-col gap-3 border-r border-[var(--border)] bg-[var(--sidebar)] p-3">
      <div className="px-1 text-[11px] font-semibold tracking-[0.18em] text-[var(--muted)] uppercase">
        The room · {patrons.length} guests
      </div>
      {ZONES.map((z) => {
        const here = peopleIn(z.id);
        const talking = live.filter((t) => t.channel === z.id).length;
        const on = zone === z.id;
        return (
          <div
            key={z.id}
            role="button"
            tabIndex={0}
            onClick={() => setZone(on ? null : z.id)}
            onKeyDown={(e) => e.key === "Enter" && setZone(on ? null : z.id)}
            className={`card cursor-pointer rounded-xl px-3 py-2.5 text-left transition-colors ${on ? "live" : "hover:border-[var(--muted)]/40"}`}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-display text-[17px] font-semibold">
                {z.title}
              </span>
              <span className="text-[11px] text-[var(--muted)]">
                {here.length}
                {z.id === "bar" ? `/${STOOLS.length}` : ""}
                {talking > 0 && (
                  <span className="ml-2 text-[var(--ok)]">● {talking}</span>
                )}
              </span>
            </div>
            <div className="mt-2 flex min-h-[26px] flex-wrap gap-1">
              {here.slice(0, 12).map((p) => (
                <span
                  key={p.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    void openProfile(p.id);
                  }}
                  className="rounded-full"
                  style={{
                    boxShadow: TIER_COLOR[presence[p.id]?.tier ?? ""]
                      ? `0 0 0 2px ${TIER_COLOR[presence[p.id]!.tier!]}`
                      : undefined,
                  }}
                  title={`${p.display}${presence[p.id]?.drink ? ` · ${presence[p.id]!.drink}` : ""}`}
                >
                  <Avatar id={p.id} size={24} round />
                </span>
              ))}
              {here.length > 12 && (
                <span className="self-center text-[11px] text-[var(--muted)]">
                  +{here.length - 12}
                </span>
              )}
              {here.length === 0 && (
                <span className="self-center text-[11px] text-[var(--muted)]/60">
                  empty
                </span>
              )}
            </div>
          </div>
        );
      })}
      <OnTap />
    </aside>
  );
}

function OnTap() {
  const presence = useStore((s) => s.presence);
  const [menu, setMenu] = useState<MenuItem[]>([]);
  useEffect(() => {
    fetch("/api/menu")
      .then((r) => (r.ok ? r.json() : []))
      .then(setMenu)
      .catch(() => setMenu([]));
  }, []);
  const rows = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of Object.values(presence))
      if (p.drink && p.drink !== "Water")
        counts[p.drink] = (counts[p.drink] ?? 0) + 1;
    const byName = Object.fromEntries(menu.map((d) => [d.name, d]));
    const drinking = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
    if (drinking.length)
      return drinking.map(([name, n]) => ({ name, n, d: byName[name] }));
    return menu.slice(0, 6).map((d) => ({ name: d.name, n: 0, d }));
  }, [presence, menu]);
  const water = Object.values(presence).filter(
    (p) => p.drink === "Water",
  ).length;

  return (
    <div className="chalkboard font-chalk mt-1 rounded-lg px-3 py-2 text-[#e9e4d4]">
      <div className="text-center text-[26px] leading-tight text-[#f3d98b]">
        On tap tonight
      </div>
      <div className="mt-1 space-y-0.5">
        {rows.map((r) => (
          <div
            key={r.name}
            className="flex items-baseline gap-2 text-[19px] leading-tight"
          >
            <span className="min-w-0 flex-1 truncate" title={r.d?.style ?? ""}>
              {r.name}
              {r.d?.style && (
                <span className="ml-1 text-[14px] text-[#bdb7a3]">
                  {r.d.style}
                </span>
              )}
            </span>
            {r.d?.abv != null && (
              <span className="text-[14px] text-[#bdb7a3]">{r.d.abv}%</span>
            )}
            {r.n > 0 && <span className="text-[#f3d98b]">×{r.n}</span>}
          </div>
        ))}
        {!rows.length && (
          <div className="text-[15px] text-[#bdb7a3]">
            Board's being chalked…
          </div>
        )}
        {water > 0 && (
          <div className="pt-1 text-[14px] text-[#bdb7a3]">
            and {water} on water
          </div>
        )}
      </div>
    </div>
  );
}

function Board({ zone }: { zone: string | null }) {
  const live = useLiveThreads();
  const feeds = useStore((s) => s.feeds);
  const shown = zone ? live.filter((t) => t.channel === zone) : live;

  const ended = useMemo(() => {
    const all = Object.values(feeds)
      .flatMap((f) => f.threads)
      .filter((t) => t.ended_at && (!zone || t.channel === zone));
    return all
      .sort((a, b) => +new Date(b.ended_at!) - +new Date(a.ended_at!))
      .slice(0, 14);
  }, [feeds, zone]);
  const comings = useMemo(() => {
    const all = Object.values(feeds)
      .flatMap((f) => f.messages)
      .filter((mm) => !zone || mm.channel === zone);
    return all.sort((a, b) => a.id - b.id).slice(-10);
  }, [feeds, zone]);

  return (
    <div className="scroll min-w-0 flex-1 px-5 py-4">
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="font-display text-[24px] font-semibold">
          {zone ? ZONES.find((z) => z.id === zone)?.title : "Tonight"}
        </h2>
        <span className="text-[12px] text-[var(--muted)]">
          {shown.length
            ? `${shown.length} conversation${shown.length === 1 ? "" : "s"} going`
            : "quiet for the moment"}
        </span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(330px,1fr))] gap-3">
        {shown.map((t) => (
          <div key={t.id} className="bubble-in">
            <LiveCard t={t} />
          </div>
        ))}
      </div>
      {!shown.length && (
        <div className="card rounded-xl px-5 py-8 text-center text-[var(--muted)]">
          Nobody's talking{zone ? " here" : ""} right now. Give it a minute: the
          room fills up after 3pm.
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[3fr_2fr]">
        <section>
          <h3 className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-[var(--muted)] uppercase">
            Earlier tonight
          </h3>
          <div className="flex flex-wrap gap-2">
            {ended.map((t) => (
              <EndedChip key={t.id} t={t} />
            ))}
            {!ended.length && (
              <span className="text-[13px] text-[var(--muted)]/60">
                Nothing yet.
              </span>
            )}
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-[var(--muted)] uppercase">
            Comings and goings
          </h3>
          <div className="card rounded-xl py-1">
            {comings.map((mm) => (
              <MessageRow key={mm.id} m={mm} />
            ))}
            {!comings.length && (
              <div className="px-4 py-2 text-[13px] text-[var(--muted)]/60">
                The door's been quiet.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function LiveCard({ t }: { t: Thread }) {
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const msgs = useStore((s) => s.threadMsgs[t.id]);
  const typing = useStore((s) => s.typing[t.id]);
  const open = useStore((s) => s.openThread === t.id);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const speech = (msgs ?? []).filter((mm) => mm.kind === "speech").slice(-2);
  const place = threadPlace(t, presence);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openThreadPane(t.id)}
      onKeyDown={(e) => e.key === "Enter" && openThreadPane(t.id)}
      className={`card live breathe block w-full cursor-pointer rounded-xl px-4 pt-3 pb-2 text-left ${open ? "ring-2 ring-[var(--accent)]" : ""}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-display text-[18px] font-semibold">{place}</div>
        <div className="text-[11px] text-[var(--muted)]">
          {t.kind === "order" ? "ordering · " : ""}
          {fmtTime(t.started_at)} · {t.count} lines
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {t.participants.slice(0, 6).map((id) => {
          const pr = presence[id];
          const ring = TIER_COLOR[pr?.tier ?? ""];
          return (
            <span
              key={id}
              className="flex items-center gap-1.5"
              title={
                pr?.drink
                  ? `${people[id]?.display} · ${pr.drink}`
                  : people[id]?.display
              }
            >
              <span
                className="rounded-full"
                style={{ boxShadow: ring ? `0 0 0 2px ${ring}` : undefined }}
              >
                <Avatar id={id} size={30} round />
              </span>
              <span className="text-[12px]">
                <span className="font-semibold">{people[id]?.short}</span>
                {pr?.drink && (
                  <span className="block text-[10px] leading-tight text-[var(--muted)]">
                    {pr.drink}
                  </span>
                )}
              </span>
            </span>
          );
        })}
      </div>
      <div className="mt-3 space-y-1.5">
        {speech.map((mm) => (
          <Bubble key={mm.id} m={mm} />
        ))}
        {!speech.length && (
          <div className="text-[13px] text-[var(--muted)]/70">
            {t.root_text}
          </div>
        )}
      </div>
      <TypingLine ids={(typing ?? []).filter((i) => people[i])} />
    </div>
  );
}

function Bubble({ m: mm }: { m: Msg }) {
  const p = useStore((s) =>
    mm.speaker_id ? s.people[mm.speaker_id] : undefined,
  );
  return (
    <div className="bubble px-3 py-1.5 text-[13.5px] leading-snug">
      {p && (
        <span className="mr-1.5 font-semibold" style={{ color: p.color }}>
          {p.short}
        </span>
      )}
      <span className="text-[var(--ink)]/90">{mm.text}</span>
    </div>
  );
}

function EndedChip({ t }: { t: Thread }) {
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const names = t.participants
    .map((id) => people[id]?.short)
    .filter(Boolean)
    .slice(0, 3)
    .join(", ");
  return (
    <button
      onClick={() => openThreadPane(t.id)}
      className="card cursor-pointer rounded-lg px-3 py-1.5 text-left text-[12px] hover:border-[var(--muted)]/50"
    >
      <span className="font-semibold">{threadPlace(t, presence)}</span>
      <span className="text-[var(--muted)]">
        {" "}
        · {names}
        {t.participants.length > 3 ? "…" : ""} · {t.count} lines · ended{" "}
        {fmtTime(t.ended_at!)}
      </span>
    </button>
  );
}
