import "@fontsource/ibm-plex-sans-condensed/400.css";
import "@fontsource/ibm-plex-sans-condensed/500.css";
import "@fontsource/ibm-plex-sans-condensed/600.css";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Controls } from "../../components/Controls";
import { useStore } from "../../store";
import { fmtDayTime, fmtTime } from "../../util";
import { eventKind, plain } from "../shared/events";
import { tint, ZONE_LABEL } from "../shared/scales";
import { useSlow } from "../shared/useSlow";
import { selPresence, useThrottled } from "../shared/useThrottled";
import { useWatch } from "../shared/useTonight";
import { Detail } from "./Detail";
import { buildNight, type Person } from "./model";
import "./ledger.css";

const ROW = 28;
const LABEL_W = 184;
const RIGHT = 20;
const LOC_COLOR: Record<string, string> = {
  bar: "#8c5a35",
  "inside-tables": "#5f7d6a",
  patio: "#7a8fb0",
  ordering: "#b9a27a",
};
const NEED: Record<string, string> = { restroom: "restroom", call: "phone call", air: "air", food: "food", smoke: "smoke" };
const HOUR = 3600e3;

type SortKey = "arrival" | "stay" | "mood" | "buzz" | "name";

const Row = memo(function Row({ p, y, x, now, onSpan, people }: {
  p: Person;
  y: number;
  x: (t: number) => number;
  now: number;
  onSpan: (thread: number) => void;
  people: Record<string, { short: string }>;
}) {
  const w = (a: number, b: number) => Math.max(1.5, x(b) - x(a));
  return (
    <g transform={`translate(0,${y})`}>
      {p.runs.map((r, i) => {
        const color = LOC_COLOR[r.loc ?? "ordering"] ?? "#999";
        const talking = r.thread != null;
        return (
          <rect key={i} x={x(r.t0)} y={6} width={w(r.t0, r.t1)} height={14} rx={2.5} fill={color}
            fillOpacity={talking ? 1 : 0.3} className={talking ? "ld-span" : undefined}
            onClick={talking ? () => onSpan(r.thread!) : undefined}>
            <title>{`${people[p.id]?.short ?? p.id}: ${talking ? "talking" : "on their own"} ${ZONE_LABEL[r.loc ?? "ordering"]?.toLowerCase() ?? ""}, ${fmtTime(new Date(r.t0).toISOString())} to ${fmtTime(new Date(Math.min(r.t1, now)).toISOString())}`}</title>
          </rect>
        );
      })}
      {p.mood.map((s, i) => <rect key={i} x={x(s.t0)} y={21} width={w(s.t0, s.t1)} height={2.5} fill={s.color} />)}
      {p.buzz.map((s, i) => <rect key={i} x={x(s.t0)} y={24} width={w(s.t0, s.t1)} height={2.5} fill={s.color} />)}
      {p.beads.map((t, i) => <circle key={i} cx={x(t)} cy={13} r={2.6} className="ld-bead" />)}
      {p.needs.map((n, i) => (
        <path key={i} d={`M${x(n.t) - 3},1 L${x(n.t) + 3},1 L${x(n.t)},5.5 Z`} className="ld-need"><title>{`Needs ${NEED[n.need] ?? n.need}`}</title></path>
      ))}
      {p.cuts.map((t, i) => (
        <path key={i} d={`M${x(t) - 2.5},1.5 L${x(t) + 2.5},5.5 M${x(t) + 2.5},1.5 L${x(t) - 2.5},5.5`} className="ld-cut"><title>Cut off</title></path>
      ))}
    </g>
  );
});

