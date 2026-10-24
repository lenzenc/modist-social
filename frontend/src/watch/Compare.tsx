import { useEffect, useRef, useState } from "react";
import "./compare.css";

const VIEWS = [
  { id: "tower", name: "Tower", line: "Conversations as flight strips; the floor, a roster and a timeline around them." },
  { id: "taps", name: "Taps", line: "Every live conversation as a column on one wall, tinted by what it's about." },
  { id: "ledger", name: "Ledger", line: "The night as a ruled sheet: one row per person, time running across." },
];

function Frame({ id, name, line }: { id: string; name: string; line: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.3);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / 1440));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <section className="cmp-card">
      <div className="cmp-head">
        <div>
          <h2>{name}</h2>
          <p>{line}</p>
        </div>
        <a href={`/watch/${id}`}>Open full screen</a>
      </div>
      <div className="cmp-frame" ref={box} style={{ height: 900 * scale }}>
        <iframe title={name} src={`/watch/${id}`} style={{ width: 1440, height: 900, transform: `scale(${scale})` }} />
      </div>
    </section>
  );
}

/** The three watch views, live, side by side. */
export default function Compare() {
  return (
    <main className="cmp">
      <header>
        <h1>Three ways to watch the taproom</h1>
        <p>Each frame is the real view on the same live simulation.</p>
      </header>
      <div className="cmp-grid">
        {VIEWS.map((v) => (
          <Frame key={v.id} {...v} />
        ))}
      </div>
    </main>
  );
}
