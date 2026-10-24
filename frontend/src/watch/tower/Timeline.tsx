import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../../store";
import { fmtTime } from "../../util";
import { eventKind, plain } from "../shared/events";
import { moodColor } from "../shared/scales";

const H = 112;
const PAD = { l: 44, r: 16, t: 14, b: 22 };

export function Timeline() {
  const tonight = useStore((s) => s.tonight);
  const now = useStore((s) => s.clock?.sim_now);
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const data = useMemo(() => {
    if (!tonight?.opened || !now) return null;
    const t0 = new Date(tonight.opened).getTime();
    const t1 = Math.max(new Date(now).getTime(), t0 + 2 * 3600e3);
    const rows = tonight.samples.map((s) => {
      const mood = s.p.length ? s.p.reduce((a, r) => a + r[3], 0) / s.p.length : 0;
      return { t: new Date(s.t).getTime(), n: s.p.length, mood, talking: s.p.filter((r) => r[2] != null).length };
    });
    const marks = tonight.events.flatMap((e) => {
      const kind = eventKind(e.text);
      return kind ? [{ t: new Date(e.sim_ts).getTime(), kind, text: plain(e.text) }] : [];
    });
    return { t0, t1, rows, marks, max: Math.max(10, ...rows.map((r) => r.n)) };
  }, [tonight, now]);

  if (!data) return <section className="tw-time"><h2>Tonight</h2><p className="tw-empty">The night log starts when the doors open.</p></section>;

  const iw = w - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const x = (t: number) => PAD.l + ((t - data.t0) / (data.t1 - data.t0)) * iw;
  const yN = (n: number) => PAD.t + ih - (n / data.max) * ih;
  const yM = (m: number) => PAD.t + ih / 2 - (m / 0.6) * (ih / 2);
  const area = data.rows.length
    ? `M${x(data.rows[0].t)},${PAD.t + ih} ` + data.rows.map((r) => `L${x(r.t)},${yN(r.n)}`).join(" ") + ` L${x(data.rows[data.rows.length - 1].t)},${PAD.t + ih} Z`
    : "";
  const line = data.rows.map((r, i) => `${i ? "L" : "M"}${x(r.t)},${Math.max(PAD.t, Math.min(PAD.t + ih, yM(r.mood)))}`).join(" ");
  const hours: number[] = [];
  for (let t = Math.ceil(data.t0 / 3600e3) * 3600e3; t <= data.t1; t += 3600e3) hours.push(t);
  const hovered = hover != null ? data.rows[hover] : null;
  const lastRow = data.rows[data.rows.length - 1];

  return (
    <section className="tw-time" aria-label="Tonight so far">
      <h2>
        Tonight
        {lastRow && <span>{lastRow.n} here, mood {lastRow.mood > 0.1 ? "up" : lastRow.mood < -0.1 ? "down" : "level"}</span>}
      </h2>
      <div ref={box} className="tw-time-chart">
        <svg width={w} height={H} role="img" aria-label="Headcount and room mood since opening">
          {hours.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={PAD.t} y2={PAD.t + ih} className="tw-grid" />
              <text x={x(t)} y={H - 6} textAnchor="middle" className="tw-axis">{fmtTime(new Date(t).toISOString())}</text>
            </g>
          ))}
          <line x1={PAD.l} x2={PAD.l + iw} y1={PAD.t + ih / 2} y2={PAD.t + ih / 2} className="tw-grid mid" />
          <text x={PAD.l - 6} y={PAD.t + 8} textAnchor="end" className="tw-axis">up</text>
          <text x={PAD.l - 6} y={PAD.t + ih} textAnchor="end" className="tw-axis">down</text>
          <path d={area} className="tw-area" />
          <path d={line} className="tw-mood" />
          {data.marks.map((m, i) => (
            <g key={i}>
              {(m.kind === "flag" || m.kind === "alert") && <line x1={x(m.t)} x2={x(m.t)} y1={PAD.t} y2={PAD.t + ih} className={`tw-mark ${m.kind}`} />}
              {(m.kind === "in" || m.kind === "out") && (
                <line x1={x(m.t)} x2={x(m.t)} y1={PAD.t + ih - 6} y2={PAD.t + ih} className={`tw-tick ${m.kind}`} />
              )}
              <title>{`${fmtTime(new Date(m.t).toISOString())} ${m.text}`}</title>
            </g>
          ))}
          {hovered && (
            <g>
              <line x1={x(hovered.t)} x2={x(hovered.t)} y1={PAD.t} y2={PAD.t + ih} className="tw-hover" />
              <circle cx={x(hovered.t)} cy={Math.max(PAD.t, Math.min(PAD.t + ih, yM(hovered.mood)))} r={4} fill={moodColor(hovered.mood * 1.6)} stroke="#14243a" />
            </g>
          )}
          <rect
            x={PAD.l} y={PAD.t} width={iw} height={ih} fill="transparent"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const bx = e.currentTarget.getBoundingClientRect().left;
              const t = data.t0 + ((e.clientX - bx) / iw) * (data.t1 - data.t0);
              let best = 0;
              data.rows.forEach((r, i) => { if (Math.abs(r.t - t) < Math.abs(data.rows[best].t - t)) best = i; });
              setHover(data.rows.length ? best : null);
            }}
          />
        </svg>
        {hovered && (
          <div className="tw-tip" style={{ left: Math.min(w - 180, Math.max(PAD.l, x(hovered.t) + 10)) }}>
            <b>{fmtTime(new Date(hovered.t).toISOString())}</b> {hovered.n} here, {hovered.talking} in a chat
          </div>
        )}
      </div>
    </section>
  );
}