export default function Ledger() {
  useWatch(8_000);
  const tonight = useStore((s) => s.tonight);
  const clock = useStore((s) => s.clock);
  const people = useStore((s) => s.people);
  const presence = useThrottled(selPresence, 1000);
  const profileId = useStore((s) => s.profileId);
  const openProfile = useStore((s) => s.openProfile);
  const openThreadPane = useStore((s) => s.openThreadPane);
  const banner = useStore((s) => s.banner);

  const onSpan = useCallback((id: number) => void openThreadPane(id), [openThreadPane]);
  const [sort, setSort] = useState<SortKey>("arrival");
  const [hereOnly, setHereOnly] = useState(false);
  const [range, setRange] = useState<"night" | "recent">("night");
  const [w, setW] = useState(900);
  const plot = useRef<HTMLDivElement>(null);
  const cursorLine = useRef<SVGLineElement>(null);
  const cursorLabel = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = plot.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // The sheet is big; follow the clock every few seconds rather than on every tick.
  const now = useSlow(clock ? new Date(clock.sim_now).getTime() : Date.now(), 4000);
  const night = useMemo(() => (tonight ? buildNight(tonight, now) : null), [tonight, now]);

  const rows = useMemo(() => {
    if (!night) return [];
    const nameOf = (p: Person) => people[p.id]?.display ?? p.id;
    const latest = (p: Person) => p.pts[p.pts.length - 1];
    const list = night.people.filter((p) => people[p.id]?.role !== "bartender" && (!hereOnly || presence[p.id]));
    const by: Record<SortKey, (a: Person, b: Person) => number> = {
      arrival: (a, b) => a.first - b.first || nameOf(a).localeCompare(nameOf(b)),
      stay: (a, b) => (b.last - b.first) - (a.last - a.first),
      mood: (a, b) => (presence[b.id]?.mood ?? latest(b).mood) - (presence[a.id]?.mood ?? latest(a).mood),
      buzz: (a, b) => (presence[b.id]?.buzz ?? latest(b).buzz) - (presence[a.id]?.buzz ?? latest(a).buzz),
      name: (a, b) => nameOf(a).localeCompare(nameOf(b)),
    };
    return [...list].sort(by[sort]);
  }, [night, people, presence, sort, hereOnly]);

  const t0 = night ? (range === "recent" ? Math.max(night.t0, now - 2 * HOUR) : night.t0) : now - 2 * HOUR;
  const lastSample = night ? night.samples[night.samples.length - 1] + night.step : t0;
  // While the doors are shut this is last night's sheet: end it where the night ended.
  const t1 = Math.max(clock?.open === false ? lastSample : now, t0 + 2 * HOUR);
  const innerW = Math.max(200, w - RIGHT);
  const x = useMemo(() => (t: number) => ((t - t0) / (t1 - t0)) * innerW, [t0, t1, innerW]);
  const hours: number[] = [];
  const stride = Math.max(1, Math.ceil(70 / (innerW / ((t1 - t0) / HOUR))));
  for (let t = Math.ceil(t0 / HOUR) * HOUR, i = 0; t <= t1 && hours.length < 48; t += HOUR, i++) if (i % stride === 0) hours.push(t);
  const marks = (tonight?.events ?? []).flatMap((e) => {
    const k = eventKind(e.text);
    return k === "flag" || k === "alert" ? [{ t: new Date(e.sim_ts).getTime(), k, text: plain(e.text) }] : [];
  });
  const here = night ? night.people.filter((p) => presence[p.id] && people[p.id]?.role !== "bartender").length : 0;
  const total = night ? night.people.filter((p) => people[p.id]?.role !== "bartender").length : 0;

  const track = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    const t = t0 + (px / innerW) * (t1 - t0);
    cursorLine.current?.setAttribute("x1", String(px));
    cursorLine.current?.setAttribute("x2", String(px));
    cursorLine.current?.setAttribute("opacity", "1");
    if (cursorLabel.current) cursorLabel.current.textContent = fmtTime(new Date(t).toISOString());
  };
  const height = rows.length * ROW;

  return (
    <div className="ld">
      <header className="ld-top">
        <div className="ld-brand"><span className="ld-mark" aria-hidden><i /><i /><i /></span><b>Ledger</b></div>
        <div className="ld-clock">
          {clock ? <b>{fmtDayTime(clock.sim_now)}</b> : null}
          <span>{clock ? (clock.open ? "open" : "closed") : "connecting"}</span>
          {clock?.occasion ? <span>{clock.occasion}</span> : null}
          <span>{total} came in, {here} still here</span>
        </div>
        <div className="ld-controls"><Controls /></div>
      </header>
      {banner && <div className="ld-banner">{banner}</div>}
      <div className="ld-bar">
        <label>Order by
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="arrival">Arrival</option>
            <option value="stay">Longest stay</option>
            <option value="mood">Mood now</option>
            <option value="buzz">Buzz now</option>
            <option value="name">Name</option>
          </select>
        </label>
        <div className="seg" role="group" aria-label="Time range">
          <button className={range === "night" ? "on" : ""} onClick={() => setRange("night")} aria-pressed={range === "night"}>Whole night</button>
          <button className={range === "recent" ? "on" : ""} onClick={() => setRange("recent")} aria-pressed={range === "recent"}>Last 2 hours</button>
        </div>
        <button className={`tog${hereOnly ? " on" : ""}`} onClick={() => setHereOnly((v) => !v)} aria-pressed={hereOnly}>Here now</button>
        <div className="key" aria-hidden>
          {Object.entries(LOC_COLOR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{ZONE_LABEL[k]}</span>)}
          <span><i className="pale" />on their own</span>
          <span><i className="bead" />drink</span>
          <span><i className="need" />need</span>
        </div>
        <span className="ld-time" ref={cursorLabel} aria-hidden />
      </div>
      <div className="ld-body">
        <div className="ld-scroll">
          <div className="ld-sheet" style={{ gridTemplateColumns: `${LABEL_W}px minmax(0, 1fr)` }}>
            <div className="ld-corner" />
            <div className="ld-axis" ref={plot}>
              <svg width={innerW} height={30} aria-hidden>
                {hours.map((t) => <text key={t} x={x(t)} y={19} textAnchor="middle">{fmtTime(new Date(t).toISOString())}</text>)}
              </svg>
            </div>
            <ul className="ld-names" aria-label="People">
              {rows.map((p) => {
                const person = people[p.id];
                const gone = !presence[p.id];
                return (
                  <li key={p.id} style={{ height: ROW }} className={`${gone ? "gone" : ""}${profileId === p.id ? " sel" : ""}`}>
                    <button onClick={() => void openProfile(profileId === p.id ? null : p.id)}>
                      <span className="chip" style={{ background: tint(person?.color ?? "#999") }}>{(person?.display ?? "?").replace(/"/g, "").split(/\s+/).slice(0, 2).map((s) => s[0]).join("")}</span>
                      <span className="nm">{person?.short ?? p.id}</span>
                      <span className="meta">{gone ? `left ${fmtTime(new Date(p.last).toISOString())}` : fmtTime(new Date(p.first).toISOString())}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <svg className="ld-plot" width={innerW} height={Math.max(height, 40)} onMouseMove={track} onMouseLeave={() => { cursorLine.current?.setAttribute("opacity", "0"); if (cursorLabel.current) cursorLabel.current.textContent = ""; }}>
              {hours.map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={0} y2={height} className="ld-hour" />)}
              {rows.map((_, i) => <line key={i} x1={0} x2={innerW} y1={(i + 1) * ROW} y2={(i + 1) * ROW} className="ld-rule" />)}
              {marks.filter((m) => m.t >= t0).map((m, i) => (
                <line key={i} x1={x(m.t)} x2={x(m.t)} y1={0} y2={height} className={`ld-flag ${m.k}`}><title>{m.text}</title></line>
              ))}
              {rows.map((p, i) => <Row key={p.id} p={p} y={i * ROW} x={x} now={now} people={people} onSpan={onSpan} />)}
              <line x1={x(now)} x2={x(now)} y1={0} y2={height} className="ld-now" />
              <line ref={cursorLine} y1={0} y2={height} className="ld-cursor" opacity={0} />
            </svg>
          </div>
          {!rows.length && <p className="ld-empty">{night ? "No one matches." : "The sheet starts when the doors open and the first sample is taken."}</p>}
        </div>
        <Detail night={night} t0={t0} t1={t1} />
      </div>
    </div>
  );
}
