import "@fontsource/ibm-plex-sans";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono";
import "@fontsource/ibm-plex-mono/500.css";
import "../shared/skin-base.css";
import "./floor.css";

import { useEffect, useMemo, useState } from "react";
import { Controls } from "../../components/Controls";
import { ProfilePane } from "../../components/RightPane";
import { StatsBar } from "../../components/StatsBar";
import { useStore } from "../../store";
import { BAR, COUNTER, DOORS, PATIO, placeAll, ROOM, STOOLS, TABLE_SIZE, TABLES } from "../../taproom/layout";
import type { Thread } from "../../types";
import { fmtDay, fmtTime, initials } from "../../util";
import { BudgetBanner } from "../shared/BudgetBanner";
import { NewsTicker } from "../shared/NewsTicker";
import { OpenSign } from "../shared/OpenSign";
import { Transcript } from "../shared/Transcript";
import { useAllFeeds, useLiveThreads } from "../shared/useAllFeeds";
import { seatLabel, threadPlace, TIER_COLOR, useRoster } from "../shared/useRoster";

/** Floor Map: the room drawn to scale, people where they sit, conversations as halos you can click to listen in. */
export default function Floor() {
  const connect = useStore((s) => s.connect);
  useEffect(() => connect(), [connect]);
  useAllFeeds();

  return (
    <div className="flex h-full flex-col">
      <Header />
      <BudgetBanner />
      <div className="flex min-h-0 flex-1">
        <div className="plan-bg relative min-w-0 flex-1">
          <FloorPlan />
          <Legend />
        </div>
        <Listening />
      </div>
      <div className="flex items-center border-t border-[var(--border)] bg-[var(--sidebar)]">
        <NewsTicker className="min-w-0 flex-1 px-4 py-1 font-mono text-[11px] text-[var(--muted)]" />
      </div>
      <StatsBar />
    </div>
  );
}

function Header() {
  const clock = useStore((s) => s.clock);
  const city = useStore((s) => s.city);
  const { patrons, bartenders } = useRoster();
  const room = clock?.room;
  return (
    <header className="flex items-center gap-5 border-b border-[var(--border)] bg-[var(--sidebar)] px-4 py-2">
      <div>
        <div className="text-[16px] font-semibold tracking-tight">Modist Social</div>
        <div className="font-mono text-[10px] tracking-[0.18em] text-[var(--muted)] uppercase">{city || "Taproom"} · floor</div>
      </div>
      <OpenSign className="text-[18px]" />
      {clock && (
        <div className="font-mono text-[18px]">
          <span className="text-[var(--muted)]">{fmtDay(clock.sim_now)}</span> {fmtTime(clock.sim_now)}
          {clock.paused && <span className="ml-2 text-[10px] tracking-[0.18em] text-[var(--muted)] uppercase">paused</span>}
        </div>
      )}
      <div className="font-mono text-[11px] text-[var(--muted)]">
        {patrons.length} guests · {bartenders.length} on shift
        {room && <> · {room.weather} · {room.noise}</>}
        {room?.game?.live && <span className="ml-2 text-[var(--accent)]">📺 {room.game.team} {room.game.score[0]}–{room.game.score[1]} {room.game.opp}</span>}
        {room?.trivia && <span className="ml-2 text-[var(--accent)]">trivia night</span>}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Controls />
      </div>
    </header>
  );
}

const VIEW = { x: -0.6, y: -1.1, w: ROOM.w + 1.2, h: PATIO.z + PATIO.d + 0.6 + 1.1 };
const R = 0.34; // person radius in world units

function FloorPlan() {
  const people = useStore((s) => s.people);
  const presence = useStore((s) => s.presence);
  const clock = useStore((s) => s.clock);
  const typing = useStore((s) => s.typing);
  const threadMsgs = useStore((s) => s.threadMsgs);
  const openThread = useStore((s) => s.openThread);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const openProfile = useStore((s) => s.openProfile);
  const live = useLiveThreads();

  const spots = useMemo(
    () => placeAll(Object.values(presence), (id) => people[id]?.role === "bartender", clock?.on_shift ?? []),
    [presence, people, clock?.on_shift],
  );

  // One halo per live conversation, around everyone in it who is in the room.
  const halos = useMemo(() => {
    return live
      .map((t) => {
        const members = Object.values(presence).filter((p) => p.thread_id === t.id && spots[p.id]);
        const pts = members.map((p) => spots[p.id].pos);
        if (!pts.length) return null;
        // A pill around everyone in it: tight for a pair at a table, long for a row of stools.
        const pad = R + 0.32;
        const x0 = Math.min(...pts.map((p) => p[0])) - pad;
        const x1 = Math.max(...pts.map((p) => p[0])) + pad;
        const z0 = Math.min(...pts.map((p) => p[1])) - pad;
        const z1 = Math.max(...pts.map((p) => p[1])) + pad;
        const last = (threadMsgs[t.id] ?? []).filter((m) => m.kind === "speech").at(-1);
        return { t, x0, x1, z0, z1, typing: (typing[t.id] ?? []).length > 0, last };
      })
      .filter((h): h is NonNullable<typeof h> => h != null);
  }, [live, presence, spots, typing, threadMsgs]);

  const game = clock?.room?.game;

  return (
    <svg viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`} className="h-full w-full" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="haloFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.2" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.07" />
        </linearGradient>
      </defs>

      {/* Room */}
      <rect x={0} y={0} width={ROOM.w} height={ROOM.d} rx={0.15} fill="var(--panel)" stroke="var(--border)" strokeWidth={0.06} />
      <rect x={PATIO.x} y={PATIO.z} width={PATIO.w} height={PATIO.d} rx={0.15} fill="rgb(255 255 255 / 0.02)" stroke="var(--border)" strokeWidth={0.05} strokeDasharray="0.25 0.18" />
      <Label x={PATIO.x + PATIO.w / 2} y={PATIO.z + PATIO.d - 0.25} text="PATIO" />
      {[PATIO.x + 1.2, PATIO.x + PATIO.w - 1.2].map((x) => (
        <g key={x}>
          <circle cx={x} cy={PATIO.z + PATIO.d / 2} r={0.32} fill="#2a1b12" stroke="#5a4330" strokeWidth={0.04} />
          <circle cx={x} cy={PATIO.z + PATIO.d / 2} r={0.14} fill="#f2a93b" opacity={0.85} />
        </g>
      ))}

      {/* Bar and counter */}
      <rect x={BAR.x} y={BAR.z} width={BAR.w} height={BAR.d} rx={0.12} fill="var(--wood)" stroke="var(--wood-edge)" strokeWidth={0.05} />
      <Label x={BAR.x + BAR.w / 2} y={BAR.z + BAR.d / 2 + 0.12} text="THE LONG OAK BAR" muted />
      <rect x={COUNTER.x} y={COUNTER.z} width={COUNTER.w} height={COUNTER.d} rx={0.12} fill="var(--wood)" stroke="var(--wood-edge)" strokeWidth={0.05} />
      <Label x={COUNTER.x + COUNTER.w / 2} y={COUNTER.z + COUNTER.d / 2 + 0.12} text="ORDER" muted />
      <rect x={0.2} y={0.15} width={1.4} height={1.3} rx={0.1} fill="none" stroke="var(--border)" strokeWidth={0.04} />
      <Label x={0.9} y={0.9} text="TAPS" muted />

      {/* TV on the back wall */}
      <g>
        <rect x={17.2} y={0.25} width={2.6} height={1.0} rx={0.08} fill={game?.live ? "#101a22" : "#0b0f14"} stroke="var(--border)" strokeWidth={0.04} />
        <Label x={18.5} y={0.65} text={game?.live ? `${game.team.toUpperCase()} ${game.score[0]}–${game.score[1]}` : "TV"} muted={!game?.live} accent={!!game?.live} />
        {game?.live && <Label x={18.5} y={1.05} text={game.opp.toUpperCase()} muted />}
      </g>

      {/* Doors */}
      {DOORS.map(([x, z]) => (
        <g key={x}>
          <rect x={x - 0.6} y={z - 0.08} width={1.2} height={0.16} fill="var(--canvas)" stroke="var(--border)" strokeWidth={0.04} />
          <Label x={x} y={z + 0.5} text="DOOR" muted />
        </g>
      ))}

      {/* Stools and tables */}
      {STOOLS.map(([x, z], i) => (
        <circle key={i} cx={x} cy={z} r={0.2} fill="var(--panel-2)" stroke="var(--border)" strokeWidth={0.04} />
      ))}
      {Object.entries(TABLES).flatMap(([area, list]) =>
        list.map(([x, z], i) => (
          <g key={`${area}${i}`}>
            <rect x={x - TABLE_SIZE[0] / 2} y={z - TABLE_SIZE[1] / 2} width={TABLE_SIZE[0]} height={TABLE_SIZE[1]} rx={0.18} fill="var(--panel-2)" stroke="var(--border)" strokeWidth={0.04} />
            <Label x={x} y={z + 0.1} text={String(i + 1)} muted />
          </g>
        )),
      )}

      {/* Conversation halos */}
      {halos.map((h) => (
        <g
          key={h.t.id}
          className={`halo ${h.typing ? "halo-pulse" : ""}`}
          onClick={() => openThreadPane(openThread === h.t.id ? null : h.t.id)}
        >
          <rect x={h.x0} y={h.z0} width={h.x1 - h.x0} height={h.z1 - h.z0} rx={Math.min(h.x1 - h.x0, h.z1 - h.z0) / 2} fill="url(#haloFill)" stroke="var(--accent)" strokeOpacity={openThread === h.t.id ? 1 : 0.45} strokeWidth={openThread === h.t.id ? 0.08 : 0.04} />
          <title>{threadPlace(h.t, presence)}: {h.t.root_text}</title>
        </g>
      ))}

      {/* People */}
      {Object.entries(spots).map(([id, spot]) => {
        const p = people[id];
        const pr = presence[id];
        if (!p) return null;
        const ring = TIER_COLOR[pr?.tier ?? ""];
        const bt = p.role === "bartender";
        return (
          <g
            key={id}
            className="person"
            style={{ transform: `translate(${spot.pos[0]}px, ${spot.pos[1]}px)` }}
            onClick={() => openProfile(id)}
          >
            <title>{`${p.display} · ${seatLabel(pr)}${pr?.drink ? ` · ${pr.drink}` : ""}${pr?.tier && pr.tier !== "sober" ? ` · ${pr.tier}` : ""}`}</title>
            {bt ? (
              <rect x={-R} y={-R} width={R * 2} height={R * 2} rx={0.09} fill={p.color} stroke="var(--accent)" strokeWidth={0.06} />
            ) : (
              <circle r={R} fill={p.color} stroke={ring ?? "rgb(0 0 0 / 0.35)"} strokeWidth={ring ? 0.08 : 0.04} />
            )}
            <text textAnchor="middle" dominantBaseline="central" fontSize={0.27} fontWeight={600} fill="#fff" fontFamily="var(--font-mono)">
              {initials(p.display)}
            </text>
          </g>
        );
      })}

      {/* Latest line above each halo, fading out */}
      {halos.map((h) =>
        h.last ? (
          <Say key={`${h.t.id}-${h.last.id}`} x={(h.x0 + h.x1) / 2} y={h.z0 - 0.22} who={people[h.last.speaker_id ?? ""]?.short ?? ""} text={h.last.text} />
        ) : null,
      )}
    </svg>
  );
}

function Label({ x, y, text, muted = false, accent = false }: { x: number; y: number; text: string; muted?: boolean; accent?: boolean }) {
  return (
    <text x={x} y={y} textAnchor="middle" fontSize={0.26} letterSpacing={0.04} fontFamily="var(--font-mono)" fill={accent ? "var(--accent)" : muted ? "var(--muted)" : "var(--ink)"} opacity={muted ? 0.8 : 1}>
      {text}
    </text>
  );
}

function Say({ x, y, who, text }: { x: number; y: number; who: string; text: string }) {
  const line = text.length > 64 ? text.slice(0, 62) + "…" : text;
  const w = Math.min(VIEW.w - 1, (who.length + 2 + line.length) * 0.155 + 0.4);
  const left = Math.max(VIEW.x + 0.2, Math.min(x - w / 2, VIEW.x + VIEW.w - w - 0.2));
  return (
    <g className="say">
      <rect x={left} y={y - 0.42} width={w} height={0.56} rx={0.14} fill="var(--panel-2)" stroke="var(--border)" strokeWidth={0.03} />
      <text x={left + 0.2} y={y - 0.06} fontSize={0.26} fontFamily="var(--font-body)" fill="var(--ink)">
        <tspan fontWeight={600} fill="var(--accent)">{who}</tspan>
        <tspan> {line}</tspan>
      </text>
    </g>
  );
}

function Legend() {
  return (
    <div className="pointer-events-none absolute top-2 left-3 flex gap-3 font-mono text-[10px] text-[var(--muted)]">
      <span><span className="mr-1 inline-block h-2 w-2 rounded-full border-2 border-[var(--accent)]" />conversation</span>
      <span><span className="mr-1 inline-block h-2 w-2 rounded-sm border border-[var(--accent)] bg-[var(--muted)]" />bartender</span>
      {Object.entries(TIER_COLOR).map(([k, c]) => (
        <span key={k}><span className="mr-1 inline-block h-2 w-2 rounded-full border-2" style={{ borderColor: c }} />{k}</span>
      ))}
      <span>click a halo to listen · click a person for their story</span>
    </div>
  );
}

function Listening() {
  const openThread = useStore((s) => s.openThread);
  const profileId = useStore((s) => s.profileId);
  if (profileId) return <ProfilePane />;
  return (
    <aside className="flex w-[26rem] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--sidebar)]">
      {openThread != null ? <Transcript id={openThread} /> : <LiveNow />}
    </aside>
  );
}

function LiveNow() {
  const live = useLiveThreads();
  const presence = useStore((s) => s.presence);
  const people = useStore((s) => s.people);
  const threadMsgs = useStore((s) => s.threadMsgs);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const { byLocation, bartenders } = useRoster();
  const [hover, setHover] = useState<number | null>(null);
  void hover;
  const rows = live
    .map((t) => ({ t, last: (threadMsgs[t.id] ?? []).filter((m) => m.kind === "speech").at(-1) }))
    .sort((a, b) => (b.last?.id ?? 0) - (a.last?.id ?? 0));
  const zones: [string, string][] = [["bar", "Bar"], ["inside-tables", "Inside"], ["patio", "Patio"], ["ordering", "Counter"], ["door", "Door"]];
  return (
    <>
      <div className="border-b border-[var(--border)] px-4 py-3">
        <div className="font-mono text-[10px] tracking-[0.18em] text-[var(--muted)] uppercase">Live now</div>
        <div className="text-[15px] font-semibold">{rows.length ? `${rows.length} conversation${rows.length === 1 ? "" : "s"}` : "Quiet for the moment"}</div>
      </div>
      <div className="scroll flex-1">
        {rows.map(({ t, last }) => (
          <Row key={t.id} t={t} place={threadPlace(t, presence)} names={t.participants.map((p) => people[p]?.short).filter(Boolean).join(", ")} last={last ? `${people[last.speaker_id ?? ""]?.short ?? ""}: ${last.text}` : t.root_text} onClick={() => openThreadPane(t.id)} onHover={setHover} />
        ))}
        {!rows.length && <div className="px-4 py-6 text-[13px] text-[var(--muted)]">Nobody's talking yet. Click a halo on the map when one appears.</div>}
      </div>
      <div className="grid grid-cols-5 border-t border-[var(--border)] font-mono text-[11px]">
        {zones.map(([id, label]) => (
          <div key={id} className="px-3 py-2">
            <div className="text-[10px] tracking-[0.14em] text-[var(--muted)] uppercase">{label}</div>
            <div className="text-[15px]">{(byLocation[id] ?? []).filter((p) => p.role === "patron").length}</div>
          </div>
        ))}
      </div>
      <div className="border-t border-[var(--border)] px-3 py-2 font-mono text-[11px] text-[var(--muted)]">
        On shift: {bartenders.map((b) => b.short).join(", ") || "nobody"}
      </div>
    </>
  );
}

function Row({ t, place, names, last, onClick, onHover }: { t: Thread; place: string; names: string; last: string; onClick: () => void; onHover: (id: number | null) => void }) {
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => onHover(t.id)}
      onMouseLeave={() => onHover(null)}
      className="block w-full cursor-pointer border-b border-[var(--border)] px-4 py-2.5 text-left hover:bg-white/5"
    >
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] font-semibold">{place}</span>
        <span className="font-mono text-[10px] text-[var(--muted)]">{t.kind === "order" ? "order · " : ""}{t.count} lines</span>
      </div>
      <div className="truncate text-[11px] text-[var(--muted)]">{names}</div>
      <div className="mt-0.5 truncate text-[12px]">{last}</div>
    </button>
  );
}
